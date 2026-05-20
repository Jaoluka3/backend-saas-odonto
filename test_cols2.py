import os, requests
from dotenv import load_dotenv
load_dotenv()

key = os.environ["SUPABASE_KEY"]
headers = {"apikey": key, "Authorization": "Bearer " + key}
base = os.environ["SUPABASE_URL"] + "/rest/v1"

# Get ONE row to see all columns
r = requests.get(f"{base}/clinicas", headers=headers, params={"select": "*", "limit": 1})
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    if d:
        print("Columns:", list(d[0].keys()))
    else:
        print("Empty result")
else:
    print(r.text[:300])
