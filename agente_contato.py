import os
import time
import logging
from datetime import datetime
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
NVIDIA_KEY = os.environ.get("NVIDIA_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SYSTEM_PROMPT = (
    "Voce e vendedor especialista em tecnologia para clinicas odontologicas. "
    "Escreva mensagem curta e persuasiva oferecendo bot de atendimento automatico "
    "no Telegram por R$297/mes. Mencione o nome da clinica. Maximo 4 linhas. "
    "Seja direto e profissional."
)


def gerar_mensagem(nome: str, cidade: str, avaliacao) -> str:
    """Gera mensagem personalizada via NVIDIA API com fallback."""
    if not NVIDIA_KEY:
        logger.warning("NVIDIA_KEY nao configurada, usando fallback")
        return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"

    try:
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json={
                "model": "nvidia/nemotron-3-nano-30b-a3b",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Clinica: {nome}, Cidade: {cidade}, Avaliacao: {avaliacao}"},
                ],
                "max_tokens": 150,
                "temperature": 0.7,
            },
            headers={
                "Authorization": f"Bearer {NVIDIA_KEY}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        logger.warning("NVIDIA retornou status %d para %s", resp.status_code, nome)
    except Exception as e:
        logger.error("NVIDIA falhou para %s: %s", nome, e)

    return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"


def rodar() -> int:
    """Contacta clinicas qualificadas com rate limiting."""
    if not supabase:
        logger.error("Supabase nao configurado")
        return 0

    try:
        result = supabase.table("clinicas").select("*").eq("status", "qualificado").execute()
        clinicas = result.data
    except Exception as e:
        logger.error("Erro ao ler clinicas qualificadas: %s", e)
        return 0

    if not clinicas:
        logger.info("Nenhuma clinica qualificada para contactar")
        return 0

    contactadas = 0
    for c in clinicas:
        try:
            mensagem = gerar_mensagem(c["nome"], c.get("cidade", ""), c.get("avaliacao_google"))
            supabase.table("clinicas").update({
                "mensagem_enviada": mensagem,
                "status": "contactado",
                "data_contato": datetime.now().isoformat(),
            }).eq("id", c["id"]).execute()
            contactadas += 1
            logger.info("Mensagem enviada para %s: %s", c["nome"], mensagem[:50])

            # Rate limiting: espera 1s entre chamadas para evitar bloqueio
            time.sleep(1)

        except Exception as e:
            logger.error("Erro ao contactar clinica %s: %s", c.get("id"), e)

    logger.info("Contato: %d clinicas contactadas", contactadas)
    return contactadas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rodar()
