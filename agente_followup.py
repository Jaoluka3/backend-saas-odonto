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


def gerar_followup(nome: str, tentativa: int) -> str:
    if tentativa == 1:
        prompt = "Ainda temos interesse em ajudar a clinica a automatizar o atendimento. Seja educado e reforce os beneficios."
    else:
        prompt = "Ultima tentativa de contato. Seja educado mas deixe claro que e a ultima oportunidade. Ofereca um desconto de 30% no primeiro mes."

    if not NVIDIA_KEY:
        return f"Follow-up {tentativa}: Ola {nome}, ainda temos interesse em ajudar!"

    try:
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json={
                "model": "nvidia/nemotron-3-nano-30b-a3b",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Clinica: {nome}"},
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
        print(f"NVIDIA falhou no followup de {nome}: {e}")

    return f"Follow-up {tentativa}: Ola {nome}, ainda temos interesse em ajudar!"


def rodar() -> dict:
    if not supabase:
        print("Erro: Supabase nao configurado")
        return {"followups_enviados": 0, "inativados": 0}

    try:
        result = supabase.table("clinicas").select("*").eq("status", "contactado").execute()
        clinicas = result.data
    except Exception as e:
        print(f"Erro ao ler clinicas contactadas: {e}")
        return {"followups_enviados": 0, "inativados": 0}

    hoje = datetime.now()
    followups = 0
    inativados = 0

    for c in clinicas:
        try:
            data_contato = datetime.fromisoformat(c["data_contato"])
            dias = (hoje - data_contato).days
            nf = c.get("numero_followups", 0) or 0

            if dias >= 14 and nf >= 2:
                supabase.table("clinicas").update({
                    "status": "inativo",
                }).eq("id", c["id"]).execute()
                inativados += 1
                print(f"Inativado: {c['nome']} ({dias} dias sem resposta)")
            elif dias >= 7 and nf == 1:
                msg = gerar_followup(c["nome"], 2)
                supabase.table("clinicas").update({
                    "numero_followups": 2,
                    "mensagem_enviada": msg,
                }).eq("id", c["id"]).execute()
                followups += 1
                print(f"Followup 2 para {c['nome']}:\n{msg}\n")
            elif dias >= 3 and nf == 0:
                msg = gerar_followup(c["nome"], 1)
                supabase.table("clinicas").update({
                    "numero_followups": 1,
                    "mensagem_enviada": msg,
                }).eq("id", c["id"]).execute()
                followups += 1
                print(f"Followup 1 para {c['nome']}:\n{msg}\n")
        except Exception as e:
            print(f"Erro no followup de {c.get('id')}: {e}")

    print(f"Followup: {followups} enviados, {inativados} inativados")
    return {"followups_enviados": followups, "inativados": inativados}


if __name__ == "__main__":
    rodar()
