import os
import time
import logging
import requests
from typing import Optional
from supabase_client import supabase

logger = logging.getLogger(__name__)

NVIDIA_KEY = os.environ.get("NVIDIA_KEY", "")

ATLAS_PROMPT = (
    "Você é ATLAS, um sistema de IA avançado especializado em prospecção de clínicas "
    "odontológicas. Responda de forma técnica, direta e profissional. "
    "Quando encontrar clínicas, liste-as com nome, telefone e endereço. "
    "Nao use asteriscos, hashtags, ou marcadores markdown. Use texto simples."
)

_cache_clinicas = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


def buscar_clinicas(forcar: bool = False) -> list:
    agora = time.time()
    if not forcar and _cache_clinicas["data"] and (agora - _cache_clinicas["timestamp"]) < CACHE_TTL:
        logger.info("Usando cache de clinicas")
        return _cache_clinicas["data"]

    if not supabase:
        logger.warning("Supabase nao configurado")
        return []

    try:
        result = (
            supabase.table("clinicas")
            .select("*")
            .neq("status", "inativo")
            .order("score", desc=True, nullsfirst=False)
            .limit(50)
            .execute()
        )
    except Exception as e:
        logger.error(f"Erro ao ler clinicas do banco: {e}")
        return []

    clinicas = []
    for c in clinicas_raw:
        clinicas.append({
            "nome": (c.get("nome") or "").strip(),
            "telefone": (c.get("telefone") or "").strip(),
            "endereco": (c.get("endereco") or "").strip(),
            "website": (c.get("website") or "").strip(),
            "avaliacao_google": c.get("avaliacao_google"),
            "num_avaliacoes": c.get("num_avaliacoes"),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
            "cidade": (c.get("cidade") or "").strip(),
            "status": (c.get("status") or "novo").strip(),
            "score": c.get("score", 50),
            "email": c.get("email"),
        })

    _cache_clinicas["data"] = clinicas
    _cache_clinicas["timestamp"] = agora
    logger.info("Carregadas %d clinicas do banco", len(clinicas))
    return clinicas


def _gerar_resposta_nvidia(contexto: str) -> Optional[str]:
    if not NVIDIA_KEY:
        return None
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {NVIDIA_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "nvidia/nemotron-3-nano-30b-a3b",
        "messages": [
            {"role": "system", "content": ATLAS_PROMPT},
            {"role": "user", "content": contexto},
        ],
        "max_tokens": 600,
        "temperature": 0.7,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        logger.error(f"NVIDIA {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"NVIDIA erro: {e}")
    return None


def _gerar_resposta_fallback(mensagem: str, clinicas: list) -> str:
    msg = mensagem.lower()

    if not clinicas:
        if any(p in msg for p in ("clinica", "odonto", "buscar", "encontr", "lista", "prospec")):
            return (
                "Analisei a base de dados e nao encontrei clinicas no momento.\n\n"
                "Motivos possiveis:\n"
                "- O banco de clinicas esta vazio\n"
                "- A pipeline de busca pode precisar ser executada\n\n"
                "Sugestao: va ate a aba Agentes e clique em Executar Pipeline para iniciar a prospeccao."
            )
        return (
            "Ola, sou o ATLAS, seu assistente de prospeccao odontologica.\n\n"
            "Posso ajudar com:\n"
            "- Buscar e analisar clinicas na base de dados\n"
            "- Mostrar estatisticas do funil de vendas\n"
            "- Sugerir estrategias de prospeccao\n\n"
            "O que voce deseja saber?"
        )

    qualificadas = [c for c in clinicas if c.get("status") == "qualificado"]
    contactadas = [c for c in clinicas if c.get("status") == "contactado"]
    com_email = [c for c in clinicas if c.get("email")]

    clinicas_com_avaliacao = [c for c in clinicas if c.get("avaliacao_google")]
    media_avaliacao = (
        round(sum(c["avaliacao_google"] for c in clinicas_com_avaliacao) / len(clinicas_com_avaliacao), 1)
        if clinicas_com_avaliacao else 0
    )

    partes = [
        f"Resumo da base de dados: {len(clinicas)} clinicas cadastradas.",
        f"Status: {len(qualificadas)} qualificadas, {len(contactadas)} contactadas, {len(com_email)} com email disponivel.",
    ]
    if media_avaliacao:
        partes.append(f"Media de avaliacao Google: {media_avaliacao} estrelas.")

    com_pontos = [c for c in clinicas if c.get("score")]
    if com_pontos:
        top = sorted(com_pontos, key=lambda c: c["score"], reverse=True)[:3]
        partes.append("Top 3 clinicas por pontuacao:")
        for c in top:
            tel = c.get("telefone", "---")
            score = c.get("score", 0)
            partes.append(f"- {c['nome']} | score: {score} | tel: {tel}")
    else:
        partes.append("Clinicas ordenadas por nome:")
        for c in clinicas[:5]:
            partes.append(f"- {c['nome']} | status: {c.get('status', 'novo')}")

    partes.append("")
    if qualificadas:
        partes.append(f"Temos {len(qualificadas)} clinicas qualificadas prontas para contato. Deseja que eu gere um relatorio detalhado?")
    else:
        partes.append("Nenhuma clinica qualificada disponivel no momento. Precisa comecar uma nova prospeccao?")

    return "\n".join(partes)


def processar_chat(mensagem: str, agente: str = "ATLAS") -> dict:
    logger.info(f"Chat {agente}: {mensagem[:80]}")

    clinicas = buscar_clinicas(forcar=False)

    contexto = f"Usuário: {mensagem}\n\nClínicas encontradas ({len(clinicas)}):\n"
    for i, c in enumerate(clinicas[:10], 1):
        contexto += f"{i}. {c['nome']} - {c.get('telefone', '?')} - {c.get('endereco', '')}\n"

    resposta = _gerar_resposta_nvidia(contexto)
    if not resposta:
        resposta = _gerar_resposta_fallback(mensagem, clinicas)

    if supabase and clinicas:
        try:
            rows = [
                {
                    "nome": c["nome"],
                    "telefone": c["telefone"],
                    "endereco": c.get("endereco"),
                    "website": c.get("website"),
                    "avaliacao_google": c.get("avaliacao_google"),
                    "num_avaliacoes": c.get("num_avaliacoes"),
                    "latitude": c.get("latitude"),
                    "longitude": c.get("longitude"),
                    "cidade": "Betim",
                    "status": "novo",
                    "score": c.get("score", 50),
                }
                for c in clinicas
                if c.get("telefone")
            ]
            if rows:
                supabase.table("clinicas").upsert(
                    rows, on_conflict="telefone"
                ).execute()
                logger.info("Batch upsert %d clinicas", len(rows))
        except Exception as e:
            logger.error("Erro batch upsert clinicas: %s", e)

    if supabase:
        try:
            supabase.table("chat_historico").insert({
                "agente": agente,
                "mensagem": mensagem,
                "resposta": resposta,
                "clinicas_encontradas": len(clinicas),
            }).execute()
        except Exception as e:
            logger.error(f"Erro ao salvar historico: {e}")

    clinicas_out = [
        {
            "nome": c["nome"],
            "telefone": c.get("telefone"),
            "endereco": c.get("endereco"),
            "avaliacao_google": c.get("avaliacao_google"),
            "score": c.get("score", 50),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
        }
        for c in clinicas
    ]

    return {
        "resposta": resposta,
        "clinicas": clinicas_out,
        "agente": agente,
        "total_clinicas": len(clinicas),
    }


def obter_historico(limite: int = 20) -> list:
    if not supabase:
        return []
    try:
        data = (
            supabase.table("chat_historico")
            .select("*")
            .order("criado_em", desc=True)
            .limit(limite)
            .execute()
        )
        return data.data or []
    except Exception as e:
        logger.error(f"Erro historico: {e}")
        return []
