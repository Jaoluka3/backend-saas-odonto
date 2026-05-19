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

# Mapping explicito de cidades para evitar "Janeiro" em vez de "Rio de Janeiro"
CIDADES_CONHECIDAS = [
    "Sao Paulo", "Rio de Janeiro", "Belo Horizonte",
    "Curitiba", "Brasilia", "Salvador", "Fortaleza",
    "Manaus", "Recife", "Porto Alegre", "Campinas",
    "Santos", "Niteroi", "Goiania", "Guarulhos",
]

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


def extrair_cidade(busca: str) -> str:
    """Extrai o nome correto da cidade a partir da string de busca."""
    for cidade in CIDADES_CONHECIDAS:
        if cidade.lower() in busca.lower():
            return cidade
    # fallback: ultimo termo (evita substrings parciais)
    return busca.split()[-1]


def _buscar_com_retry(busca: str, tentativas: int = 3) -> list:
    """Busca na SerpApi com retry exponencial e paginacao."""
    resultados: list = []  # fallback se todas as tentativas falharem
    for tentativa in range(1, tentativas + 1):
        try:
            resultados = []
            start = 0
            while True:
                params = {
                    "engine": "google_maps",
                    "q": busca,
                    "api_key": SERPAPI_KEY,
                    "start": start,
                }
                resp = requests.get(
                    "https://serpapi.com/search",
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                pagina = data.get("local_results", [])
                resultados.extend(pagina)

                # Parar se nao houver mais paginas
                if len(pagina) < 20:
                    break
                start += 20
        except Exception as e:
            logger.warning(
                "Tentativa %d falhou para '%s': %s", tentativa, busca, e
            )
            if tentativa < tentativas:
                time.sleep(2**tentativa)
    return resultados


def rodar() -> int:
    """Busca clinicas e faz batch upsert para evitar duplicatas."""
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

        cidade = extrair_cidade(busca)
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
                "cidade": cidade,
                "status": "novo",
            })

    if not todas_clinicas:
        logger.info("Nenhuma clinica encontrada")
        return 0

    inseridas = 0
    for c in todas_clinicas:
        try:
            supabase.table("clinicas").upsert(
                c, on_conflict="telefone"
            ).execute()
            inseridas += 1
        except Exception as e:
            logger.error(
                "Erro ao inserir %s (%s): %s",
                c["nome"], c["telefone"], e,
            )
    logger.info("Inseridas %d/%d clinicas", inseridas, len(todas_clinicas))
    return inseridas


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
