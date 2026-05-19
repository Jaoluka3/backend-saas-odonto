import os
import time
import logging
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from supabase_client import supabase

load_dotenv()
logger = logging.getLogger(__name__)

NVIDIA_KEY = os.environ.get("NVIDIA_KEY")

SYSTEM_PROMPT = (
    "Voce e um vendedor especialista em tecnologia para clinicas odontologicas. "
    "Escreva uma mensagem curta e persuasiva oferecendo um bot de atendimento "
    "automatico no Telegram por R$297/mes. Mencione o nome da clinica. "
    "Maximo 4 linhas. Seja direto e profissional."
)


def gerar_mensagem(nome: str, cidade: str, avaliacao) -> str:
    """Gera mensagem personalizada via NVIDIA API com fallback."""
    if not NVIDIA_KEY:
        logger.warning("NVIDIA_KEY nao configurada, usando fallback")
        return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"

    # Protecao contra None no prompt
    avaliacao_str = str(avaliacao) if avaliacao is not None else "N/A"

    try:
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json={
                "model": "nvidia/nemotron-3-nano-30b-a3b",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Clinica: {nome}, "
                            f"Cidade: {cidade}, "
                            f"Avaliacao: {avaliacao_str}"
                        ),
                    },
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
        logger.warning(
            "NVIDIA retornou status %d para %s", resp.status_code, nome
        )
    except Exception as e:
        logger.error("NVIDIA falhou para %s: %s", nome, e)

    return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"


def rodar() -> int:
    """Contacta clinicas qualificadas com rate limiting."""
    if not supabase:
        logger.error("Supabase nao configurado")
        return 0

    try:
        result = (
            supabase.table("clinicas")
            .select("*")
            .eq("status", "qualificado")
            .execute()
        )
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
            mensagem = gerar_mensagem(
                c["nome"],
                c.get("cidade", ""),
                c.get("avaliacao_google"),
            )
            supabase.table("clinicas").update({
                "mensagem_enviada": mensagem,
                "status": "contactado",
                "data_contato": datetime.now(timezone.utc).isoformat(),
            }).eq("id", c["id"]).execute()
            contactadas += 1
            logger.info(
                "Mensagem enviada para %s: %s", c["nome"], mensagem[:50]
            )

            # Rate limiting: 1s entre chamadas NVIDIA
            time.sleep(1)
        except Exception as e:
            logger.error(
                "Erro ao contactar clinica %s: %s", c.get("id"), e
            )

    logger.info("Contato: %d clinicas contactadas", contactadas)
    return contactadas


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    rodar()
