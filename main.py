import logging
import os
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

# Conexão com Supabase via variáveis de ambiente
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    logger.warning("SUPABASE_URL ou SUPABASE_KEY nao configurados.")

app = FastAPI()

class Lead(BaseModel):
    nome: str
    telefone: str
    status: str = "novo"

@app.get("/health")
def health_check():
    return {"status": "Cérebro IA Online e Conectado"}

@app.post("/lead")
def create_lead(lead: Lead):
    if not supabase:
        return {"success": False, "error": "Banco de dados nao configurado"}

    try:
        data = supabase.table("leads").insert({
            "nome": lead.nome,
            "telefone": lead.telefone,
            "status": lead.status
        }).execute()
        if data.data:
            logger.info("Lead criado: %s (%s)", lead.nome, lead.status)
            return {"success": True, "data": data.data}
        else:
            logger.error("Supabase retornou sem data para lead %s", lead.nome)
            return {"success": False, "error": "Falha ao inserir lead"}
    except Exception as e:
        logger.error("Erro ao criar lead: %s", e)
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    # app rodando na porta $PORT via variável de ambiente
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)