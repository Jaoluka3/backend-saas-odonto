import logging
import os
import requests
import telebot
from supabase_client import supabase

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

# ================================================
# MOTOR DE IA: NVIDIA LLaMA 3.1
# ================================================
# Decisão: 19/05/2026 (migrado de Gemini 2.0 Flash)
# Motivo: [DOCUMENTAR - custo menor? latência? rate limits?]
# Latência: ~2s por request
# Rate limit: 1000 req/dia (plano atual)
# Fallback: Resposta genérica se API cair
# Documentação: DECISIONS.md
# ================================================

# --- CHAVES CONFIGURADAS VIA VARIÁVEIS DE AMBIENTE (SEM HARDCODE) ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

if not TOKEN:
    raise SystemExit("Erro: TELEGRAM_BOT_TOKEN nao definido nas variaveis de ambiente.")
if not NVIDIA_API_KEY:
    raise SystemExit("Erro: NVIDIA_API_KEY nao definida nas variaveis de ambiente.")

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
            "model": "meta/llama-3.1-8b-instruct",
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
    """Retorna telefone validado ou None (força compartilhamento)."""
    if not message.contact or not message.contact.phone_number:
        logger.warning("Usuário %s: contato não compartilhado", message.chat.id)
        return None

    telefone = message.contact.phone_number
    if not isinstance(telefone, str) or len(telefone) < 8:
        logger.warning("Telefone inválido recebido: %s", telefone)
        return None

    logger.info("Telefone válido extraído: %s", telefone)
    return telefone


def _enviar_lead(nome: str, telefone: str, status: str):
    """Salva lead diretamente no Supabase (sem HTTP)."""
    if not supabase:
        logger.error("Supabase nao configurado, lead perdido: %s", nome)
        return
    for tentativa in range(1, 4):
        try:
            supabase.table("clinicas").insert({
                "nome": nome, "telefone": telefone, "status": status
            }).execute()
            logger.info("Lead %s salvo no banco: %s (%s)", status, nome, telefone)
            return
        except Exception as e:
            logger.warning("Lead %s falhou (tentativa %d/3): %s", status, tentativa, e)
    logger.error("Lead %s perdido apos 3 tentativas: %s", status, nome)


@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Nome do Paciente").strip()
    user_text = message.text or ""

    telefone = _extrair_telefone(message)

    if not telefone and ("[AGENDAR]" in user_text.upper() or "agendar" in user_text.lower()):
        bot.send_message(
            chat_id,
            "📱 Para agendar, preciso do seu contato!\n"
            "Por favor, compartilhe seu telefone usando o botão de contato abaixo.",
            reply_markup=telebot.types.ReplyKeyboardMarkup(
                one_time_keyboard=True, resize_keyboard=True
            ).add(telebot.types.KeyboardButton(
                "📞 Compartilhar Contato", request_contact=True
            ))
        )
        return

    ai_response = gerar_resposta_ia(user_text, first_name)

    if "[AGENDAR]" in user_text.upper() or "agendar" in user_text.lower():
        ai_response += " [AGENDAR]"

    if "[AGENDAR]" in ai_response:
        ai_response = ai_response.replace("[AGENDAR]", "").strip()
        bot.reply_to(message, ai_response + "\n\nOtimo! Por favor, compartilhe seu numero de telefone usando o botao de contato para confirmar o agendamento.")
        logger.info("Agendamento solicitado por %s (chat %s)", first_name, chat_id)
    else:
        bot.reply_to(message, ai_response)


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Nome do Paciente").strip()
    telefone = message.contact.phone_number

    _enviar_lead(first_name, telefone, "agendado")
    bot.reply_to(message, "Obrigado! Seu agendamento foi registrado com sucesso. Entraremos em contato em breve!")
    logger.info("Contato recebido de %s: %s", first_name, telefone)

if __name__ == "__main__":
    import sys
    import time as time_module

    print("Bot iniciando apenas no Render...")
    print("Se estiver rodando localmente, use Ctrl+C para parar.")
    logger.info("Iniciando Robo do Telegram (Polling mode)...")

    while True:
        try:
            logger.info("Iniciando polling...")
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            erro = str(e)
            if "409" in erro:
                logger.warning("Conflito 409 detectado. Aguardando 30s...")
                time_module.sleep(30)
                continue
            else:
                logger.error(f"Erro inesperado: {e}")
                time_module.sleep(10)
                continue