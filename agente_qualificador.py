import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def rodar() -> dict:
    """Pontua clinicas novas e classifica como qualificado ou descartado."""
    if not supabase:
        logger.error("Supabase nao configurado")
        return {"qualificadas": 0, "descartadas": 0}

    try:
        result = supabase.table("clinicas").select("*").eq("status", "novo").execute()
        clinicas = result.data
    except Exception as e:
        logger.error("Erro ao ler clinicas: %s", e)
        return {"qualificadas": 0, "descartadas": 0}

    if not clinicas:
        logger.info("Nenhuma clinica nova para qualificar")
        return {"qualificadas": 0, "descartadas": 0}

    qualificadas = 0
    descartadas = 0

    for c in clinicas:
        try:
            score = 0
            if c.get("website"):
                score += 25
            if c.get("avaliacao_google") is not None and c["avaliacao_google"] >= 4.0:
                score += 25
            if c.get("telefone"):
                score += 25
            if c.get("num_avaliacoes") is not None and c["num_avaliacoes"] >= 30:
                score += 25

            novo_status = "qualificado" if score >= 50 else "descartado"

            supabase.table("clinicas").update({
                "score": score,
                "status": novo_status,
            }).eq("id", c["id"]).execute()

            if novo_status == "qualificado":
                qualificadas += 1
            else:
                descartadas += 1

        except Exception as e:
            logger.error("Erro ao qualificar clinica %s: %s", c.get("id"), e)

    logger.info("Qualificador: %d qualificadas, %d descartadas", qualificadas, descartadas)
    return {"qualificadas": qualificadas, "descartadas": descartadas}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rodar()
