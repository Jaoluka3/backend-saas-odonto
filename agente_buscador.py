import os
import time
import logging
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

# Buscas mais especificas para maximizar resultados (cidade + bairros)
BUSCAS = [
    "clinica odontologica Sao Paulo",
    "clinica odontologica Rio de Janeiro",
    "clinica odontologica Belo Horizonte",
    "clinica odontologica Curitiba",
    "clinica odontologica Brasilia",
    "dentista Sao Paulo",
    "dentista Rio de Janeiro",
    "odontologia Belo Horizonte",
]

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _buscar_com_retry(busca: str, tentativas: int = 3) -> list:
    """Busca na SerpApi com retry exponencial em caso de falha."""
    for tentativa in range(1, tentativas + 1):
        try:
            params = {
                "engine": "google_maps",
                "q": busca,
                "api_key": SERPAPI_KEY,
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("local_results", [])
        except Exception as e:
            logger.warning("Tentativa %d falhou para '%s': %s", tentativa, busca, e)
            if tentativa < tentativas:
                time.sleep(2 ** tentativa)  # backoff exponencial
    return []


def rodar() -> int:
    """Busca clinicas e faz batch insert com upsert para evitar duplicatas."""
    if not supabase:
        logger.error("Supabase nao configurado")
        return 0
    if not SERPAPI_KEY:
        logger.error("SERPAPI_KEY nao configurada")
        return 0

    todas_clinicas = []
    for busca in BUSCAS:
        logger.info("Buscando: %s", busca)
        resultados = _buscar_com_retry(busca)
        logger.info("Encontrados %d resultados para '%s'", len(resultados), busca)

        for r in resultados:
            telefone = (r.get("phone") or "").strip()
            nome = (r.get("title") or "").strip()
            if not telefone or not nome:
                continue

            todas_clinicas.append({
                "nome": nome,
                "telefone": telefone,
                "endereco": (r.get("address") or "").strip(),
                "website": (r.get("website") or "").strip(),
                "avaliacao_google": r.get("rating"),
                "num_avaliacoes": r.get("reviews"),
                "cidade": busca.split()[-1],  # ultima palavra da busca
                "status": "novo",
            })

    if not todas_clinicas:
        logger.info("Nenhuma clinica encontrada")
        return 0

    # Batch insert com upsert (on_conflict no telefone)
    try:
        supabase.table("clinicas").upsert(
            todas_clinicas,
            on_conflict="telefone",
        ).execute()
        logger.info("Batch insert: %d clinicas processadas", len(todas_clinicas))
    except Exception as e:
        logger.error("Erro no batch insert: %s", e)
        return 0

    return len(todas_clinicas)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rodar()
