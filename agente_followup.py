import time
import logging
from datetime import datetime
import os
import requests
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()
logger = logging.getLogger(__name__)

NVIDIA_KEY = os.environ.get("NVIDIA_KEY")


def gerar_followup(nome: str, tentativa: int) -> str:
    """Gera mensagem de follow-up via NVIDIA API com fallback."""
    if tentativa == 1:
        prompt = (
            "Ainda temos interesse em ajudar a clinica a automatizar "
            "o atendimento. Seja educado e reforce os beneficios."
        )
    else:
        prompt = (
            "Ultima tentativa de contato. Seja educado mas deixe claro "
            "que e a ultima oportunidade. Ofereca um desconto de 30% "
            "no primeiro mes."
        )

    if not NVIDIA_KEY:
        return (
            f"Follow-up {tentativa}: Ola {nome}, ainda temos interesse!"
        )

    try:
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json={
                "model": "nvidia/nemotron-3-nano-30b-a3b",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Clinica: {nome}"},
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
    except Exception as e:
        logger.error("NVIDIA falhou no followup de %s: %s", nome, e)

    return (
        f"Follow-up {tentativa}: Ola {nome}, ainda temos interesse em ajudar!"
    )


def rodar() -> dict:
    """Gerencia follow-ups automaticos baseado no tempo desde contato."""
    if not supabase:
        logger.error("Supabase nao configurado")
        return {"followups_enviados": 0, "inativados": 0}

    try:
        result = (
            supabase.table("clinicas")
            .select("*")
            .eq("status", "contactado")
            .execute()
        )
        clinicas = result.data
    except Exception as e:
        logger.error("Erro ao ler clinicas contactadas: %s", e)
        return {"followups_enviados": 0, "inativados": 0}

    if not clinicas:
        logger.info("Nenhuma clinica contactada para followup")
        return {"followups_enviados": 0, "inativados": 0}

    hoje = datetime.now()
    followups = 0
    inativados = 0

    for c in clinicas:
        try:
            # Protecao: se data_contato for None, pula
            data_contato_str = c.get("data_contato")
            if not data_contato_str:
                logger.warning(
                    "Clinica %s sem data_contato, pulando", c.get("id")
                )
                continue

            data_contato = datetime.fromisoformat(data_contato_str)
            dias = (hoje - data_contato).days
            nf = c.get("numero_followups", 0) or 0

            if dias >= 14 and nf >= 2:
                supabase.table("clinicas").update({
                    "status": "inativo",
                }).eq("id", c["id"]).execute()
                inativados += 1
                logger.info(
                    "Inativado: %s (%d dias sem resposta)", c["nome"], dias
                )
            elif dias >= 7 and nf == 1:
                msg = gerar_followup(c["nome"], 2)
                supabase.table("clinicas").update({
                    "numero_followups": 2,
                    "mensagem_enviada": msg,
                }).eq("id", c["id"]).execute()
                followups += 1
                logger.info("Followup 2 para %s", c["nome"])
                time.sleep(1)
            elif dias >= 3 and nf == 0:
                msg = gerar_followup(c["nome"], 1)
                supabase.table("clinicas").update({
                    "numero_followups": 1,
                    "mensagem_enviada": msg,
                }).eq("id", c["id"]).execute()
                followups += 1
                logger.info("Followup 1 para %s", c["nome"])
                time.sleep(1)
        except Exception as e:
            logger.error(
                "Erro no followup de %s: %s", c.get("id"), e
            )

    logger.info(
        "Followup: %d enviados, %d inativados", followups, inativados
    )
    return {"followups_enviados": followups, "inativados": inativados}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
