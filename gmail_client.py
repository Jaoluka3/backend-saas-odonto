import base64
import os
import pickle
import re
import logging

logger = logging.getLogger(__name__)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.warning("Google API libraries nao instaladas - Gmail desabilitado")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = "gmail_token.pickle"
CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS", "credentials.json")


def _autenticar():
    if not GOOGLE_AVAILABLE:
        return None
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler token: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.error(f"Erro ao refresh token: {e}")
            creds = None

    if not creds and os.path.exists(CREDENTIALS_FILE):
        try:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        except Exception as e:
            logger.error(f"Erro auth Gmail: {e}")

    if creds:
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return creds


def _get_service():
    if not GOOGLE_AVAILABLE:
        return None
    creds = _autenticar()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds)


def _extrair_corpo(payload: dict) -> str:
    corpo = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                body_data = part.get("body", {}).get("data", "")
                if body_data:
                    try:
                        corpo = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                    except Exception:
                        corpo = ""
                break
    elif payload.get("mimeType") == "text/plain":
        body_data = payload.get("body", {}).get("data", "")
        if body_data:
            try:
                corpo = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
            except Exception:
                corpo = ""
    return corpo


def _sanitizar_corpo(texto: str, max_chars: int = 400) -> str:
    if not texto:
        return ""
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:max_chars]


def buscar_emails(query: str = "", max_results: int = 10) -> list:
    if not GOOGLE_AVAILABLE:
        return []
    service = _get_service()
    if not service:
        logger.warning("Gmail nao autenticado")
        return []

    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        emails = []
        for msg in messages[:max_results]:
            detalhe = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detalhe.get("payload", {}).get("headers", [])}
            corpo_bruto = _extrair_corpo(detalhe.get("payload", {}))
            corpo = _sanitizar_corpo(corpo_bruto)
            emails.append({
                "id": msg["id"],
                "remetente": headers.get("From", ""),
                "destinatario": headers.get("To", ""),
                "assunto": headers.get("Subject", ""),
                "data": headers.get("Date", ""),
                "corpo": corpo,
            })
        return emails
    except Exception as e:
        logger.error(f"Erro Gmail API: {e}")
        return []


def verificar_respostas(clinica_nome: str = "") -> list:
    query = "subject:clinica OR subject:odontologica OR subject:dentista"
    if clinica_nome:
        query += f" {clinica_nome}"
    return buscar_emails(query=query, max_results=20)


def contar_respostas() -> dict:
    emails = verificar_respostas()
    return {
        "total_emails_encontrados": len(emails),
        "emails": emails[:10],
    }
