import os
import re
import time
import logging
import requests
from supabase_client import supabase

logger = logging.getLogger(__name__)

EMAIL_CACHE = {}
CACHE_TTL = 3600

EMAILS_GENERICOS = {
    "noreply", "no-reply", "no_reply", "webmaster", "admin",
    "support", "suporte", "contato", "newsletter", "marketing",
    "vendas", "sac", "ouvidoria", "naoresponda", "nao-responda",
}

URL_CONTATO_PATTERNS = re.compile(
    r'href=["\']([^"\']*(?:contato|contact|fale[-_]?conosco|faleconosco|email)[^"\']*)["\']',
    re.IGNORECASE,
)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _email_valido(email: str) -> bool:
    local = email.split("@")[0].lower()
    dominio = email.split("@")[-1].lower()
    if local in EMAILS_GENERICOS:
        return False
    if any(dominio.endswith(sufixo) for sufixo in (".png", ".jpg", ".jpeg", ".gif", ".svg")):
        return False
    return True


def _extrair_email_html(html: str) -> str | None:
    encontrados = EMAIL_REGEX.findall(html)
    for e in encontrados:
        e = e.strip().lower()
        if _email_valido(e):
            return e
    return None


def _fetch_url(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code == 200:
            return resp.text
    except requests.RequestException:
        pass
    return None


def _normalizar_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/")


def _resolver_email_site(website: str) -> str | None:
    url = _normalizar_url(website)
    if not url:
        return None

    if url in EMAIL_CACHE:
        cache_age = time.time() - EMAIL_CACHE[url]["timestamp"]
        if cache_age < CACHE_TTL:
            return EMAIL_CACHE[url]["email"]
        del EMAIL_CACHE[url]

    html = _fetch_url(url)
    if html is None:
        EMAIL_CACHE[url] = {"email": None, "timestamp": time.time()}
        return None

    email = _extrair_email_html(html)
    if email:
        EMAIL_CACHE[url] = {"email": email, "timestamp": time.time()}
        return email

    links = URL_CONTATO_PATTERNS.findall(html)
    for link in links:
        if link.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            link = f"{parsed.scheme}://{parsed.netloc}{link}"
        elif not link.startswith("http"):
            link = url.rstrip("/") + "/" + link.lstrip("/")

        html2 = _fetch_url(link)
        if html2:
            email = _extrair_email_html(html2)
            if email:
                EMAIL_CACHE[url] = {"email": email, "timestamp": time.time()}
                return email

    EMAIL_CACHE[url] = {"email": None, "timestamp": time.time()}
    return None


def rodar() -> dict:
    if not supabase:
        logger.error("Supabase nao configurado")
        return {"resolvidos": 0, "sem_website": 0, "nao_encontrados": 0}

    try:
        result = (
            supabase.table("clinicas")
            .select("*")
            .eq("status", "qualificado")
            .execute()
        )
        clinicas = result.data or []
    except Exception as e:
        logger.error("Erro ao ler clinicas qualificadas: %s", e)
        return {"resolvidos": 0, "sem_website": 0, "nao_encontrados": 0}

    alvo = [c for c in clinicas if not c.get("email")]
    if not alvo:
        logger.info("Nenhuma clinica qualificada sem email para resolver")
        return {"resolvidos": 0, "sem_website": 0, "nao_encontrados": 0}

    logger.info("Resolvendo emails para %d clinicas...", len(alvo))
    resolvidos = 0
    sem_website = 0
    nao_encontrados = 0

    for c in alvo:
        website = (c.get("website") or "").strip()
        if not website:
            sem_website += 1
            logger.info("Sem website: %s", c["nome"])
            continue

        try:
            email = _resolver_email_site(website)
            if email:
                supabase.table("clinicas").update({"email": email}).eq("id", c["id"]).execute()
                resolvidos += 1
                logger.info("Email encontrado para %s: %s", c["nome"], email)
            else:
                nao_encontrados += 1
                logger.info("Email nao encontrado para %s (site: %s)", c["nome"], website)
        except Exception as e:
            nao_encontrados += 1
            logger.error("Erro ao resolver email de %s: %s", c["nome"], e)

        time.sleep(0.5)

    logger.info(
        "Resolver: %d resolvidos, %d sem website, %d nao encontrados",
        resolvidos, sem_website, nao_encontrados,
    )
    return {
        "resolvidos": resolvidos,
        "sem_website": sem_website,
        "nao_encontrados": nao_encontrados,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
