import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from supabase_client import supabase
from gmail_client import buscar_emails

logger = logging.getLogger(__name__)

NVIDIA_KEY = os.environ.get("NVIDIA_KEY", "")

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "nvidia/nemotron-3-nano-30b-a3b"
NVIDIA_TIMEOUT = 10

CATEGORIAS_VALIDAS = {"interesse", "agendamento", "recusou", "automatico", "indefinido"}

SYSTEM_PROMPT = (
    "You are a classifier for dental clinic email replies in Portuguese. "
    "Classify the email into one of the following categories and return ONLY a JSON object "
    'with keys: "categoria" (one of: interesse, agendamento, recusou, automatico, indefinido), '
    '"confianca" (0-1 float), "resumo" (short 50-char excerpt in Portuguese). '
    "If the email is clearly an out-of-office auto-reply or bounce, use automatico. "
    "If nothing can be understood, use indefinido. "
    'Return ONLY valid JSON, no markdown, no explanation.'
)

ultima_leitura: Optional[str] = None
ultimo_resultado_leitura: dict = {}


def _extrair_email(texto: str) -> str:
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", texto)
    return match.group(0).lower() if match else ""


def _classificar_com_nvidia(corpo: str, assunto: str) -> dict:
    if not NVIDIA_KEY:
        logger.warning("NVIDIA_KEY nao configurada — usando indefinido")
        return {"categoria": "indefinido", "confianca": 0.0, "resumo": assunto[:50]}

    user_message = f"Assunto: {assunto}\nCorpo: {corpo}"

    try:
        resp = requests.post(
            NVIDIA_URL,
            json={
                "model": NVIDIA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 200,
                "temperature": 0,
            },
            headers={
                "Authorization": f"Bearer {NVIDIA_KEY}",
                "Content-Type": "application/json",
            },
            timeout=NVIDIA_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.error("NVIDIA retornou %d: %s", resp.status_code, resp.text[:200])
            return {"categoria": "indefinido", "confianca": 0.0, "resumo": assunto[:50]}

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        content = content.strip()

        if content.startswith("```"):
            content = re.sub(r"```\w*\n?", "", content)
            content = content.replace("```", "")

        try:
            resultado = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[^}]+\}", content)
            if match:
                try:
                    resultado = json.loads(match.group(0))
                except json.JSONDecodeError:
                    logger.warning("JSON nao parseavel da NVIDIA: %s", content[:200])
                    return {"categoria": "indefinido", "confianca": 0.0, "resumo": assunto[:50]}
            else:
                logger.warning("JSON nao encontrado na resposta NVIDIA: %s", content[:200])
                return {"categoria": "indefinido", "confianca": 0.0, "resumo": assunto[:50]}

        categoria = resultado.get("categoria", "indefinido")
        if categoria not in CATEGORIAS_VALIDAS:
            categoria = "indefinido"

        confianca = resultado.get("confianca", 0.0)
        try:
            confianca = float(confianca)
        except (ValueError, TypeError):
            confianca = 0.0

        resumo = resultado.get("resumo", assunto[:50])
        if not isinstance(resumo, str):
            resumo = str(resumo)

        return {"categoria": categoria, "confianca": confianca, "resumo": resumo[:50]}

    except requests.Timeout:
        logger.warning("Timeout NVIDIA ao classificar email")
        return {"categoria": "indefinido", "confianca": 0.0, "resumo": assunto[:50]}
    except Exception as e:
        logger.error("NVIDIA falhou: %s", e)
        return {"categoria": "indefinido", "confianca": 0.0, "resumo": assunto[:50]}


def _emparelhar_clinica(destinatario: str, remetente: str) -> Optional[dict]:
    if not supabase:
        return None
    try:
        result = (
            supabase.table("emails")
            .select("id, clinica_id, destinatario")
            .eq("destinatario", destinatario)
            .eq("respondeu", False)
            .limit(1)
            .execute()
        )
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        logger.error("Erro ao emparelhar clinica: %s", e)
        return None


def _atualizar_status(clinica_id: str, email_id: str, categoria: str, resumo: str) -> None:
    if not supabase:
        return

    mapa_status_email = {
        "interesse": "respondido",
        "agendamento": "respondido",
        "recusou": "recusado",
        "automatico": "automatico",
        "indefinido": "indefinido",
    }
    status_email = mapa_status_email.get(categoria, "indefinido")
    respondeu = categoria not in ("automatico", "indefinido")

    try:
        supabase.table("emails").update({
            "status": status_email,
            "data_resposta": datetime.now(timezone.utc).isoformat(),
            "respondeu": respondeu,
        }).eq("id", email_id).execute()

        mapa_status_clinica = {
            "interesse": None,
            "agendamento": "cliente",
            "recusou": "inativo",
            "automatico": None,
            "indefinido": None,
        }
        novo_status = mapa_status_clinica.get(categoria)
        if novo_status:
            supabase.table("clinicas").update({
                "status": novo_status,
            }).eq("id", clinica_id).execute()
            logger.info("Clinica %s -> status %s (categoria: %s)", clinica_id, novo_status, categoria)

        logger.info(
            "Email %s classificado: %s (confianca: ver log) | resumo: %s",
            email_id, categoria, resumo[:50],
        )
    except Exception as e:
        logger.error("Erro ao atualizar status para email %s: %s", email_id, e)


def rodar() -> dict:
    global ultima_leitura, ultimo_resultado_leitura
    inicio = datetime.now(timezone.utc)

    if not supabase:
        logger.error("Supabase nao configurado")
        return {"success": False, "error": "Supabase nao configurado"}

    query = "in:inbox is:unread"
    try:
        emails = buscar_emails(query=query, max_results=50)
    except Exception as e:
        logger.error("Erro ao buscar emails: %s", e)
        return {"success": False, "error": str(e)}

    if not emails:
        logger.info("Nenhum email nao lido encontrado")
        ultima_leitura = inicio.isoformat()
        ultimo_resultado_leitura = {"processado": 0, "classificados": {}, "erros": []}
        return {"success": True, "data": ultimo_resultado_leitura}

    logger.info("Processando %d emails nao lidos...", len(emails))

    classificados = {c: 0 for c in CATEGORIAS_VALIDAS}
    processado = 0
    erros = []

    for email in emails:
        try:
            destinatario = _extrair_email(email.get("destinatario", ""))
            remetente = _extrair_email(email.get("remetente", ""))
            assunto = email.get("assunto", "")
            corpo = email.get("corpo", "")

            if not destinatario:
                logger.debug("Email %s sem destinatario extraivel, ignorando", email.get("id"))
                continue

            pareado = _emparelhar_clinica(destinatario, remetente)
            if not pareado:
                logger.debug(
                    "Email %s (dest: %s) nao emparelhou com nenhuma clinica",
                    email.get("id"), destinatario,
                )
                continue

            clinica_id = pareado.get("clinica_id")
            email_db_id = pareado.get("id")
            if not clinica_id or not email_db_id:
                continue

            classificacao = _classificar_com_nvidia(corpo, assunto)
            categoria = classificacao["categoria"]
            confianca = classificacao["confianca"]
            resumo = classificacao["resumo"]

            logger.info(
                "Email %s -> %s (%.2f): %s",
                email.get("id"), categoria, confianca, resumo,
            )

            _atualizar_status(clinica_id, email_db_id, categoria, resumo)

            classificados[categoria] += 1
            processado += 1
        except Exception as e:
            msg = f"Email {email.get('id', '?')}: {e}"
            logger.exception(msg)
            erros.append(msg)

    duracao = round((datetime.now(timezone.utc) - inicio).total_seconds(), 2)
    resultado = {
        "processado": processado,
        "classificados": classificados,
        "erros": erros,
        "duracao_segundos": duracao,
    }

    logger.info(
        "Leitor neural concluido: %d processados, %s, %d erros, %ss",
        processado, classificados, len(erros), duracao,
    )

    ultima_leitura = inicio.isoformat()
    ultimo_resultado_leitura = resultado
    return {"success": True, "data": resultado}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    resultado = rodar()
    print(json.dumps(resultado, indent=2, ensure_ascii=False))