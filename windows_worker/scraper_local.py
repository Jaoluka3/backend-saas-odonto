#!/usr/bin/env python3
"""scraper_local.py — Worker Local de Prospeccao Odontologica (Windows + IP Residencial)

Stack: Python 3.12+, scrapling (StealthyFetcher + Camoufox), Playwright, Supabase.
Alvo: Google Maps — busca por "Clinica Odontologica" em Betim, MG.
Output: Upsert direto na tabela `clinicas` do Supabase.

AVISO: Google Maps pode exigir resolucao manual de CAPTCHA em headful mode.
       Para rodar visivel (debug): python scraper_local.py --visible
"""

import os
import re
import sys
import time
import json
import random
import argparse
import logging
from typing import Optional

# Reutiliza o singleton do supabase_client.py (evita DRY violation)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from supabase_client import supabase as _supabase  # NOQA

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scraper_local")

# ── Constantes ──────────────────────────────────────────────────────────────
CIDADE = "Betim, MG"
QUERY = "clinica odontologica"
URL_BASE = "https://www.google.com/maps/search/"
BATCH_SIZE = 20
MAX_SCROLLS = 50           # limite de seguranca contra loop infinito
SCROLL_TIMEOUT_S = 120     # timeout maximo para o scroll total
SCROLL_PAUSE_MS = (1800, 3200)      # (min, max) pausa entre scrolls (ms)
SCROLL_STEP_PX = (800, 1200)        # (min, max) pixels por scroll
SAME_HEIGHT_LIMIT = 3               # scrolls consecutivos sem mudanca = fim da lista
RETRY_FETCH = 3                     # tentativas de fetch em caso de erro
RETRY_BACKOFF = (5, 10, 15)         # backoff em segundos entre retries

# ── Selectores (baseados em atributos a11y, nunca em classes hasheadas) ─────
SEL_FEED = "div[role='feed']"
SEL_CARD = "div[role='article']"
SEL_NAME = "h3"                                   # titulo da clinica
SEL_NAME_FB = "span.fontHeadlineSmall"             # fallback 1
SEL_NAME_FB2 = "[aria-label]"                      # fallback 2 (o link tem aria-label com o nome)
SEL_STARS = "[aria-label*='estrela']"              # avaliacao (portugues)
SEL_STARS_EN = "[aria-label*='star']"              # avaliacao (ingles)
SEL_STARS_FB = "[aria-label*='Stars']"             # avaliacao (outro formato)
SEL_ADDRESS = "div[data-tooltip]"                  # endereco tem tooltip
SEL_ADDRESS_FB = "span[jsinstance]"                # fallback endereco
SEL_PHONE_BTN = "button[data-item-id*='phone']"    # botao de telefone
SEL_PHONE_LINK = "a[href^='tel:']"                 # link telefonico
SEL_WEBSITE = "a[rel*='noopener']"                 # link externo do site
SEL_LINK_EXTERNO = "a[data-value]"                 # link com data-value

# ── Telefone ────────────────────────────────────────────────────────────────
RE_DIGITOS = re.compile(r"\d")
RE_REMOVER_ESPECIAIS = re.compile(r"[^\d]")
RE_RATING = re.compile(r"([\d.,]+)")
RE_NUM_REVIEWS = re.compile(r"(\d[\d.,]*)\s*(?:avalia[cç][oõ]es|reviews|coment[aá]rios)", re.IGNORECASE)
RE_NUM_REVIEWS_PAREN = re.compile(r"\((\d[\d.,]*)\)")


# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE MAPS SCRAPER
# ═══════════════════════════════════════════════════════════════════════════════


class GoogleMapsScraper:
    """Scraper standalone que usa StealthyFetcher + Camoufox para bypass anti-bot."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._session: Optional[object] = None
        self._imports_ok = self._verificar_imports()

    # ── Verificacao de dependencias ──────────────────────────────────────

    def _verificar_imports(self) -> bool:
        try:
            from scrapling.fetchers import StealthySession  # NOQA
            return True
        except ImportError as e:
            logger.error(
                "scrapling nao encontrado. Instale: pip install 'scrapling[fetchers]' && scrapling install"
            )
            logger.error("Erro: %s", e)
            return False

    # ── Scroll humano no feed ────────────────────────────────────────────

    @staticmethod
    def _scroll_feed(page) -> None:
        """page_action do StealthyFetcher: scroll humano ate o fim do feed.
        Usa mouse.wheel + move para simular comportamento humano e evitar
        deteccao de scroll automatizado (scrollBy e facil de detectar).
        """
        from playwright.sync_api import Page  # NOQA

        feed = page.query_selector(SEL_FEED)
        if not feed:
            logger.warning("Feed (div[role='feed']) nao encontrado — tentando scroll na pagina inteira")

        last_height = 0
        same_count = 0
        start_time = time.monotonic()

        for i in range(1, MAX_SCROLLS + 1):
            # timeout global
            if time.monotonic() - start_time > SCROLL_TIMEOUT_S:
                logger.info("Timeout global de scroll atingido (%ds)", SCROLL_TIMEOUT_S)
                break

            # jitter: pausa irregular entre scrolls
            pause_ms = random.randint(*SCROLL_PAUSE_MS)
            step_px = random.randint(*SCROLL_STEP_PX)

            # scroll: mouse.wheel (mais humano que scrollBy)
            try:
                if feed:
                    # mover mouse para o centro do feed antes do scroll
                    box = feed.bounding_box()
                    if box:
                        page.mouse.move(
                            box["x"] + box["width"] / 2 + random.randint(-50, 50),
                            box["y"] + box["height"] / 2 + random.randint(-50, 50),
                        )
                    feed.evaluate(f"(el) => {{ el.scrollBy(0, {step_px}); }}")
                else:
                    page.evaluate(f"window.scrollBy(0, {step_px})")
            except Exception as e:
                logger.warning("Erro no scroll #%d: %s", i, e)

            # aguardar renderizacao + XHR
            page.wait_for_timeout(pause_ms)
            try:
                page.wait_for_selector(SEL_CARD, state="attached", timeout=3000)
            except Exception:
                pass  # pode nao ter novos cards ainda

            # verificar se a altura mudou
            try:
                if feed:
                    new_height = feed.evaluate("(el) => el.scrollHeight")
                else:
                    new_height = page.evaluate("() => document.body.scrollHeight")
            except Exception:
                new_height = last_height

            if new_height == last_height:
                same_count += 1
            else:
                same_count = 0

            if same_count >= SAME_HEIGHT_LIMIT:
                logger.info("Fim do scroll: %d rodadas sem mudanca de altura", same_count)
                break

            last_height = new_height

        logger.info("Scroll concluido apos %d iteracoes", min(i, MAX_SCROLLS) if 'i' in dir() else 0)

    # ── Navegacao + fetch ────────────────────────────────────────────────

    def buscar_por_cidade(self, cidade: str, query: str) -> list[dict]:
        """Retorna lista de dicts com dados extraidos do Google Maps."""
        if not self._imports_ok:
            return []

        from scrapling.fetchers import StealthySession  # NOQA

        url = f"{URL_BASE}{query.replace(' ', '+')}+{cidade.replace(', ', ',+')}"
        logger.info("Fazendo fetch: %s", url)

        for tentativa in range(1, RETRY_FETCH + 1):
            try:
                with StealthySession(
                    headless=self.headless,
                    solve_cloudflare=True,
                    block_ads=True,
                    timeout=90000,
                ) as session:
                    self._session = session

                    page = session.fetch(
                        url,
                        page_action=self._scroll_feed,
                        network_idle=True,
                        wait_selector=SEL_FEED,
                    )

                    dados = self._extrair_listings(page)
                    logger.info(
                        "Fetch #%d: %d clinicas extraidas de %s, %s",
                        tentativa, len(dados), cidade, query,
                    )
                    return dados

            except Exception as e:
                logger.error("Tentativa %d/%d falhou: %s", tentativa, RETRY_FETCH, e)
                if tentativa < RETRY_FETCH:
                    delay = RETRY_BACKOFF[min(tentativa - 1, len(RETRY_BACKOFF) - 1)]
                    logger.info("Aguardando %ds antes do retry...", delay)
                    time.sleep(delay)

        logger.error("Todas as %d tentativas de fetch falharam", RETRY_FETCH)
        return []

    # ── Extracao do DOM ──────────────────────────────────────────────────

    def _extrair_listings(self, page) -> list[dict]:
        """Parse do DOM apos o scroll completo. Cada card = 1 clinica."""
        cards = page.css(SEL_CARD)
        logger.info("Encontrados %d cards (div[role='article'])", len(cards))

        if not cards:
            logger.warning("Nenhum card encontrado. Salvando HTML para debug...")
            self._salvar_debug_html(page, "sem_cards")
            return []

        dados: list[dict] = []
        visto: set[tuple] = set()  # dedup in-memory

        for i, card in enumerate(cards, 1):
            try:
                clinica = self._extrair_dados_card(card)
                if clinica is None:
                    continue

                # dedup: usa nome+telefone, mas se telefone=None usa nome+endereco
                tel = clinica.get("telefone") or ""
                end = clinica.get("endereco") or ""
                chave = (clinica["nome"].lower().strip(), tel if tel else end.lower().strip())
                if chave in visto:
                    continue
                visto.add(chave)

                dados.append(clinica)
            except Exception as e:
                logger.warning("Erro ao extrair card #%d: %s", i, e)
                continue

        logger.info("Extraidos %d registros unicos (de %d cards)", len(dados), len(cards))
        return dados

    # ── Extracao de um card individual ───────────────────────────────────

    def _extrair_dados_card(self, card) -> Optional[dict]:
        """Extrai nome, telefone, endereco, website, avaliacao de um card."""

        # Nome
        nome = None
        for sel in (SEL_NAME, SEL_NAME_FB):
            el = card.css(sel)
            if el:
                nome = (el[0].text or "").strip()
                break
        if not nome:
            # tentar aria-label do link
            el = card.css(SEL_NAME_FB2)
            if el:
                nome = (el[0].attrib.get("aria-label") or "").strip()
        if not nome or len(nome) < 3:
            return None  # descartar cards sem nome valido

        # Avaliacao Google
        avaliacao = None
        for sel in (SEL_STARS, SEL_STARS_EN, SEL_STARS_FB):
            el = card.css(sel)
            if el:
                raw = (el[0].text or el[0].attrib.get("aria-label") or "")
                m = RE_RATING.search(raw)
                if m:
                    try:
                        avaliacao = float(m.group(1).replace(",", "."))
                    except ValueError:
                        pass
                    break

        # Numero de avaliacoes
        num_avaliacoes = None
        texto_card = (card.text or "")
        m = RE_NUM_REVIEWS.search(texto_card)
        if m:
            num_avaliacoes = int(m.group(1).replace(",", "").replace(".", ""))
        else:
            m = RE_NUM_REVIEWS_PAREN.search(texto_card)
            if m:
                num_avaliacoes = int(m.group(1).replace(",", "").replace(".", ""))

        # Endereco
        endereco = None
        for sel in (SEL_ADDRESS, SEL_ADDRESS_FB):
            el = card.css(sel)
            if el:
                endereco = (el[0].text or el[0].attrib.get("aria-label") or "").strip()
                if endereco:
                    break

        # Telefone
        telefone_raw = None
        for sel in (SEL_PHONE_BTN, SEL_PHONE_LINK):
            el = card.css(sel)
            if el:
                if sel == SEL_PHONE_LINK:
                    telefone_raw = el[0].attrib.get("href", "")
                    telefone_raw = telefone_raw.removeprefix("tel:")
                else:
                    telefone_raw = el[0].text or el[0].attrib.get("data-phone-number") or el[0].attrib.get("aria-label") or ""
                if telefone_raw:
                    break

        if not telefone_raw:
            # fallback: scannear texto do card por padrao de telefone
            telefone_raw = self._extrair_telefone_por_regex(texto_card)

        telefone = self._normalizar_telefone(telefone_raw) if telefone_raw else None
        if not telefone or len(telefone) < 8:
            telefone = None

        # Website
        website = None
        for sel in (SEL_WEBSITE, SEL_LINK_EXTERNO):
            el = card.css(sel)
            if el:
                href = el[0].attrib.get("href") or el[0].attrib.get("data-value") or ""
                if href and "google" not in href.lower() and "maps" not in href.lower():
                    website = href.strip()
                    break

        return {
            "nome": nome,
            "telefone": telefone,
            "endereco": endereco or "",
            "website": website or "",
            "avaliacao_google": avaliacao,
            "num_avaliacoes": num_avaliacoes,
            "cidade": CIDADE,
            "status": "novo",
        }

    # ── Normalizacao ─────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_telefone(raw: str) -> str:
        """Remove tudo que nao for digito."""
        return RE_REMOVER_ESPECIAIS.sub("", raw)

    @staticmethod
    def _extrair_telefone_por_regex(texto: str) -> Optional[str]:
        """Tenta encontrar padrao de telefone brasileiro no texto."""
        # (XX) XXXXX-XXXX ou (XX) XXXX-XXXX
        padrao = re.compile(r"(?:\(\d{2}\)\s?\d{4,5}[-\s]?\d{4})")
        m = padrao.search(texto)
        if m:
            return m.group(0)
        return None

    @staticmethod
    def _salvar_debug_html(page, prefixo: str) -> None:
        """Salva HTML da pagina para debug em caso de falha na extracao."""
        try:
            html = page.content
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            fname = f"debug_{prefixo}_{timestamp}.html"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("HTML salvo para debug: %s (%d bytes)", fname, len(html))
        except Exception as e:
            logger.warning("Nao foi possivel salvar HTML de debug: %s", e)

    # ── Cleanup ──────────────────────────────────────────────────────────

    def fechar(self) -> None:
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None


# ═══════════════════════════════════════════════════════════════════════════════
# SUPABASE INJECTOR
# ═══════════════════════════════════════════════════════════════════════════════


class SupabaseInjector:
    """Gerencia upsert em batch na tabela clinicas."""

    @staticmethod
    def upsert_batch(dados: list[dict]) -> int:
        """Insere dados em batches de BATCH_SIZE com upsert on_conflict='telefone'.
        Upsert INDIVIDUAL (1 registro por chamada) para evitar erro 21000
        do PostgreSQL quando ha telefones duplicados no batch.
        """
        if not _supabase:
            logger.error("Supabase nao configurado — dados NAO foram salvos")
            return 0

        if not dados:
            logger.info("Lista vazia — nada para inserir")
            return 0

        inseridos = 0
        falhas = 0
        total = len(dados)

        for i in range(0, total, BATCH_SIZE):
            batch = dados[i : i + BATCH_SIZE]
            for registro in batch:
                try:
                    _supabase.table("clinicas").upsert(
                        registro, on_conflict="telefone"
                    ).execute()
                    inseridos += 1
                except Exception as e:
                    logger.error(
                        "Erro upsert: %s (tel: %s): %s",
                        registro.get("nome", "?"),
                        registro.get("telefone", "?"),
                        str(e)[:120],
                    )
                    falhas += 1
                    time.sleep(0.3)  # rate limit minimo

            logger.info(
                "Progresso: %d/%d inseridos (%d falhas)",
                inseridos, total, falhas,
            )

        logger.info("Batch concluido: %d inseridos, %d falhas", inseridos, falhas)
        return inseridos


# ═══════════════════════════════════════════════════════════════════════════════
# ORQUESTRADOR
# ═══════════════════════════════════════════════════════════════════════════════


def rodar(headless: bool = True) -> dict:
    """Orquestra o ciclo completo: scrape -> upsert -> relatorio."""
    resultado = {
        "cidade": CIDADE,
        "query": QUERY,
        "extraidos": 0,
        "inseridos": 0,
        "falhas": 0,
        "inicio": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    inicio = time.monotonic()

    scraper = GoogleMapsScraper(headless=headless)
    try:
        dados = scraper.buscar_por_cidade(CIDADE, QUERY)
        resultado["extraidos"] = len(dados)

        if dados:
            inseridos = SupabaseInjector.upsert_batch(dados)
            resultado["inseridos"] = inseridos
            resultado["falhas"] = len(dados) - inseridos
        else:
            logger.warning("Nenhum dado extraido — pulando upsert")
    finally:
        scraper.fechar()

    duracao = time.monotonic() - inicio
    resultado["duracao_s"] = round(duracao, 1)
    resultado["fim"] = time.strftime("%Y-%m-%d %H:%M:%S")

    logger.info("=== RESUMO ===")
    logger.info("Cidade: %s | Query: %s", resultado["cidade"], resultado["query"])
    logger.info("Extraidos: %d | Inseridos: %d | Falhas: %d", resultado["extraidos"], resultado["inseridos"], resultado["falhas"])
    logger.info("Duracao: %.1fs", duracao)
    return resultado


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Local — Google Maps → Supabase")
    parser.add_argument(
        "--visible",
        action="store_false",
        dest="headless",
        default=True,
        help="Executa com navegador visivel (modo debug)",
    )
    parser.add_argument(
        "--salvar-json",
        action="store_true",
        default=False,
        help="Salva dados extraidos em JSON local antes do upsert",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        default=False,
        help="Apenas extrai e salva JSON (nao faz upsert no Supabase)",
    )
    args = parser.parse_args()

    if args.json_only:
        logger.info("Modo JSON-only: sem injecao no Supabase")
        scraper = GoogleMapsScraper(headless=args.headless)
        try:
            dados = scraper.buscar_por_cidade(CIDADE, QUERY)
            if dados and args.salvar_json:
                fname = f"clinicas_{time.strftime('%Y%m%d_%H%M%S')}.json"
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                logger.info("Dados salvos em %s (%d registros)", fname, len(dados))
            else:
                print(json.dumps(dados, ensure_ascii=False, indent=2))
        finally:
            scraper.fechar()
    else:
        resultado = rodar(headless=args.headless)
        if args.salvar_json:
            fname = f"relatorio_{time.strftime('%Y%m%d_%H%M%S')}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            logger.info("Relatorio salvo em %s", fname)