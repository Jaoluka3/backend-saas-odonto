import os
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

CIDADES = ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba", "Brasília"]

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def rodar() -> int:
    if not supabase:
        print("Erro: Supabase não configurado")
        return 0
    if not SERPAPI_KEY:
        print("Erro: SERPAPI_KEY não configurada")
        return 0

    inseridas = 0
    for cidade in CIDADES:
        try:
            params = {
                "engine": "google_maps",
                "q": f"clinica odontologica {cidade}",
                "api_key": SERPAPI_KEY,
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
            data = resp.json()

            results = data.get("local_results", [])
            for r in results:
                try:
                    telefone = (r.get("phone") or "").strip()
                    if not telefone:
                        continue

                    nome = (r.get("title") or "").strip()
                    if not nome:
                        continue

                    existing = supabase.table("clinicas").select("id").eq("telefone", telefone).execute()
                    if existing.data and len(existing.data) > 0:
                        continue

                    supabase.table("clinicas").insert({
                        "nome": nome,
                        "telefone": telefone,
                        "endereco": (r.get("address") or "").strip(),
                        "website": (r.get("website") or "").strip(),
                        "avaliacao_google": r.get("rating"),
                        "num_avaliacoes": r.get("reviews"),
                        "cidade": cidade,
                        "status": "novo",
                    }).execute()
                    inseridas += 1
                except Exception as e:
                    print(f"Erro ao processar clinica em {cidade}: {e}")

        except Exception as e:
            print(f"Erro ao buscar {cidade}: {e}")

    print(f"Buscador: {inseridas} clinicas inseridas")
    return inseridas


if __name__ == "__main__":
    rodar()
