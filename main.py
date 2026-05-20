import os
import sys

REQUIRED_ENV_VARS = {
    "TELEGRAM_BOT_TOKEN": "Token do Bot Telegram (obrigatorio)",
    "SUPABASE_URL": "URL do Supabase (obrigatorio)",
    "SUPABASE_KEY": "Chave da API Supabase (obrigatorio)",
}

OPTIONAL_ENV_VARS = {
    "SERPAPI_KEY": "Chave da API SerpAPI (opcional - necessario apenas para busca de clinicas)",
    "NVIDIA_KEY": "Chave da API NVIDIA LLM (opcional - necessario apenas para geracao de mensagens IA)",
    "GMAIL_EMAIL": "Email Gmail para envio de mensagens (opcional - necessario para SMTP)",
    "GMAIL_APP_PASSWORD": "App Password do Gmail (opcional - necessario para SMTP)",
}

missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
if missing:
    print("\n🚨 ERRO CRÍTICO: VARIÁVEIS DE AMBIENTE OBRIGATÓRIAS FALTANDO")
    print("=" * 50)
    for var in missing:
        print(f"  ❌ {var} - {REQUIRED_ENV_VARS[var]}")
    print("=" * 50)
    print("Defina as variáveis acima antes de iniciar o sistema.\n")
    sys.exit(1)

print("✅ Todas as variáveis de ambiente obrigatórias validadas com sucesso\n")

missing_optional = [k for k in OPTIONAL_ENV_VARS if not os.environ.get(k)]
if missing_optional:
    print("⚠️  AVISO: Variáveis opcionais não configuradas - funcionalidades limitadas")
    for var in missing_optional:
        print(f"  ⚠️  {var} - {OPTIONAL_ENV_VARS[var]}")
    print()

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from supabase_client import supabase
from bot_telegram import bot
import telebot
from agente_orquestrador import (
    rodar_pipeline_async,
    iniciar_agendador,
    parar_agendador,
    status,
)
from agente_chat import processar_chat, obter_historico
from gmail_client import verificar_respostas, contar_respostas

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


class ChatPayload(BaseModel):
    """Modelo da mensagem do chat ATLAS."""
    message: str = ""
    mensagem: str = ""
    agente: str = "ATLAS"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida do scheduler e webhook com startup/shutdown."""
    logger.info("Iniciando scheduler...")
    iniciar_agendador()

    webhook_base = (
        os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("WEBHOOK_URL")
        or ""
    )
    if webhook_base:
        webhook_url = f"{webhook_base}/webhook"
        try:
            bot.remove_webhook()
            bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook configurado: {webhook_url}")
        except Exception as e:
            logger.error(f"Falha ao configurar webhook: {e}")
    else:
        logger.info("RENDER_EXTERNAL_URL ausente — webhook nao configurado (dev local)")

    yield

    logger.info("Parando scheduler...")
    parar_agendador()
    try:
        bot.remove_webhook()
        logger.info("Webhook removido")
    except Exception as e:
        logger.error(f"Falha ao remover webhook: {e}")


app = FastAPI(lifespan=lifespan)
app.mount("/painel", StaticFiles(directory="static", html=True), name="static")


# v4 - pipeline prospecting
@app.get("/health")
def health_check():
    return {"status": "Cerebro IA Online e Conectado"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Recebe updates do Telegram via webhook."""
    try:
        body = await request.json()
        update = telebot.types.Update.de_json(body)
        bot.process_new_updates([update])
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/chat")
def chat_handler(payload: ChatPayload):
    """Endpoint do chat ATLAS. Aceita message ou mensagem no body."""
    texto = payload.message or payload.mensagem
    if not texto:
        return {"success": False, "error": "Mensagem vazia"}
    try:
        resultado = processar_chat(mensagem=texto, agente=payload.agente)
        return {"success": True, **resultado}
    except Exception as e:
        logger.error(f"Erro no chat: {e}")
        return {"success": False, "error": str(e)}


@app.get("/chat/historico")
def chat_historico(limite: int = Query(20, ge=1, le=100)):
    """Retorna ultimas mensagens do chat ATLAS."""
    try:
        historico = obter_historico(limite=limite)
        return {"success": True, "data": historico}
    except Exception as e:
        logger.error(f"Erro ao obter historico: {e}")
        return {"success": False, "error": str(e)}


@app.get("/gmail/verificar")
def gmail_verificar():
    """Verifica emails do Gmail relacionados a clinicas."""
    try:
        resultado = contar_respostas()
        return {"success": True, "data": resultado}
    except Exception as e:
        logger.error(f"Erro Gmail: {e}")
        return {"success": False, "error": str(e)}


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
    """Dispara a pipeline em background e retorna imediatamente."""
    try:
        resultado = rodar_pipeline_async()
        return {"success": True, "data": resultado}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/agentes/enviar")
@app.post("/agentes/enviar")
def enviar_agentes():
    """Executa apenas o envio de emails (contato)."""
    import agente_contato
    try:
        r = agente_contato.rodar()
        return {"success": True, "data": {"enviados": r}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/agentes/reset")
def reset_agentes():
    """Reseta clinicas contactadas/descartadas com website para qualificado."""
    if not supabase:
        return {"success": False, "error": "Sem Supabase"}
    try:
        r1 = supabase.table("clinicas").select("id,status,website").eq("status", "contactado").execute()
        r2 = supabase.table("clinicas").select("id,status,website").eq("status", "descartado").execute()
        alvo = [c for c in (r1.data or []) + (r2.data or []) if c.get("website")]
        if not alvo:
            return {"success": True, "data": {"resetadas": 0}}
        for c in alvo:
            supabase.table("clinicas").update({"status": "qualificado", "email": None}).eq("id", c["id"]).execute()
        logger.info("Reset: %d clinicas para qualificado", len(alvo))
        return {"success": True, "data": {"resetadas": len(alvo)}}
    except Exception as e:
        logger.error("Erro reset: %s", e)
        return {"success": False, "error": str(e)}


@app.get("/agentes/status")
def status_agentes():
    """Status da pipeline com lock atual, ultima execucao e agendamento."""
    return {"success": True, "data": status()}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
