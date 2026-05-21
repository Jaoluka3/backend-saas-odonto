#!/usr/bin/env python3
"""geocoder.py — Geocodificacao de enderecos via Nominatim (OpenStreetMap).

Busca clinicas sem coordenadas (latitude/longitude) na tabela `clinicas` do
Supabase, geocodifica via Nominatim e faz update direto no banco.

NAO depende de arquivos JSON temporarios — 100% Supabase.
"""

import logging
import time
import requests
from supabase_client import supabase

logger = logging.getLogger(__name__)

# ── Nominatim ────────────────────────────────────────────────────────────────
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MAX_POR_EXECUCAO = 50
DELAY_ENTRE_REQUISICOES = 2  # segundos — respeitar policy da Nominatim (max 1 req/s)
USER_AGENT = "DentalSaaS/1.0 (contato@seusite.com)"


def geocodificar_endereco(endereco: str) -> dict:
    """Geocodifica um endereco via Nominatim com retry em caso de 429.

    Retorna dict com 'latitude' e 'longitude' (ambos float ou None).
    """
    dados: dict = {"latitude": None, "longitude": None}

    if not endereco or len(endereco.strip()) < 10:
        return dados

    params = {
        "q": endereco.strip(),
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": USER_AGENT}

    for tentativa in range(1, 4):
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params=params,
                headers=headers,
                timeout=15,
            )

            # Rate limit 429 — respeitar Retry-After
            if resp.status_code == 429:
                delay = int(resp.headers.get("Retry-After", 10))
                logger.warning(
                    "Rate limit 429 (tentativa %d): aguardando %ds...",
                    tentativa, delay,
                )
                time.sleep(delay)
                continue

            resp.raise_for_status()
            data = resp.json()

            if data:
                dados["latitude"] = float(data[0]["lat"])
                dados["longitude"] = float(data[0]["lon"])

            return dados

        except requests.exceptions.Timeout:
            logger.warning(
                "Timeout ao geocodificar '%s' (tentativa %d)",
                endereco[:50], tentativa,
            )
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            logger.error(
                "Erro de rede ao geocodificar '%s' (tentativa %d): %s",
                endereco[:50], tentativa, e,
            )
            time.sleep(2)
        except (ValueError, TypeError, IndexError) as e:
            logger.error(
                "Erro ao parsear resposta para '%s': %s",
                endereco[:50], e,
            )
            return dados

    return dados


def rodar() -> int:
    """Busca clinicas sem coordenadas e faz geocodificacao + update.

    Returns:
        int: numero de clinicas atualizadas com sucesso.
    """
    if not supabase:
        logger.error("Supabase nao configurado — abortando")
        return 0

    # Buscar clinicas sem coordenadas (latitude IS NULL)
    try:
        result = (
            supabase.table("clinicas")
            .select("id", "endereco")
            .is_("latitude", "null")
            .limit(MAX_POR_EXECUCAO)
            .execute()
        )
    except Exception as e:
        logger.error("Erro ao buscar clinicas sem coordenadas: %s", e)
        return 0

    clinicas = result.data or []
    logger.info("%d clinicas sem coordenadas encontradas", len(clinicas))

    if not clinicas:
        logger.info("Nada para geocodificar")
        return 0

    atualizadas = 0
    falhas = 0

    for i, c in enumerate(clinicas, 1):
        endereco = c.get("endereco", "")
        if not endereco or len(endereco.strip()) < 10:
            logger.debug("Pulando %s: endereco muito curto", c["id"])
            continue

        coords = geocodificar_endereco(endereco)

        if coords["latitude"] is None or coords["longitude"] is None:
            falhas += 1
            logger.warning(
                "[%d/%d] Falha ao geocodificar: %s",
                i, len(clinicas), endereco[:60],
            )
            time.sleep(DELAY_ENTRE_REQUISICOES)
            continue

        # Update direto no Supabase
        try:
            supabase.table("clinicas").update({
                "latitude": coords["latitude"],
                "longitude": coords["longitude"],
            }).eq("id", c["id"]).execute()
            atualizadas += 1
            logger.info(
                "[%d/%d] OK: %s → (%.5f, %.5f)",
                i, len(clinicas), endereco[:40],
                coords["latitude"], coords["longitude"],
            )
        except Exception as e:
            falhas += 1
            logger.error(
                "[%d/%d] Erro ao atualizar %s: %s",
                i, len(clinicas), c["id"], e,
            )

        # Respeitar rate limit da Nominatim
        time.sleep(DELAY_ENTRE_REQUISICOES)

    logger.info(
        "Geocodificacao concluida: %d atualizadas, %d falhas (de %d total)",
        atualizadas, falhas, len(clinicas),
    )
    return atualizadas


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    rodar()