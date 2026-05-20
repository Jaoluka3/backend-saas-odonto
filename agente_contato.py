import os
import re
import time
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import requests
from supabase_client import supabase

logger = logging.getLogger(__name__)

GMAIL_EMAIL = os.environ.get("GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NVIDIA_KEY = os.environ.get("NVIDIA_KEY")

SYSTEM_PROMPT = (
    "Voce e um vendedor especialista em tecnologia para clinicas odontologicas. "
    "Escreva uma mensagem curta e persuasiva oferecendo um bot de atendimento "
    "automatico no Telegram por R$297/mes. Mencione o nome da clinica. "
    "Maximo 4 linhas. Seja direto e profissional."
)

TEMPLATE_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
<p>Prezada equipe da <strong>{nome}</strong>,</p>
<p>Sou o <strong>Bleckson</strong>, fundador da <strong>ATLAS</strong> — plataforma de atendimento inteligente para clínicas odontológicas.</p>
<p>Nosso sistema funciona 24h no Telegram, automatizando:</p>
<ul>
  <li>Agendamento de consultas</li>
  <li>Respostas a perguntas frequentes</li>
  <li>Captação de novos pacientes</li>
</ul>
<p>A {nome} já tem {avaliacao}★ no Google — imagine converter ainda mais leads em consultas reais.</p>
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


def gerar_assunto(nome: str) -> str:
    return f"Automatize o atendimento da {nome} com IA"


def smtp_disponivel() -> bool:
    return bool(GMAIL_EMAIL and GMAIL_APP_PASSWORD)


def enviar_email_smtp(destinatario: str, assunto: str, corpo_html: str, corpo_txt: str) -> bool:
    if not smtp_disponivel():
        logger.error("Credenciais SMTP nao configuradas (GMAIL_EMAIL / GMAIL_APP_PASSWORD)")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_EMAIL
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo_txt, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        logger.info("Email enviado para %s", destinatario)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Falha de autenticacao SMTP para %s. Verifique GMAIL_APP_PASSWORD.", destinatario)
        return False
    except smtplib.SMTPException as e:
        logger.error("Erro SMTP ao enviar para %s: %s", destinatario, e)
        return False
    except Exception as e:
        logger.error("Erro inesperado ao enviar email para %s: %s", destinatario, e)
        return False


def gerar_mensagem(nome: str, cidade: str, avaliacao) -> str:
    if not NVIDIA_KEY:
        return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"

    avaliacao_str = str(avaliacao) if avaliacao is not None else "N/A"

    try:
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json={
                "model": "nvidia/nemotron-3-nano-30b-a3b",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Clinica: {nome}, "
                            f"Cidade: {cidade}, "
                            f"Avaliacao: {avaliacao_str}"
                        ),
                    },
                ],
                "max_tokens": 150,
                "temperature": 0.7,
            },
            headers={
                "Authorization": f"Bearer {NVIDIA_KEY}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        logger.warning("NVIDIA retornou status %d para %s", resp.status_code, nome)
    except Exception as e:
        logger.error("NVIDIA falhou para %s: %s", nome, e)

    return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"


def _formatar_avaliacao(valor) -> str:
    if valor is None:
        return "N/A"
    try:
        return f"{float(valor):.1f}"
    except (ValueError, TypeError):
        return str(valor)


def registrar_email_db(clinica_id: str, destinatario: str, assunto: str, corpo: str) -> bool:
    if not supabase:
        return False
    try:
        supabase.table("emails").insert({
            "clinica_id": clinica_id,
            "remetente": GMAIL_EMAIL,
            "destinatario": destinatario,
            "assunto": assunto,
            "corpo": corpo,
            "status": "enviado",
            "data_envio": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error("Erro ao registrar email no DB: %s", e)
        return False


def rodar() -> int:
    if not supabase:
        logger.error("Supabase nao configurado")
        return 0

    if not smtp_disponivel():
        logger.warning("SMTP nao configurado — pulando envio real")

    try:
        result = (
            supabase.table("clinicas")
            .select("*")
            .eq("status", "qualificado")
            .execute()
        )
        clinicas = [
            c for c in (result.data or [])
            if c.get("email")
        ]
    except Exception as e:
        logger.error("Erro ao ler clinicas qualificadas com email: %s", e)
        return 0

    if not clinicas:
        logger.info("Nenhuma clinica qualificada com email para contactar")
        return 0

    contactadas = 0
    for c in clinicas:
        try:
            nome = c["nome"]
            email = c["email"]
            avaliacao = _formatar_avaliacao(c.get("avaliacao_google"))
            assunto = gerar_assunto(nome)

            corpo_html = TEMPLATE_HTML.format(nome=nome, avaliacao=avaliacao)
            corpo_txt = TEMPLATE_TXT.format(nome=nome, avaliacao=avaliacao)

            if smtp_disponivel():
                enviado = enviar_email_smtp(email, assunto, corpo_html, corpo_txt)
            else:
                enviado = True

            supabase.table("clinicas").update({
                "mensagem_enviada": assunto,
                "status": "contactado",
                "data_contato": datetime.now(timezone.utc).isoformat(),
            }).eq("id", c["id"]).execute()

            registrar_email_db(c["id"], email, assunto, corpo_html)

            contactadas += 1
            logger.info("Email processado para %s (%s): %s", nome, email, assunto)

            time.sleep(20)
        except Exception as e:
            logger.error("Erro ao contactar clinica %s: %s", c.get("id"), e)

    logger.info("Contato: %d emails processados", contactadas)
    return contactadas


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
