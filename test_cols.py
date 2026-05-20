import os, requests
from dotenv import load_dotenv
load_dotenv()

key = os.environ["SUPABASE_SERVICE_KEY"] or os.environ["SUPABASE_KEY"]
headers = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}
base = os.environ["SUPABASE_URL"] + "/rest/v1"

# Try various potential column names
r = requests.get(f"{base}/clinicas", headers=headers, params={"select": "id,nome,lat,lng,latit,longi,coord_x,coord_y,latitude,longitude", "limit": 1})
print(f"Status: {r.status_code}")
if r.status_code == 200:
    print(list(r.json()[0].keys()) if r.json() else "empty")
else:
    print(r.text[:300])
