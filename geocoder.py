import os
import json
import time
import logging
import requests
from supabase_client import supabase

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "ATLAS-Prospeccao/2.0 (blecksonbra@gmail.com)"
}
ARQUIVO_COORDENADAS = "/tmp/coordenadas.json"


def _carregar_coordenadas() -> dict:
    if not os.path.exists(ARQUIVO_COORDENADAS):
        return {}
    try:
        with open(ARQUIVO_COORDENADAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_coordenadas(coords: dict):
    with open(ARQUIVO_COORDENADAS, "w", encoding="utf-8") as f:
        json.dump(coords, f, ensure_ascii=False, indent=2)


def obter_coordenadas() -> dict:
    """Retorna dicionario {id_clinica: {"lat": x, "lng": y}}."""
    return _carregar_coordenadas()


def geocodificar_endereco(endereco: str, cidade: str = "") -> tuple[float, float] | None:
    query = f"{endereco}, {cidade}, Brasil" if cidade else f"{endereco}, Brasil"

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            dados = resp.json()
            if dados:
                lat = float(dados[0]["lat"])
                lon = float(dados[0]["lon"])
                return lat, lon
            else:
                logger.warning("Nominatim sem resultados: %s", query[:80])
        else:
            logger.warning("Nominatim status %s: %s", resp.status_code, query[:80])
    except requests.exceptions.Timeout:
        logger.error("Timeout Nominatim: %s", query[:80])
    except Exception as e:
        logger.error("Erro Nominatim para %s: %s", query[:60], e)

    return None


def rodar(max_por_execucao: int = 5) -> dict:
    if not supabase:
        logger.warning("supabase nao inicializado")
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0}

    try:
        result = (
            supabase.table("clinicas")
            .select("id,nome,endereco,cidade")
            .execute()
        )
        clinicas_raw = result.data or []
    except Exception as e:
        logger.error("Erro ao ler clinicas: %s", e)
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0, "erro": str(e)}

    logger.info("Geocoder: %d clinicas lidas do banco", len(clinicas_raw))

    ja_feitas = _carregar_coordenadas()
    alvo = [c for c in clinicas_raw if c.get("endereco") and str(c["id"]) not in ja_feitas]
    if not alvo:
        logger.info("Nenhuma clinica sem coordenadas encontrada.")
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0}

    alvo = alvo[:max_por_execucao]
    logger.info("Geocodificando %d clinicas...", len(alvo))

    geocodificadas = 0
    falhas = 0

    for c in alvo:
        endereco = (c.get("endereco") or "").strip()
        cidade = (c.get("cidade") or "").strip()

        try:
            coords = geocodificar_endereco(endereco, cidade)
            if coords:
                lat, lon = coords
                ja_feitas[str(c["id"])] = {"lat": lat, "lng": lon}
                geocodificadas += 1
                logger.info("Coordenadas para clinica %s: %.4f, %.4f", c["nome"], lat, lon)
            else:
                falhas += 1
        except Exception as e:
            falhas += 1
            logger.error("Erro ao geocodificar %s: %s", c["nome"], e)

        time.sleep(1.1)

    _salvar_coordenadas(ja_feitas)

    logger.info(
        "Geocoder: %d geocodificadas, %d falhas",
        geocodificadas, falhas,
    )
    return {
        "geocodificadas": geocodificadas,
        "sem_endereco": 0,
        "falhas": falhas,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
