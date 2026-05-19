import os
import sys

REQUIRED_ENV_VARS = {
    "TELEGRAM_BOT_TOKEN": "Token do Bot Telegram",
    "SUPABASE_URL": "URL do Supabase",
    "SUPABASE_KEY": "Chave da API Supabase",
    "SERPAPI_KEY": "Chave da API SerpAPI",
    "NVIDIA_KEY": "Chave da API NVIDIA LLM",
}

missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
if missing:
    print("\n🚨 ERRO CRÍTICO: VARIÁVEIS DE AMBIENTE FALTANDO")
    print("=" * 50)
    for var in missing:
        print(f"  ❌ {var} - {REQUIRED_ENV_VARS[var]}")
    print("=" * 50)
    print("Defina as variáveis acima antes de iniciar o sistema.\n")
    sys.exit(1)

print("✅ Todas as variáveis de ambiente validadas com sucesso\n")

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase_client import supabase
from agente_orquestrador import (
    rodar_pipeline_async,
    iniciar_agendador,
    parar_agendador,
    status,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class LeadPayload(BaseModel):
    """Modelo do lead recebido via JSON do bot_telegram."""
    nome: str
    telefone: str
    status: str = "novo"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida do scheduler com startup/shutdown."""
    logger.info("Iniciando scheduler...")
    iniciar_agendador()
    yield
    logger.info("Parando scheduler...")
    parar_agendador()


app = FastAPI(lifespan=lifespan)
app.mount("/painel", StaticFiles(directory="static", html=True), name="static")


@app.get("/health")
def health_check():
    return {"status": "Cerebro IA Online e Conectado"}


@app.post("/lead")
def create_lead(lead: LeadPayload):
    """Cria um lead na tabela leads a partir de JSON body."""
    if not supabase:
        return {"success": False, "error": "Banco de dados nao configurado"}
    try:
        data = (
            supabase.table("leads")
            .insert(lead.model_dump())
            .execute()
        )
        if data.data:
            logger.info("Lead criado: %s (%s)", lead.nome, lead.telefone)
            return {"success": True, "data": data.data}
        return {"success": False, "error": "Falha ao inserir lead"}
    except Exception as e:
        logger.error("Erro ao criar lead: %s", e)
        return {"success": False, "error": str(e)}


@app.get("/clinicas")
def listar_clinicas(
    limit: int = Query(50, ge=1, le=200, description="Maximo de registros"),
    offset: int = Query(0, ge=0, description="Deslocamento para paginacao"),
):
    """Lista clinicas com paginacao e ordenacao por score."""
    if not supabase:
        return {"success": False, "error": "Banco de dados nao configurado"}
    try:
        data = (
            supabase.table("clinicas")
            .select("*")
            .order("score", desc=True, nullsfirst=False)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return {"success": True, "data": data.data, "limit": limit, "offset": offset}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/funil")
def funil_status():
    """Contagem de clinicas por status (funil de vendas)."""
    if not supabase:
        return {"success": False, "error": "Banco de dados nao configurado"}
    try:
        result = supabase.table("clinicas").select("status").execute()
        contagem = {
            "novo": 0,
            "qualificado": 0,
            "descartado": 0,
            "contactado": 0,
            "inativo": 0,
            "cliente": 0,
        }
        for r in result.data:
            s = r.get("status", "novo")
            if s in contagem:
                contagem[s] += 1
        return {"success": True, "data": contagem}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/agentes/rodar")
@app.post("/agentes/rodar")
def rodar_agentes():
    """Dispara a pipeline em background e retorna imediatamente.
    Aceita GET (navegador) e POST (curl/programatico)."""
    try:
        resultado = rodar_pipeline_async()
        return {"success": True, "data": resultado}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/agentes/status")
def status_agentes():
    """Status da pipeline com lock atual, ultima execucao e agendamento."""
    return {"success": True, "data": status()}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
