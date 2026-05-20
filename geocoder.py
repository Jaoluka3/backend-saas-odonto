import os
import time
import logging
import requests
from supabase_client import supabase

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "ATLAS-Prospeccao/2.0 (blecksonbra@gmail.com)"
}

COLUNAS_GEO = ["latitude", "longitude"]

def _add_colunas_geo():
    """Tenta adicionar colunas latitude/longitude na tabela clinicas."""
    try:
        import psycopg2
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or ""
        if not db_url:
            logger.warning("DATABASE_URL nao configurado - nao e possivel adicionar colunas")
            return False
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        for col in ["latitude double precision", "longitude double precision"]:
            try:
                cur.execute(f"ALTER TABLE clinicas ADD COLUMN IF NOT EXISTS {col}")
            except Exception:
                pass
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Colunas latitude/longitude adicionadas com sucesso")
        return True
    except ImportError:
        logger.warning("psycopg2 nao instalado - nao e possivel adicionar colunas")
        return False
    except Exception as e:
        logger.warning("Falha ao adicionar colunas: %s", e)
        return False


def geocodificar_endereco(endereco: str, cidade: str = "") -> tuple[float, float] | None:
    query = f"{endereco}, {cidade}, Brasil" if cidade else f"{endereco}, Brasil"

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            dados = resp.json()
            if dados:
                lat = float(dados[0]["lat"])
                lon = float(dados[0]["lon"])
                return lat, lon
    except Exception as e:
        logger.error("Erro Nominatim para %s: %s", query[:60], e)

    return None


def rodar(max_por_execucao: int = 30) -> dict:
    if not supabase:
        logger.warning("supabase nao inicializado")
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0}

    try:
        try:
            result = (
                supabase.table("clinicas")
                .select("id,nome,endereco,cidade,latitude,longitude")
                .execute()
            )
            clinicas_raw = result.data or []
        except Exception:
            logger.info("Colunas latitude/longitude nao existem, tentando criar...")
            _add_colunas_geo()
            result = (
                supabase.table("clinicas")
                .select("id,nome,endereco,cidade,latitude,longitude")
                .execute()
            )
            clinicas_raw = result.data or []
    except Exception as e:
        logger.error("Erro ao ler clinicas: %s", e)
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0, "erro": str(e)}

    logger.info("Geocoder: %d clinicas lidas do banco", len(clinicas_raw))
    sem_end = [c for c in clinicas_raw if not c.get("endereco")]
    com_lat = [c for c in clinicas_raw if c.get("latitude")]
    com_status = [c.get("status") for c in clinicas_raw[:5]]
    alvo = [c for c in clinicas_raw if not c.get("latitude") and c.get("endereco")]
    sem_campo = [c for c in clinicas_raw if "latitude" not in c or "endereco" not in c]
    logger.info(
        "Geocoder debug: total=%d, sem_end=%d, com_lat=%d, alvo=%d, sem_campo=%d, status_amostra=%s",
        len(clinicas_raw), len(sem_end), len(com_lat), len(alvo), len(sem_campo), str(com_status),
    )
    if not alvo:
        logger.info("Nenhuma clinica sem coordenadas encontrada.")
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0}

    alvo = alvo[:max_por_execucao]
    logger.info("Geocodificando %d clinicas...", len(alvo))

    geocodificadas = 0
    sem_endereco = 0
    falhas = 0

    for c in alvo:
        endereco = (c.get("endereco") or "").strip()
        cidade = (c.get("cidade") or "").strip()

        if not endereco:
            sem_endereco += 1
            continue

        try:
            coords = geocodificar_endereco(endereco, cidade)
            if coords:
                lat, lon = coords
                supabase.table("clinicas").update({
                    "latitude": lat,
                    "longitude": lon,
                }).eq("id", c["id"]).execute()
                geocodificadas += 1
                logger.info("Coordenadas para %s: %.4f, %.4f", c["nome"], lat, lon)
            else:
                falhas += 1
        except Exception as e:
            falhas += 1
            logger.error("Erro ao geocodificar %s: %s", c["nome"], e)

        time.sleep(1.1)

    logger.info(
        "Geocoder: %d geocodificadas, %d sem endereco, %d falhas",
        geocodificadas, sem_endereco, falhas,
    )
    return {
        "geocodificadas": geocodificadas,
        "sem_endereco": sem_endereco,
        "falhas": falhas,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
