import os
import time
import logging
import requests
import telebot
from supabase_client import supabase

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DE LOGS
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CARREGAR .ENV MANUALMENTE
# ─────────────────────────────────────────────
def _load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


_load_env()


# ─────────────────────────────────────────────
# VARIÁVEIS DE AMBIENTE
# ─────────────────────────────────────────────
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
NVIDIA_KEY = os.environ.get("NVIDIA_KEY", "")
API_URL = os.environ.get(
    "API_URL", "https://backend-saas-odonto.onrender.com"
)

if not TOKEN:
    raise SystemExit(
        "ERRO: Variável TELEGRAM_BOT_TOKEN não configurada. "
        "Defina-a no arquivo .env ou nas variáveis de ambiente."
    )

if not NVIDIA_KEY:
    logger.warning(
        "ATENÇÃO: NVIDIA_KEY não configurada! "
        "Bot responderá apenas com mensagem padrão. "
        "Configure NVIDIA_KEY no Render."
    )


# ─────────────────────────────────────────────
# INICIALIZAR BOT
# ─────────────────────────────────────────────
bot = telebot.TeleBot(TOKEN)


# ─────────────────────────────────────────────
# SYSTEM PROMPT DA ALEX
# ─────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Você é a Alex, recepcionista e vendedora de elite de uma clínica odontológica.\n"
    "Seu objetivo é ser educada, tirar dúvidas e converter leads em agendamentos reais.\n"
    "Seja sempre simpática, profissional e persuasiva. "
    "Use linguagem natural e calorosa.\n"
    "Caso o paciente demonstre interesse em agendar ou aceitar um horário, "
    "adicione a tag [AGENDAR] no final da sua resposta."
)


# ─────────────────────────────────────────────
# GERAÇÃO DE RESPOSTA VIA NVIDIA API
# ─────────────────────────────────────────────
def gerar_resposta_ia(user_text: str, first_name: str) -> str:
    nvidia_key = os.environ.get("NVIDIA_KEY", "")
    if not nvidia_key:
        logger.warning("NVIDIA_KEY ausente — usando resposta padrão.")
        return f"Olá {first_name}! Sou a Alex. Como posso ajudar?"

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {nvidia_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "nvidia/nemotron-3-nano-30b-a3b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Nome: {first_name}\nMensagem: {user_text}"},
        ],
        "max_tokens": 500,
        "temperature": 0.7,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            logger.error(
                f"NVIDIA retornou {response.status_code}: {response.text[:200]}"
            )
    except Exception as e:
        logger.error(f"NVIDIA falhou: {e}")

    return f"Olá {first_name}! Sou a Alex. Como posso ajudar?"


# ─────────────────────────────────────────────
# SALVAR LEAD NO SUPABASE
# ─────────────────────────────────────────────
# TABELA leads: pacientes do bot Telegram
# TABELA clinicas: clínicas prospectadas pelos agentes (buscador, contato, followup, qualificador)
# NÃO misturar — propósitos diferentes.
# ─────────────────────────────────────────────
def salvar_lead(nome, telefone, status):
    for tentativa in range(3):
        try:
            supabase.table("leads").upsert({
                "nome": nome,
                "telefone": str(telefone),
                "status": status,
            }, on_conflict="telefone").execute()
            logger.info(f"Lead salvo: {nome} - {status}")
            return
        except Exception as e:
            logger.error(
                f"Erro ao salvar lead "
                f"(tentativa {tentativa+1}/3): {e}"
            )
            if tentativa < 2:
                time.sleep(2)
    logger.error(f"Falha total ao salvar lead: {nome}")


# ─────────────────────────────────────────────
# HANDLER DE CONTATO (COMPARTILHAR TELEFONE)
# ─────────────────────────────────────────────
@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    chat_id = message.chat.id
    first_name = (
        message.from_user.first_name or "Paciente"
    ).strip()

    if message.contact and message.contact.phone_number:
        telefone_real = message.contact.phone_number
        try:
            supabase.table("leads").upsert({
                "nome": first_name,
                "telefone": telefone_real,
                "status": "agendado"
            }, on_conflict="telefone").execute()

            supabase.table("leads").delete().eq(
                "telefone", str(chat_id)
            ).execute()

            logger.info(
                f"Contato real recebido: "
                f"{first_name} - {telefone_real}"
            )
        except Exception as e:
            logger.error(f"Erro ao salvar contato: {e}")

        bot.reply_to(
            message,
            f"Obrigada {first_name}! "
            f"Seu contato foi registrado com sucesso! "
            f"Em breve entraremos em contato."
        )


# ─────────────────────────────────────────────
# HANDLER DE MENSAGENS DE TEXTO
# ─────────────────────────────────────────────
@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Paciente").strip()
    user_text = message.text

    logger.info(f"Mensagem de {first_name}: {user_text[:50]}")

    ai_response = gerar_resposta_ia(user_text, first_name)

    if "[AGENDAR]" in ai_response:
        ai_response = ai_response.replace("[AGENDAR]", "").strip()
        mensagem_final = ai_response + "\n\nÓtimo! Vou registrar seu agendamento!"
        bot.reply_to(message, mensagem_final)
        salvar_lead(first_name, str(chat_id), "agendado")
    else:
        bot.reply_to(message, ai_response)
        salvar_lead(first_name, str(chat_id), "novo")


# ─────────────────────────────────────────────
# MAIN — POLLING COM TRATAMENTO DE ERROS
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Bot Alex iniciando no Render...")
    logger.info(f"Token configurado: {bool(TOKEN)}")
    logger.info(f"NVIDIA configurada: {bool(NVIDIA_KEY)}")

    while True:
        try:
            logger.info("Iniciando polling...")
            bot.polling(none_stop=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            erro = str(e)
            if "409" in erro:
                logger.warning(
                    "Conflito 409: outra instância rodando. Aguardando 30 segundos..."
                )
                time.sleep(30)
                continue
            elif "401" in erro:
                logger.error("Token inválido! Verifique TELEGRAM_BOT_TOKEN")
                time.sleep(60)
                continue
            else:
                logger.error(f"Erro inesperado: {e}")
                time.sleep(10)
                continue