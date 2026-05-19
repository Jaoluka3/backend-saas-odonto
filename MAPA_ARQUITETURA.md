# 🗺️ Mapa de Dependências e Fluxos - SaaS Dentista

## Arquitetura Atual (com problemas marcados)

```
┌─────────────────────────────────────────────────────────────────┐
│                     TELEGRAM USERS                              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │   bot_telegram.py          │
    │  ⚠️ PROBLEMA: Telefone     │  
    │     inválido (chat_id)     │
    │  ⚠️ PROBLEMA: gerar_      │
    │     resposta_ia usa NVIDIA │
    └────────────┬───────────────┘
                 │
                 ├──────────────────────┬──────────────────┐
                 │                      │                  │
                 ▼                      ▼                  ▼
    ┌──────────────────────┐  ┌─────────────────┐  ┌──────────────┐
    │ main.py              │  │ agente_         │  │ supabase_    │
    │ ❌ Sem validação de  │  │ orquestrador.py │  │ client.py    │
    │    startup (P1)      │  │ 🔴 DEADLOCK     │  │              │
    │ (falha silenciosa)   │  │    (Lock issue) │  │ ✅ OK        │
    └──────────┬───────────┘  └────────┬────────┘  └──────────────┘
               │                       │
               └───────────┬───────────┘
                           │
                    ┌──────▼──────────────────┐
                    │ Pipeline Assíncrona     │
                    │ (rodar_pipeline_async)  │
                    └──────┬───────┬──────────┘
                           │       │
         ┌─────────────────┘       └─────────────────┐
         │                                           │
         ▼                      ▼                    ▼
    ┌─────────────┐   ┌──────────────────┐  ┌──────────────┐
    │ agente_     │   │ agente_          │  │ agente_      │
    │ buscador.py │   │ qualificador.py  │  │ contato.py   │
    │ ❌ Sem      │   │                  │  │              │
    │ validação   │   │ ✅ OK            │  │ ⚠️ Telefone  │
    │ SERPAPI_KEY │   │                  │  │  inválido    │
    │ (falha      │   │                  │  │              │
    │ silenciosa) │   │                  │  │              │
    └─────────────┘   └──────────────────┘  └──────────────┘
         │
         ▼
    SerpAPI (Google Maps)
    ❌ Sem validação de API key

    ┌──────────────────────────────────────┐
    │ SUPABASE (PostgreSQL)                │
    │ Tabela: clinicas                    │
    │ Status: novo → qualificado → ...    │
    │                                      │
    │ ✅ Funciona, mas:                   │
    │    - Sem backup documentado         │
    │    - Sem disaster recovery          │
    └──────────────────────────────────────┘
```

---

## 📡 Fluxo de Sincronização (QUEBRADO)

```
┌──────────────────────────────────────────────┐
│   watch_sync.py / sync_to_obsidian.sh        │
│   ❌ CRÍTICO: LOOP INFINITO                  │
└────────────────┬─────────────────────────────┘
                 │
                 ├─ A cada 1 segundo:
                 │  └─ Adiciona "- **Last Sync:** HH:MM:SS"
                 │
                 ▼ (170+ vezes por dia)
         ┌───────────────────────┐
         │   CONTEXT.md          │
         │                       │
         │ - Last Sync: 15:28:25 │ ← Linha 15
         │ - Last Sync: 15:28:22 │ ← Linha 16
         │ - Last Sync: 15:28:18 │ ← Linha 17
         │ ...                   │ ← 170+ linhas idênticas
         │ - Last Sync: 02:06:24 │ ← Linha 180
         │                       │
         └───────────┬───────────┘
                     │
                     ├─ Git: commits poluídos
                     ├─ Disco: crescimento infinito
                     └─ Leitura: arquivo inutilizável

        ✅ DEVERIA SER:
        ┌────────────────────┐
        │   CONTEXT.md       │
        │ Last updated:      │
        │ 2026-05-18 14:30   │  ← Uma única linha
        │ (sincronizado 1x   │     atualizada
        │  por dia)          │     uma vez por dia
        └────────────────────┘
```

---

## 🔀 Fluxo de Decisão AI (CONFUSO)

```
┌──────────────────────────────────────┐
│    DECISIONS.md                      │
│    "Use Gemini 2.0 Flash"            │  ← Arquitetura registrada
└────────────┬──────────────────────────┘
             │
             ❌ MISMATCH
             │
┌────────────▼──────────────────────────┐
│    bot_telegram.py:gerar_resposta_ia()│
│                                        │
│    if not nvidia_key:                 │
│      return "fallback genérico"       │
│                                        │  ← Implementação REAL
│    resp = requests.post(               │
│      "https://integrate.api.nvidia.   │
│       com/v1/chat/completions",       │
│      model="meta/llama-3.1-8b-instruct"
│    )                                  │
└────────────────────────────────────────┘
             │
             ▼
    ❓ Quando mudou?
    ❓ Por quê?
    ❓ Custos?
    ❓ Plano de volta?
    
    → Ninguém sabe! 😱
```

---

## 🧵 Fluxo de Lock (DEADLOCK RISCO)

```
Cenário Normal:
  Cliente A                        Sistema
    │                              │
    ├─ GET /agentes/pipeline       │
    │                              ▼
    │                      lock.acquire() = ✅
    │                              │
    │                      rodar_pipeline()
    │                              │
    │                      (30 segundos de trabalho)
    │                              │
    └──────── timeout ────────────▶ ?
                                    │
                                    ▼
                            finally: lock.release() ✅

Cenário de CRASH (COM LOCK ATUAL):
  Cliente A                        Sistema
    │                              │
    ├─ GET /agentes/pipeline       │
    │                              ▼
    │                      lock.acquire() = ✅
    │                              │
    │                      rodar_pipeline()
    │                              │
    │                      Erro não previsto!
    │                              │ 🔥 EXCEPTION
    │                              │ (não chega no finally?)
    │                              │
  Cliente B                        ▼
    │                      (lock NÃO liberado!)
    ├─ GET /agentes/pipeline       │
    │                              ▼
    │                      lock.acquire() = ❌ FALHA
    │                              │
    │                      Não entra (ocupado)
    │                              │
  Cliente C                        │
    ├─ GET /agentes/pipeline       │
    │                              │
    │                      lock.acquire() = ❌ FALHA
    │                              │
  ...sistema TRAVADO PERMANENTEMENTE até reiniciar

Solução com TIMEOUT:
    lock.acquire(timeout=5)
    ↓
    Se 5 segundos passarem → liberta automáticamente
    Ninguém fica pendurado pra sempre
```

---

## 🔗 Dependências (Arquivo vs Arquivo)

```
main.py
  ├─ imports: agente_orquestrador
  │                ├─ imports: agente_buscador
  │                │                ├─ requires: SERPAPI_KEY ❌ NÃO VALIDADO
  │                │                └─ imports: supabase_client
  │                │
  │                ├─ imports: agente_qualificador
  │                │                └─ imports: supabase_client
  │                │
  │                ├─ imports: agente_contato
  │                │                ├─ requires: telefone (invalido!)
  │                │                └─ imports: supabase_client
  │                │
  │                └─ imports: agente_followup
  │                                └─ imports: supabase_client
  │
  ├─ imports: supabase_client
  │                ├─ requires: SUPABASE_URL ❌ NÃO VALIDADO
  │                └─ requires: SUPABASE_KEY ❌ NÃO VALIDADO
  │
  └─ imports: FastAPI
                    └─ monta /painel (static files)

bot_telegram.py
  ├─ imports: supabase_client
  │                └─ requires: SUPABASE_URL ❌ NÃO VALIDADO
  │
  └─ requires: NVIDIA_API_KEY ❌ NÃO VALIDADO
            (deveria ser GEMINI_API_KEY conforme DECISIONS.md!)
```

---

## ✅ vs ❌ Checklist por Arquivo

```
┌─────────────────────────────┬──────────┬──────────┐
│ Arquivo                     │ Status   │ Problema │
├─────────────────────────────┼──────────┼──────────┤
│ main.py                     │ ⚠️ ALERTA│ Sem      │
│                             │          │ validação│
│                             │          │ de env   │
├─────────────────────────────┼──────────┼──────────┤
│ bot_telegram.py             │ ⚠️ ALERTA│ 2 issues │
│                             │          │ (AI + tel)
├─────────────────────────────┼──────────┼──────────┤
│ agente_buscador.py          │ ⚠️ ALERTA│ Sem      │
│                             │          │ validação│
│                             │          │ serpapi  │
├─────────────────────────────┼──────────┼──────────┤
│ agente_qualificador.py      │ ✅ OK    │ Nenhum  │
├─────────────────────────────┼──────────┼──────────┤
│ agente_contato.py           │ ⚠️ ALERTA│ Depende │
│                             │          │ telefone│
│                             │          │ inválido│
├─────────────────────────────┼──────────┼──────────┤
│ agente_orquestrador.py      │ 🔴 CRÍTI │ Deadlock│
│                             │          │ lock    │
├─────────────────────────────┼──────────┼──────────┤
│ supabase_client.py          │ ✅ OK    │ Nenhum  │
├─────────────────────────────┼──────────┼──────────┤
│ requirements.txt            │ ⚠️ ALERTA│ Falta   │
│                             │          │ google- │
│                             │          │ genai   │
├─────────────────────────────┼──────────┼──────────┤
│ CONTEXT.md                  │ 🔴 CRÍTI │ Loop    │
│                             │          │ infinito│
├─────────────────────────────┼──────────┼──────────┤
│ DECISIONS.md                │ ⚠️ ALERTA│ Descrito│
│                             │          │ Gemini, │
│                             │          │ não    │
│                             │          │ NVIDIA  │
├─────────────────────────────┼──────────┼──────────┤
│ render.yaml                 │ ✅ OK    │ Nenhum  │
├─────────────────────────────┼──────────┼──────────┤
│ graphify-out/               │ ⚠️ ALERTA│ Grafo   │
│                             │          │ pequeno,│
│                             │          │ fraco   │
└─────────────────────────────┴──────────┴──────────┘
```

---

## 🏗️ Estrutura Recomendada Pós-Fix

```
d:\saas dentista\
├── main.py                    ← Validação ENV no top
├── bot_telegram.py            ← Telefone obrigatório
├── agente_orquestrador.py     ← Lock com timeout
├── agente_buscador.py         ← Fail-fast sem SERPAPI
│
├── DOCS/ (novo)               ← Organizar documentação
│   ├── CONTEXT.md             ← Template limpo
│   ├── DECISIONS.md           ← Explicar Gemini→NVIDIA
│   ├── ANALISE_CRITICA.md     ← Erros encontrados
│   ├── ACOES_IMEDIATAS.md     ← Como consertar
│   ├── RESUMO_EXECUTIVO.md    ← Para executivos
│   └── ARQUITETURA.md         ← (novo) Diagrama visual
│
├── requirements.txt           ← Completo com todas deps
├── render.yaml                ← OK
├── graphify-out/              ← Atualizado
│
└── .github/
    └── workflows/
        └── validate.yml (novo) ← Testar ENV vars
```

---

## 🎯 Pontos de Verificação (Smoke Tests)

```bash
# Teste 1: Startup falha corretamente?
TELEGRAM_BOT_TOKEN= SUPABASE_URL= SUPABASE_KEY= SERPAPI_KEY= \
NVIDIA_API_KEY= python3 main.py
# Esperado: ❌ Erro com listagem de vars faltantes

# Teste 2: Lock não trava?
python3 -c "
import threading
from agente_orquestrador import _pipeline_lock

acquired = _pipeline_lock.acquire(timeout=1)
print('Lock liberado OK' if acquired else 'DEADLOCK!!')
"
# Esperado: ✅ Lock liberado OK

# Teste 3: CONTEXT.md foi limpo?
grep "Last Sync" CONTEXT.md | wc -l
# Esperado: ≤ 1 (apenas a atualização atual)

# Teste 4: Telefone validado?
# Testar no bot: enviar mensagem sem compartilhar contato
# Esperado: Bot pede para compartilhar

# Teste 5: Graphify atualizado?
wc -l graphify-out/graph.json
# Esperado: Número maior que versão anterior
```

---

**Diagrama gerado:** 18 de maio de 2026  
**Para entender:** Como os componentes se conectam e onde os problemas aparecem  
**Próximo passo:** Ver ACOES_IMEDIATAS.md para executar fixes
