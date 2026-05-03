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
OR_KEYS = [
    os.environ.get("OPENROUTER_KEY_1", ""),
    os.environ.get("OPENROUTER_KEY_2", ""),
    os.environ.get("OPENROUTER_KEY_3", ""),
    os.environ.get("OPENROUTER_KEY_4", ""),
    os.environ.get("OPENROUTER_KEY_5", ""),
    os.environ.get("OPENROUTER_KEY_6", ""),
    os.environ.get("OPENROUTER_KEY_7", ""),
    os.environ.get("OPENROUTER_KEY_8", ""),
    os.environ.get("OPENROUTER_KEY_9", ""),
    os.environ.get("OPENROUTER_KEY_10", ""),
]
OR_KEYS = [k for k in OR_KEYS if k]
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
API_URL = os.environ.get("API_URL", "http://localhost:8000")

if not TOKEN:
    raise SystemExit("Erro: TELEGRAM_BOT_TOKEN não definido nas variáveis de ambiente.")

bot = telebot.TeleBot(TOKEN)

SYSTEM_PROMPT = """Você é a Alex, uma recepcionista e vendedora de elite de uma clínica odontológica.
Seu objetivo é ser educada, tirar dúvidas e converter leads em agendamentos reais.
Caso o paciente demonstre interesse em agendar ou aceitar um horário, adicione a tag [AGENDAR] no final da sua resposta."""

def gerar_resposta_ia(user_text, first_name):
    GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
    if not GEMINI_KEY:
        return f"Olá {first_name}! Sou a Alex. Como posso ajudar?"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": f"Nome: {first_name}\nMensagem: {user_text}"}]}]
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass

    return f"Olá {first_name}! Sou a Alex. Como posso ajudar?"

@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    first_name = (message.from_user.first_name or "Nome do Paciente").strip()
    user_text = message.text

    ai_response = gerar_resposta_ia(user_text, first_name)
    
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