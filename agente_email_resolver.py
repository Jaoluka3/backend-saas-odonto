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
    "comercial", "financeiro", "rh", "ti", "tecnologia",
}

URL_CONTATO_PATTERNS = re.compile(
    r'href=["\']([^"\']*(?:contato|contact|fale[-_]?conosco|faleconosco|email)[^"\']*)["\']',
    re.IGNORECASE,
)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

COMMON_PATHS = [
    "/contato", "/contact", "/fale-conosco", "/faleconosco",
    "/quem-somos", "/sobre", "/sobre-nos", "/institucional",
    "/email", "/atendimento", "/onde-estamos",
    "/localizacao", "/unidade", "/unidades",
]

ALIASES_PADRAO = [
    "contato", "atendimento", "sac", "adm", "comercial",
    "clinica", "recepcionista", "secretaria",
    "diretoria", "administracao",
]

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
        resp = requests.get(url, timeout=8, headers=HEADERS, allow_redirects=True)
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


def _resolver_email_site(website: str, nome: str = "", cidade: str = "") -> str | None:
    url = _normalizar_url(website)
    if not url:
        return None

    if url in EMAIL_CACHE:
        cache_age = time.time() - EMAIL_CACHE[url]["timestamp"]
        if cache_age < CACHE_TTL:
            return EMAIL_CACHE[url]["email"]
        del EMAIL_CACHE[url]

    # Camada 1: homepage
    html = _fetch_url(url)
    if html:
        email = _extrair_email_html(html)
        if email:
            EMAIL_CACHE[url] = {"email": email, "timestamp": time.time()}
            return email

        # Camada 2: paths comuns de contato (mesmo sem link explicito no HTML)
        from urllib.parse import urlparse
        parsed = urlparse(url)
        for path in COMMON_PATHS:
            link = f"{parsed.scheme}://{parsed.netloc}{path}"
            html2 = _fetch_url(link)
            if html2:
                email = _extrair_email_html(html2)
                if email:
                    EMAIL_CACHE[url] = {"email": email, "timestamp": time.time()}
                    return email

        # Camada 3: links de contato encontrados no HTML
        links = URL_CONTATO_PATTERNS.findall(html)
        for link in links:
            if link.startswith("/"):
                link = f"{parsed.scheme}://{parsed.netloc}{link}"
            elif not link.startswith("http"):
                link = url.rstrip("/") + "/" + link.lstrip("/")

            html3 = _fetch_url(link)
            if html3:
                email = _extrair_email_html(html3)
                if email:
                    EMAIL_CACHE[url] = {"email": email, "timestamp": time.time()}
                    return email

    # Camada 4: domain alias guessing — comum em clinicas brasileiras
    # Ex: contato@dominio.com.br, atendimento@dominio.com.br
    email = _tentar_aliases(url)
    if email:
        EMAIL_CACHE[url] = {"email": email, "timestamp": time.time()}
        return email

    EMAIL_CACHE[url] = {"email": None, "timestamp": time.time()}
    return None


def _tentar_aliases(url: str) -> str | None:
    """Tenta emails comuns baseados no dominio."""
    from urllib.parse import urlparse
    dominio = urlparse(url).netloc.lower()
    if dominio.startswith("www."):
        dominio = dominio[4:]
    for alias in ALIASES_PADRAO:
        email = f"{alias}@{dominio}"
        if _email_valido(email):
            return email
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

    MAX_POR_EXECUCAO = 30
    alvo = alvo[:MAX_POR_EXECUCAO]
    logger.info("Resolvendo emails para %d clinicas (max %d)...", len(alvo), MAX_POR_EXECUCAO)
    resolvidos = 0
    sem_website = 0
    nao_encontrados = 0
    por_alias = 0

    for c in alvo:
        website = (c.get("website") or "").strip()
        nome = c.get("nome", "")

        if not website:
            sem_website += 1
            continue

        try:
            email = _resolver_email_site(website)
            if email:
                supabase.table("clinicas").update({"email": email}).eq("id", c["id"]).execute()
                resolvidos += 1
                logger.info("Email encontrado para %s: %s", nome, email)
            else:
                nao_encontrados += 1
        except Exception as e:
            nao_encontrados += 1
            logger.error("Erro ao resolver email de %s: %s", nome, e)

        time.sleep(0.2)

    logger.info(
        "Resolver: %d resolvidos (%d por alias), %d sem website, %d nao encontrados",
        resolvidos, por_alias, sem_website, nao_encontrados,
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
