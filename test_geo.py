import os, requests
from dotenv import load_dotenv
load_dotenv()

key = os.environ["SUPABASE_KEY"]
headers = {"apikey": key, "Authorization": "Bearer " + key}
base = os.environ["SUPABASE_URL"] + "/rest/v1"

r = requests.get(f"{base}/clinicas", headers=headers,
    params={"select": "id,nome,endereco,cidade,latitude,longitude", "order": "score.desc.nullslast", "limit": 200})
print(f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code==200 else 'ERR'}")
if r.status_code == 200:
    dados = r.json()
    sem_lat = [c for c in dados if not c.get("latitude")]
    print(f"Total: {len(dados)}, sem lat: {len(sem_lat)}")
    for c in sem_lat[:3]:
        print(f"  {c['nome'][:35]} | {str(c.get('endereco',''))[:50]}")
else:
    print(r.text[:200])
