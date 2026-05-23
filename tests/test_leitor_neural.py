import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "mock-key")

mock_supabase_client_module = MagicMock()
mock_supabase_client_module.supabase = MagicMock()
sys.modules["supabase_client"] = mock_supabase_client_module

mock_requests = MagicMock()
mock_requests.Timeout = type("Timeout", (Exception,), {})
sys.modules["requests"] = mock_requests

sys.modules["google.auth.transport.requests"] = MagicMock()
sys.modules["google.auth"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.credentials"] = MagicMock()
sys.modules["google_auth_oauthlib"] = MagicMock()
sys.modules["google_auth_oauthlib.flow"] = MagicMock()
sys.modules["googleapiclient"] = MagicMock()
sys.modules["googleapiclient.discovery"] = MagicMock()
sys.modules["googleapiclient.errors"] = MagicMock()

import gmail_client
import agente_leitor_neural


class TestGmailClient(unittest.TestCase):

    def test_buscar_emails_retorna_corpo(self):
        mock_service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": [{"id": "msg001"}]}
        mock_service.users().messages().list.return_value = mock_list

        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "msg001",
            "payload": {
                "headers": [
                    {"name": "From", "value": "clinica@exemplo.com"},
                    {"name": "To", "value": "atlas@meudominio.com"},
                    {"name": "Subject", "value": "Re: Proposta ATLAS"},
                    {"name": "Date", "value": "2026-01-01"},
                ],
                "mimeType": "text/plain",
                "body": {
                    "data": "T2zBIEJsZWNrc29uLCBlc3RvdSBpbnRlcmVzc2FkbyBlbS"
                            "BtYWlzIGluZm9ybWFjb2VzLiBBdGVuY2lvc2FtZW50ZSwgSm9hbw=="
                },
            },
        }
        mock_service.users().messages().get.return_value = mock_get

        gmail_client._get_service = MagicMock(return_value=mock_service)
        emails = gmail_client.buscar_emails(query="is:unread", max_results=5)
        self.assertEqual(len(emails), 1)
        self.assertIn("corpo", emails[0])
        self.assertTrue(len(emails[0]["corpo"]) > 0)
        self.assertLessEqual(len(emails[0]["corpo"]), 400)


class TestGmailClientSanitize(unittest.TestCase):

    def test_sanitizar_colapsa_espacos(self):
        sujo = "Ola   Bleckson,\n\nestou       interessado\r\nem mais\n\ninformacoes."
        limpo = gmail_client._sanitizar_corpo(sujo)
        self.assertNotIn("  ", limpo)
        self.assertNotIn("\n\n", limpo)
        self.assertNotIn("\r", limpo)

    def test_sanitizar_trunca_400(self):
        longo = "A" * 600
        resultado = gmail_client._sanitizar_corpo(longo)
        self.assertEqual(len(resultado), 400)

    def test_sanitizar_vazio(self):
        self.assertEqual(gmail_client._sanitizar_corpo(""), "")
        self.assertEqual(gmail_client._sanitizar_corpo(None), "")


class TestLeitorNeural(unittest.TestCase):

    def test_classificar_interesse(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"):
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"categoria":"interesse","confianca":0.92,"resumo":"Quer mais informacoes sobre o servico"}'
                    }
                }]
            }
            mock_requests.post.return_value = mock_resp

            resultado = agente_leitor_neural._classificar_com_nvidia(
                "Ola, estou interessado em mais informacoes sobre o servico.",
                "Re: Proposta ATLAS",
            )
            self.assertEqual(resultado["categoria"], "interesse")
            self.assertGreater(resultado["confianca"], 0.9)
            self.assertIn("mais informacoes", resultado["resumo"])

    def test_classificar_recusou(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"):
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"categoria":"recusou","confianca":0.97,"resumo":"Nao tem interesse no momento"}'
                    }
                }]
            }
            mock_requests.post.return_value = mock_resp

            resultado = agente_leitor_neural._classificar_com_nvidia(
                "Nao temos interesse no momento, por favor remova.",
                "Re: Proposta ATLAS",
            )
            self.assertEqual(resultado["categoria"], "recusou")

    def test_classificar_automatico(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"):
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"categoria":"automatico","confianca":0.99,"resumo":"Resposta automatica de fora de escritorio"}'
                    }
                }]
            }
            mock_requests.post.return_value = mock_resp

            resultado = agente_leitor_neural._classificar_com_nvidia(
                "Estarei ausente do escritorio ate o dia 20. Em caso de urgencia...",
                "Re: Proposta ATLAS",
            )
            self.assertEqual(resultado["categoria"], "automatico")

    def test_classificar_fallback_json_nao_parseavel(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"):
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": "Resposta: a clinica demonstrou interesse mas nao sei classificar"
                    }
                }]
            }
            mock_requests.post.return_value = mock_resp

            resultado = agente_leitor_neural._classificar_com_nvidia(
                "qualquer coisa...",
                "Re: Proposta ATLAS",
            )
            self.assertEqual(resultado["categoria"], "indefinido")

    def test_classificar_sem_key(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", ""):
            resultado = agente_leitor_neural._classificar_com_nvidia(
                "Ola, gostaria de saber mais.",
                "Re: Proposta ATLAS",
            )
            self.assertEqual(resultado["categoria"], "indefinido")
            self.assertEqual(resultado["confianca"], 0.0)

    def test_classificar_timeout(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"):
            mock_requests.post.side_effect = mock_requests.Timeout("Timeout simulado")
            resultado = agente_leitor_neural._classificar_com_nvidia(
                "mensagem qualquer",
                "Re: Proposta ATLAS",
            )
            self.assertEqual(resultado["categoria"], "indefinido")
            self.assertEqual(resultado["confianca"], 0.0)
            mock_requests.post.side_effect = None

    def test_classificar_status_nao_200(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"):
            mock_resp = MagicMock(status_code=500, text="Internal Server Error")
            mock_resp.json.side_effect = ValueError("no json")
            mock_requests.post.return_value = mock_resp
            resultado = agente_leitor_neural._classificar_com_nvidia(
                "qualquer texto",
                "Re: Proposta",
            )
            self.assertEqual(resultado["categoria"], "indefinido")

    def test_extrair_email_valido(self):
        self.assertEqual(
            agente_leitor_neural._extrair_email("Clinica Sorriso <clinica@sorriso.com.br>"),
            "clinica@sorriso.com.br",
        )
        self.assertEqual(agente_leitor_neural._extrair_email("sem email aqui"), "")


class TestLeitorNeuralIntegracao(unittest.TestCase):

    def test_rodar_fluxo_completo(self):
        with patch.object(agente_leitor_neural, "NVIDIA_KEY", "mock-key"), \
             patch.object(agente_leitor_neural, "buscar_emails") as mock_buscar, \
             patch.object(agente_leitor_neural, "supabase") as mock_supabase:
            mock_buscar.return_value = [
                {
                    "id": "msg001",
                    "remetente": "clinica@exemplo.com",
                    "destinatario": "atlas@meudominio.com",
                    "assunto": "Re: Proposta",
                    "corpo": "Estou interessado",
                }
            ]

            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": '{"categoria":"interesse","confianca":0.92,"resumo":"Quer mais informacoes"}'
                    }
                }]
            }
            mock_requests.post.return_value = mock_resp

            mock_result = MagicMock()
            mock_result.data = [
                {"id": "email-db-id", "clinica_id": "clinica-uuid", "destinatario": "atlas@meudominio.com"}
            ]
            mock_supabase.table().select().eq().eq().limit().execute.return_value = mock_result

            resultado = agente_leitor_neural.rodar()

            self.assertTrue(resultado["success"])
            self.assertEqual(resultado["data"]["processado"], 1)
            self.assertEqual(resultado["data"]["classificados"]["interesse"], 1)
            mock_supabase.table().update().eq().execute.assert_called()


if __name__ == "__main__":
    unittest.main()