#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Daemon SMTP Local – Worker Windows

Objetivo
---------
* Pollar o Supabase a cada 5 min (300 s) em busca de clinicas:
    status == 'qualificado'  AND  email IS NOT NULL
* Enviar o e-mail de prospeccao via Gmail (SMTP)
* Atualizar o registro da clinica para status 'contactado' e
  registrar o envio na tabela `emails`
* Logar erros e garantir que o loop nunca termine inesperadamente

Requisitos de ambiente (variaveis .env)
---------------------------------------
SUPABASE_URL          - URL do Supabase
SUPABASE_KEY          - Chave anon do Supabase
GMAIL_EMAIL           - Conta Gmail que enviara os e-mails
GMAIL_APP_PASSWORD    - App-password da conta Gmail (2-FA habilitado)

O daemon deve ser executado em uma maquina Windows que possua acesso
a internet (porta 587/465 liberada).  Nao ha necessidade de
qualquer outra configuracao.
"""

import os
import time
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Carrega .env antes de qualquer import que dependa dele
from dotenv import load_dotenv
load_dotenv()

# ----------------------------------------------------------------------
# Configuracoes
# ----------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

MAX_POR_CICLO = 15          # numero maximo de clinicas por varredura
INTERVALO_SEGUNDOS = 300    # 5 minutos

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("daemon_smtp_local")

# ----------------------------------------------------------------------
# Supabase client (reutiliza o modulo ja existente)
# ----------------------------------------------------------------------
try:
    from supabase_client import supabase
except Exception as e:
    log.error("Supabase client nao carregado: %s", e)
    supabase = None

# ----------------------------------------------------------------------
# Templates de e-mail (mesmo conteudo de agente_contato.py)
# ----------------------------------------------------------------------
TEMPLATE_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
<p>Prezada equipe da <strong>{nome}</strong>,</p>
<p>Sou o <strong>Bleckson</strong>, fundador da <strong>ATLAS</strong> — plataforma de atendimento inteligente para clinicas odontologicas.</p>
<p>Nosso sistema funciona 24h no Telegram, automatizando:</p>
<ul>
  <li>Agendamento de consultas</li>
  <li>Respostas a perguntas frequentes</li>
  <li>Captacao de novos pacientes</li>
</ul>
<p>A {nome} ja tem {avaliacao}* no Google — imagine converter ainda mais leads em consultas reais.</p>
<p>Quer ver funcionando? Responda este e-mail ou acesse meu site:<br>
<a href="https://backend-saas-odonto.onrender.com/painel">https://backend-saas-odonto.onrender.com/painel</a></p>
<p>Atenciosamente,<br>
<strong>Bleckson</strong><br>
ATLAS — Atendimento Inteligente</p>
</body>
</html>"""

TEMPLATE_TXT = """\
Prezada equipe da {nome},

Sou o Bleckson, fundador da ATLAS -- plataforma de atendimento inteligente para clinicas odontologicas.

Nosso sistema funciona 24h no Telegram, automatizando:
* Agendamento de consultas
* Respostas a perguntas frequentes
* Captacao de novos pacientes

A {nome} ja tem {avaliacao}* no Google -- imagine converter ainda mais leads em consultas reais.

Quer ver funcionando? Responda este e-mail ou acesse:
https://backend-saas-odonto.onrender.com/painel

Atenciosamente,
Bleckson
ATLAS -- Atendimento Inteligente
"""


# ----------------------------------------------------------------------
# Funcoes auxiliares
# ----------------------------------------------------------------------
def _formatar_avaliacao(valor) -> str:
    """Mantem o mesmo comportamento de agente_contato."""
    if valor is None:
        return "N/A"
    try:
        return f"{float(valor):.1f}"
    except (ValueError, TypeError):
        return str(valor)


def _enviar_email(destinatario: str, assunto: str, html_body: str, txt_body: str) -> bool:
    """
    Envia o e-mail via Gmail SMTP.
    Tenta porta 587 (STARTTLS) e, em caso de falha, porta 465 (SSL).
    Retorna True em caso de sucesso, False caso contrario.
    """
    if not all([GMAIL_EMAIL, GMAIL_APP_PASSWORD]):
        log.error("Credenciais SMTP nao configuradas (GMAIL_EMAIL / GMAIL_APP_PASSWORD)")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_EMAIL
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(txt_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Primeiro tenta STARTTLS (porta 587), depois SSL (porta 465)
    for porta, usar_ssl in [(587, False), (465, True)]:
        try:
            if usar_ssl:
                server = smtplib.SMTP_SSL("smtp.gmail.com", porta, timeout=30)
            else:
                server = smtplib.SMTP("smtp.gmail.com", porta, timeout=30)
                server.ehlo()
                server.starttls()
                server.ehlo()

            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
            server.quit()
            log.info("Email enviado para %s (porta %d)", destinatario, porta)
            return True
        except smtplib.SMTPAuthenticationError:
            log.error("Falha de autenticacao SMTP (porta %d). Verifique GMAIL_APP_PASSWORD.", porta)
            return False
        except Exception as exc:
            log.warning("SMTP porta %d falhou: %s - tentando proxima porta", porta, exc)

    log.error("Todas as tentativas de envio SMTP falharam para %s", destinatario)
    return False


def _processar_ciclo() -> None:
    """
    Executa uma iteracao do daemon:
    1. Busca ate MAX_POR_CICLO clinicas qualificadas com e-mail.
    2. Envia o e-mail.
    3. Atualiza o status da clinica e registra o envio na tabela `emails`.
    """
    if supabase is None:
        log.error("Supabase nao esta configurado - abortando ciclo.")
        return

    try:
        resp = (
            supabase.table("clinicas")
            .select("*")
            .eq("status", "qualificado")
            .not_.is_("email", "null")
            .limit(MAX_POR_CICLO)
            .execute()
        )
        clinicas = resp.data or []
    except Exception as exc:
        log.error("Erro ao consultar Supabase: %s", exc)
        return

    if not clinicas:
        log.info("Nenhuma clinica qualificada com e-mail encontrada neste ciclo.")
        return

    for clinica in clinicas:
        try:
            nome = clinica.get("nome", "Clinica")
            avaliacao = _formatar_avaliacao(clinica.get("avaliacao_google"))
            email_dest = clinica.get("email")
            if not email_dest:
                log.warning("Clinica %s nao possui e-mail - pulando.", clinica.get("id"))
                continue

            assunto = f"Automatize o atendimento da {nome} com IA"
            html_body = TEMPLATE_HTML.format(nome=nome, avaliacao=avaliacao)
            txt_body = TEMPLATE_TXT.format(nome=nome, avaliacao=avaliacao)

            enviado = _enviar_email(email_dest, assunto, html_body, txt_body)

            if enviado:
                agora = datetime.utcnow().isoformat()

                # 1. Atualiza status da clinica
                supabase.table("clinicas").update(
                    {
                        "status": "contactado",
                        "data_contato": agora,
                    }
                ).eq("id", clinica["id"]).execute()

                # 2. Insere registro na tabela `emails`
                supabase.table("emails").insert({
                    "clinica_id": clinica["id"],
                    "remetente": GMAIL_EMAIL,
                    "destinatario": email_dest,
                    "assunto": assunto,
                    "corpo": html_body,
                    "status": "enviado",
                    "data_envio": agora,
                }).execute()

                log.info("Processado com sucesso: clinica %s (id=%s)", nome, clinica["id"])
            else:
                log.error("Falha ao enviar e-mail para %s (id=%s)", nome, clinica["id"])

        except Exception as exc:
            # Garantia de que o loop nao quebra por excecao inesperada
            log.exception("Erro inesperado ao processar clinica %s: %s", clinica.get("id"), exc)
            continue


def main() -> None:
    log.info("=== Daemon SMTP Local iniciado ===")
    log.info("Supabase URL: %s", SUPABASE_URL)
    log.info("Polling a cada %d segundos (max %d clinicas por ciclo)", INTERVALO_SEGUNDOS, MAX_POR_CICLO)

    while True:
        try:
            _processar_ciclo()
        except Exception as exc:
            # Captura qualquer erro que vaze da funcao interna
            log.exception("Erro critico no ciclo do daemon: %s", exc)
        finally:
            time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    main()
