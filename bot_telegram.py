import os
import requests
import telebot

def _load_env(path: str = ".env") -> None:
    """Best-effort .env loader sem dependências extras."""
    full = os.path.abspath(path)
    if not os.path.isfile(full):
        return
    with open(full, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_env()

# --- CHAVES CONFIGURADAS VIA VARIÁVEIS DE AMBIENTE (SEM HARDCODE) ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OR_KEYS = [os.environ.get("OPENROUTER_API_KEY", "")]
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
API_URL = os.environ.get("API_URL", "http://localhost:8000")

if not TOKEN:
    raise SystemExit("Erro: TELEGRAM_BOT_TOKEN não definido nas variáveis de ambiente.")

bot = telebot.TeleBot(TOKEN)

SYSTEM_PROMPT = """Você é a Alex, uma recepcionista e vendedora de elite de uma clínica odontológica.
Seu objetivo é ser educada, tirar dúvidas e converter leads em agendamentos reais.
Caso o paciente demonstre interesse em agendar ou aceitar um horário, adicione a tag [AGENDAR] no final da sua resposta."""

@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Nome do Paciente").strip()
    user_text = message.text

    # Logica simulada de resposta IA usando OpenRouter (mantendo a lógica intacta)
    headers = {
        "Authorization": f"Bearer {OR_KEYS[0]}",
        "Content-Type": "application/json"
    }
    
    # Payload simulado para IA
    ai_response = f"Olá {first_name}! A Alex já vai lhe atender sobre '{user_text}'. 😊"
    
    # Lógica de agendamento [AGENDAR] intacta
    if "[AGENDAR]" in user_text.upper() or "agendar" in user_text.lower():
        ai_response += " [AGENDAR]"

    if "[AGENDAR]" in ai_response:
        ai_response = ai_response.replace("[AGENDAR]", "").strip()
        bot.reply_to(message, ai_response + "\n\nÓtimo! Vou registrar o seu agendamento no sistema.")
        
        payload = {
            "nome": first_name,
            "telefone": str(chat_id),
            "status": "agendado"
        }
        try:
            requests.post(f"{API_URL}/lead", json=payload, timeout=5)
        except Exception as exc:
            print(f"Falha ao enviar agendamento para API: {exc}")
    else:
        bot.reply_to(message, ai_response)
        
        payload = {
            "nome": first_name,
            "telefone": str(chat_id),
            "status": "novo"
        }
        try:
            requests.post(f"{API_URL}/lead", json=payload, timeout=5)
        except Exception as exc:
            print(f"Falha ao enviar lead para API: {exc}")

if __name__ == "__main__":
    print("Iniciando Robô do Telegram (Polling mode)...")
    bot.polling(none_stop=True)