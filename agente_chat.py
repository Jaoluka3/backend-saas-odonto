import os
import time
import logging
import requests
from typing import Optional
from supabase_client import supabase

logger = logging.getLogger(__name__)

NVIDIA_KEY = os.environ.get("NVIDIA_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

ATLAS_PROMPT = (
    "Você é ATLAS, um sistema de IA avançado especializado em prospecção de clínicas "
    "odontológicas. Responda de forma técnica, direta e profissional. "
    "Quando encontrar clínicas, liste-as com nome, telefone e endereço."
)

_cache_clinicas = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


def buscar_clinicas(forcar: bool = False) -> list:
    agora = time.time()
    if not forcar and _cache_clinicas["data"] and (agora - _cache_clinicas["timestamp"]) < CACHE_TTL:
        logger.info("Usando cache de clinicas")
        return _cache_clinicas["data"]

    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY nao configurada")
        return []

    time.sleep(10)
    params = {
        "engine": "google_maps",
        "type": "search",
        "q": "clinica odontologica Betim MG CEP 32672306",
        "ll": "@-19.9703184,-44.2064950,14z",
        "hl": "pt-BR",
        "gl": "br",
        "start": 0,
        "api_key": SERPAPI_KEY,
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        if resp.status_code == 429:
            logger.error("429 SerpAPI - limite excedido")
            return []
        resp.raise_for_status()
        dados = resp.json()
    except Exception as e:
        logger.error(f"Erro SerpAPI: {e}")
        return []

    resultados = dados.get("local_results", [])[:20]
    clinicas = []
    for r in resultados:
        coords = r.get("gps_coordinates")
        clinica = {
            "nome": (r.get("title") or "").strip(),
            "telefone": (r.get("phone") or "").strip(),
            "endereco": (r.get("address") or "").strip(),
            "website": (r.get("website") or "").strip(),
            "avaliacao_google": r.get("rating"),
            "num_avaliacoes": r.get("reviews"),
            "latitude": coords.get("latitude") if coords else None,
            "longitude": coords.get("longitude") if coords else None,
            "horario": r.get("hours"),
            "cidade": "Betim",
            "status": "novo",
            "score": 50,
        }
        if clinica["nome"]:
            clinicas.append(clinica)

    _cache_clinicas["data"] = clinicas
    _cache_clinicas["timestamp"] = agora
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

    if not clinicas and ("clinica" in msg or "odonto" in msg or "buscar" in msg):
        return (
            "ATLAS - Análise de Prospecção\n\n"
            "Não encontrei clínicas odontológicas em Betim/MG neste momento.\n"
            "Motivos possíveis:\n"
            "1. Limite da API SerpAPI excedido\n"
            "2. Nenhum resultado disponível\n\n"
            "Sugiro aguardar e tentar novamente."
        )

    if not clinicas:
        return (
            "ATLAS - Assistente de Prospecção\n\n"
            "Olá! Sou o ATLAS. Posso ajudar com:\n"
            "- Buscar clínicas odontológicas em Betim/MG\n"
            "- Analisar dados de prospecção\n"
            "- Relatórios de desempenho\n\n"
            "Como posso ajudar?"
        )

    media = 0
    n_aval = 0
    for c in clinicas:
        if c.get("avaliacao_google"):
            media += c["avaliacao_google"]
            n_aval += 1
    media = media / n_aval if n_aval else 0

    top = sorted(
        [c for c in clinicas if c.get("avaliacao_google")],
        key=lambda c: c["avaliacao_google"], reverse=True
    )[:3]

    linhas = [
        f"ATLAS - Relatório de Prospecção\n",
        f"Encontrei {len(clinicas)} clínicas odontológicas em Betim/MG.",
        f"Média de avaliação: {media:.1f}\n",
    ]
    if top:
        linhas.append("Top 3 clínicas:")
        for c in top:
            nome = c["nome"]
            av = c.get("avaliacao_google", "N/D")
            tel = c.get("telefone", "N/D")
            linhas.append(f"  - {nome} (avaliação: {av}, tel: {tel})")
        linhas.append("")
    linhas.append("Recomendo focar nas clínicas com maior pontuação e contato disponível.")

    return "\n".join(linhas)


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
