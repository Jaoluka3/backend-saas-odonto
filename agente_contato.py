import os
from datetime import datetime
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

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
    if not NVIDIA_KEY:
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
    except Exception as e:
        print(f"NVIDIA falhou para {nome}: {e}")

    return f"Ola! Oferecemos um bot de atendimento para {nome}. Interessado?"


def rodar() -> int:
    if not supabase:
        print("Erro: Supabase nao configurado")
        return 0

    try:
        result = supabase.table("clinicas").select("*").eq("status", "qualificado").execute()
        clinicas = result.data
    except Exception as e:
        print(f"Erro ao ler clinicas qualificadas: {e}")
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
            print(f"Mensagem para {c['nome']}:\n{mensagem}\n")
        except Exception as e:
            print(f"Erro ao contactar clinica {c.get('id')}: {e}")

    print(f"Contato: {contactadas} clinicas contactadas")
    return contactadas


if __name__ == "__main__":
    rodar()
