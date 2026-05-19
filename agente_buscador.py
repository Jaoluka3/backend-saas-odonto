import os
import time
import logging
import requests
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
if not SERPAPI_KEY:
    raise SystemExit("Erro: SERPAPI_KEY nao definida nas variaveis de ambiente. O agente buscador nao pode funcionar sem ela.")

logger = logging.getLogger(__name__)

# --- Parametros hiperlocal fixos (Betim/MG, CEP 32673-306) ---
QUERY_FIXA = "clinica odontologica Betim MG CEP 32673306"
LL_PARAM = "@-19.9703184,-44.2064950,14z"
HL_PARAM = "pt-BR"
GL_PARAM = "br"
MAX_LEADS = 10


def _buscar_hiperlocal() -> list:
    """Faz uma unica requisicao a SerpAPI Google Maps com escopo hiperlocal.

    Regras:
      - Nenhuma iteracao sobre cidades.
      - Nenhuma paginacao recursiva (apenas start=0).
      - time.sleep(10) antes da requisicao para respeitar free tier.
      - Se HTTP 429, loga e retorna lista vazia sem derrubar a aplicacao.
      - Retorna no maximo MAX_LEADS (10) resultados.
    """
    time.sleep(10)  # Rate limiter: respeita free tier (~100 req/mes)

    params = {
        "engine": "google_maps",
        "type": "search",
        "q": QUERY_FIXA,
        "ll": LL_PARAM,
        "hl": HL_PARAM,
        "gl": GL_PARAM,
        "start": 0,
        "api_key": SERPAPI_KEY,
    }

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=30,
        )

        if resp.status_code == 429:
            logger.error(
                "ERRO 429: Limite da SerpAPI excedido. "
                "Retornando lista vazia."
            )
            return []

        resp.raise_for_status()
        dados = resp.json()

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        logger.error(
            "ERRO HTTP %s na requisicao SerpAPI: %s. "
            "Retornando lista vazia.",
            status, e,
        )
        return []
    except requests.exceptions.ConnectionError as e:
        logger.error(
            "ERRO de conexao SerpAPI: %s. Retornando lista vazia.", e
        )
        return []
    except requests.exceptions.Timeout as e:
        logger.error(
            "TIMEOUT na requisicao SerpAPI: %s. Retornando lista vazia.", e
        )
        return []
    except Exception as e:
        logger.error(
            "ERRO inesperado na requisicao SerpAPI: %s. Retornando lista vazia.", e
        )
        return []

    resultados = dados.get("local_results", [])[:MAX_LEADS]
    logger.info(
        "SerpAPI retornou %d resultados (limitado a %d)",
        len(resultados), MAX_LEADS,
    )
    return resultados


def rodar() -> int:
    """Busca clinicas odontologicas em Betim/MG e faz batch upsert no Supabase."""
    if not supabase:
        logger.error("Supabase nao configurado")
        return 0
    logger.info("Buscando clinicas em Betim/MG (CEP 32673-306)...")
    resultados = _buscar_hiperlocal()
    logger.info("Encontrados %d resultados", len(resultados))

    leads = []
    for r in resultados:
        telefone = (r.get("phone") or "").strip()
        nome = (r.get("title") or "").strip()
        if not telefone or not nome:
            continue

        leads.append({
            "nome": nome,
            "telefone": telefone,
            "endereco": (r.get("address") or "").strip(),
            "website": (r.get("website") or "").strip(),
            "avaliacao_google": r.get("rating"),
            "num_avaliacoes": r.get("reviews"),
            "cidade": "Betim",
            "status": "novo",
        })

    if not leads:
        logger.info("Nenhum lead valido encontrado")
        return 0

    # Batch upsert: unica chamada ao Supabase em vez de row-by-row
    try:
        resp = supabase.table("clinicas").upsert(
            leads, on_conflict="telefone"
        ).execute()
        inseridas = len(leads)
        logger.info("Batch upsert concluido: %d clinicas inseridas/atualizadas", inseridas)
    except Exception as e:
        logger.error("Erro no batch upsert: %s. Tentando fallback row-by-row...", e)
        inseridas = 0
        for lead in leads:
            try:
                supabase.table("clinicas").upsert(
                    lead, on_conflict="telefone"
                ).execute()
                inseridas += 1
            except Exception as e2:
                logger.error(
                    "Erro ao inserir %s (%s): %s",
                    lead["nome"], lead["telefone"], e2,
                )
        logger.info("Fallback concluido: inseridas %d/%d", inseridas, len(leads))

    return inseridas


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
