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


def _add_colunas_se_necessario():
    """Tenta adicionar colunas que podem estar faltando (instagram etc).
    Usa psycopg2 se DATABASE_URL estiver configurado, ou tenta via RPC."""
    colunas_faltando = []
    try:
        result = supabase.table("clinicas").select("instagram").limit(1).execute()
    except Exception:
        colunas_faltando.append("instagram")
    if not colunas_faltando:
        return
    db_url = os.environ.get("DATABASE_URL") or ""
    if db_url:
        try:
            import psycopg2
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute("ALTER TABLE clinicas ADD COLUMN IF NOT EXISTS instagram text;")
            conn.commit()
            cur.close()
            conn.close()
            logger.info("Colunas adicionadas: %s", colunas_faltando)
        except Exception as e:
            logger.warning("Nao foi possivel adicionar colunas via psycopg2: %s", e)
    else:
        logger.info(
            "DATABASE_URL nao configurado — rode no SQL Editor do Supabase:\n"
            "ALTER TABLE clinicas ADD COLUMN IF NOT EXISTS instagram text;"
        )


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
    import re
    cidade_nome = cidade.split("/")[0].strip() or "Sao Paulo"
    end_clean = re.sub(r",\s*\d{5}-?\d{3}.*", "", endereco)
    end_clean = re.sub(r"\s*-\s*(SP|RJ|MG|BA|RS|PR|SC|PE|CE|GO|DF|AM|PA|MA|ES|RN|PB|AL|SE|MT|MS|RO|TO|AC|AP|RR).*", "", end_clean, flags=re.IGNORECASE)
    end_clean = end_clean.strip(" ,-")
    query = f"{end_clean}, {cidade_nome}, Brasil"

    for tentativa in [query, f"{end_clean}, Brasil", cidade_nome + ", Brasil"]:
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": tentativa, "format": "json", "limit": 1},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                dados = resp.json()
                if dados:
                    return float(dados[0]["lat"]), float(dados[0]["lon"])
        except requests.exceptions.Timeout:
            logger.error("Timeout: %s", tentativa[:60])
        except Exception as e:
            logger.error("Erro %s: %s", tentativa[:60], e)
    return None


def rodar(max_por_execucao: int = 30) -> dict:
    if not supabase:
        logger.warning("supabase nao inicializado")
        return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0}

    _add_colunas_se_necessario()

    try:
        result = (
            supabase.table("clinicas")
            .select("id,nome,endereco,cidade")
            .neq("status", "inativo")
            .execute()
        )
        clinicas_raw = result.data or []
    except Exception as e:
        logger.warning("Falha com neq, tentando sem filtro: %s", e)
        try:
            result = (
                supabase.table("clinicas")
                .select("id,nome,endereco,cidade")
                .execute()
            )
            clinicas_raw = result.data or []
        except Exception as e2:
            logger.error("Erro ao ler clinicas: %s", e2)
            return {"geocodificadas": 0, "sem_endereco": 0, "falhas": 0, "erro": str(e2)}

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
