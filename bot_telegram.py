import logging
import os
import requests
import telebot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# --- CHAVES CONFIGURADAS VIA VARIÁVEIS DE AMBIENTE (SEM HARDCODE) ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
API_URL = os.environ.get("API_URL", "https://backend-saas-odonto.onrender.com")

if not TOKEN:
    raise SystemExit("Erro: TELEGRAM_BOT_TOKEN nao definido nas variaveis de ambiente.")

bot = telebot.TeleBot(TOKEN)

SYSTEM_PROMPT = """Você é a Alex, recepcionista da Clínica Sorriso. Responda APENAS perguntas sobre a clínica: horários, procedimentos, agendamentos e dúvidas de atendimento. Horários: segunda a sexta 8h-18h, sábado 8h-12h. Seja curta, simpática e direta. Se perguntarem algo fora do assunto da clínica, diga que só pode ajudar com assuntos da clínica. Se o paciente quiser agendar, adicione [AGENDAR] no final da resposta."""

def gerar_resposta_ia(user_text, first_name):
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "")
    if not nvidia_key:
        logger.info("NVIDIA_KEY nao definida, usando fallback")
        return f"Olá {first_name}! Sou a Alex. Como posso ajudar?"
    
    try:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {nvidia_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "nvidia/llama-3.1-8b-instruct",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Nome: {first_name}\nMensagem: {user_text}"}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            logger.error("NVIDIA erro %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("NVIDIA falhou: %s", e)
    
    return f"Olá {first_name}! Sou a Alex. Como posso ajudar?"


def _extrair_telefone(message):
    if message.contact and message.contact.phone_number:
        return message.contact.phone_number
    return str(message.chat.id)


def _enviar_lead(api_url, nome, telefone, status):
    payload = {"nome": nome, "telefone": telefone, "status": status}
    url = f"{api_url}/lead"
    for tentativa in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            logger.info("Lead %s enviado (tentativa %d): HTTP %s", status, tentativa, resp.status_code)
            return
        except requests.exceptions.RequestException as e:
            logger.warning("Lead %s falhou (tentativa %d/3): %s", status, tentativa, e)
    logger.error("Lead %s perdido apos 3 tentativas", status)


@bot.message_handler(func=lambda message: True, content_types=["text", "contact"])
def handle_text(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Nome do Paciente").strip()
    user_text = message.text or ""

    ai_response = gerar_resposta_ia(user_text, first_name)

    if "[AGENDAR]" in user_text.upper() or "agendar" in user_text.lower():
        ai_response += " [AGENDAR]"

    if "[AGENDAR]" in ai_response:
        ai_response = ai_response.replace("[AGENDAR]", "").strip()
        bot.reply_to(message, ai_response + "\n\nOtimo! Por favor, compartilhe seu numero de telefone usando o botao de contato para confirmar o agendamento.")
        logger.info("Agendamento solicitado por %s (chat %s)", first_name, chat_id)
    else:
        bot.reply_to(message, ai_response)
        telefone = _extrair_telefone(message)
        _enviar_lead(API_URL, first_name, telefone, "novo")


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Nome do Paciente").strip()
    telefone = message.contact.phone_number

    _enviar_lead(API_URL, first_name, telefone, "agendado")
    bot.reply_to(message, "Obrigado! Seu agendamento foi registrado com sucesso. Entraremos em contato em breve!")
    logger.info("Contato recebido de %s: %s", first_name, telefone)

if __name__ == "__main__":
    logger.info("Iniciando Robo do Telegram (Polling mode)...")
    bot.polling(none_stop=True)