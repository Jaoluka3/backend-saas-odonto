import os
import logging
import pickle
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = "gmail_token.pickle"
CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS", "credentials.json")


def _autenticar() -> Optional[Credentials]:
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
    creds = _autenticar()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds)


def buscar_emails(query: str = "", max_results: int = 10) -> list:
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
                .get(userId="me", id=msg["id"], format="metadata")
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detalhe.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "remetente": headers.get("From", ""),
                "destinatario": headers.get("To", ""),
                "assunto": headers.get("Subject", ""),
                "data": headers.get("Date", ""),
            })
        return emails
    except HttpError as e:
        logger.error(f"Erro Gmail API: {e}")
        return []


def verificar_respostas(clinica_nome: str = "") -> list:
    query = f"subject:clinica OR subject:odontologica OR subject:dentista"
    if clinica_nome:
        query += f" {clinica_nome}"
    return buscar_emails(query=query, max_results=20)


def contar_respostas() -> dict:
    emails = verificar_respostas()
    return {
        "total_emails_encontrados": len(emails),
        "emails": emails[:10],
    }
