# 🔧 Ações Imediatas - SaaS Dentista

## Status: AGUARDANDO EXECUÇÃO

---

## ⏱️ URGENTES (Hoje - 18 de Maio)

### 1. ✋ PARAR Loop Infinito no Obsidian
```bash
# No seu servidor/máquina:

# 1a. Ver o que está rodando
ps aux | grep -E "watch_sync|sync_to_obsidian|cron"

# 1b. Matar processes (se houver)
pkill -f sync_to_obsidian
pkill -f watch_sync

# 1c. Deletar arquivo corrompido
rm CONTEXT.md

# 1d. Recriar template limpo
cat > CONTEXT.md << 'EOF'
# CONTEXT.md - Dental SaaS (Alex Bot)

## Project Overview
- **Name:** Dental SaaS (Alex bot)
- **Purpose:** AI-driven receptionist for dental clinics via Telegram
- **Repository:** github.com/Jaoluka3/backend-saas-odonto
- **Deploy:** Render.com (backend-saas-odonto)

## Stack
- **Backend:** Python 3.x, FastAPI
- **Database:** Supabase (PostgreSQL)
- **AI/LLM:** NVIDIA LLaMA 3.1 (via nvidia.com API)
- **Bot:** pyTelegramBotAPI (Telebot)
- **Deployment:** Render (GitHub auto-deploy)

## Status: 🔴 3 CRITICAL ISSUES FOUND
See ANALISE_CRITICA.md for details
EOF
```

---

### 2. ✅ Validar Startup (falhar rápido)
Editar `main.py` - adicionar validation ao início:

```python
# main.py - linhas 1-20 (ADICIONAR ANTES DE IMPORTS)
import os
import sys
from pathlib import Path

# Validar todas as chaves obrigatórias ANTES de iniciar
REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "SUPABASE_URL", 
    "SUPABASE_KEY",
    "SERPAPI_KEY",
    "NVIDIA_API_KEY",
]

missing = [k for k in REQUIRED_VARS if not os.environ.get(k)]
if missing:
    print(f"\n🚨 ERRO CRÍTICO: Variáveis não definidas:")
    for var in missing:
        print(f"   ❌ {var}")
    sys.exit(1)

print("✅ Todas as variáveis de ambiente validadas")
```

---

### 3. 🔒 Documentar Decisão Gemini → NVIDIA
Editar `DECISIONS.md`:

```markdown
# DECISIONS.md

## [2024-05-04] - AI Engine: NVIDIA LLaMA 3.1 (MUDOU DE GEMINI)
- **Context:** Inicial: Gemini 2.0 Flash, depois migrado para NVIDIA
- **Choice:** NVIDIA LLaMA 3.1 via https://integrate.api.nvidia.com/v1/chat/completions
- **Razão da mudança:** [TODO: DOCUMENTAR AQUI]
  - [ ] Custo menor?
  - [ ] Latência menor?
  - [ ] Taxa limite maior?
  - [ ] Outra razão?
- **Impacto:** `bot_telegram.py:gerar_resposta_ia()`
- **Fallback:** Se API cair, retorna mensagem genérica (PODE MELHORAR)
```

---

### 4. 🧵 Corrigir Thread Lock
Editar `agente_orquestrador.py` - substituir a função:

```python
# ANTES (linhas 57-82):
def rodar_pipeline_async() -> dict:
    """Dispara a pipeline em thread separada e retorna imediatamente.
    Usa Lock para impedir execucoes concorrentes."""
    if not _pipeline_lock.acquire(blocking=False):
        logger.warning("Pipeline ja esta em execucao...")
        return {"status": "ocupado", ...}
    
    run_id = str(uuid.uuid4())[:8]
    
    def _executar_com_lock():
        try:
            rodar_pipeline(run_id)
        finally:
            _pipeline_lock.release()
    
    t = threading.Thread(target=_executar_com_lock, daemon=True)
    t.start()
    return {"run_id": run_id, "status": "iniciado", ...}

# DEPOIS (USAR ISTO):
def rodar_pipeline_async() -> dict:
    """Dispara a pipeline em thread separada com timeout de 5s para lock."""
    acquired = _pipeline_lock.acquire(timeout=5)
    if not acquired:
        logger.warning("Pipeline ja em execucao (timeout 5s)")
        return {
            "status": "ocupado",
            "mensagem": "Pipeline já está em execução. Aguarde e tente novamente.",
        }
    
    run_id = str(uuid.uuid4())[:8]
    
    def _executar_com_lock():
        try:
            logger.info("Pipeline [%s] iniciada em background", run_id)
            rodar_pipeline(run_id)
        except Exception as e:
            logger.error("Pipeline [%s] falhou: %s", run_id, e)
        finally:
            _pipeline_lock.release()
            logger.info("Pipeline [%s] finalizada, lock liberado", run_id)
    
    t = threading.Thread(target=_executar_com_lock, daemon=True, name=f"Pipeline-{run_id}")
    t.start()
    logger.info("Pipeline [%s] disparada em background", run_id)
    return {
        "run_id": run_id,
        "status": "iniciado",
        "mensagem": "Pipeline rodando em background. Use GET /agentes/status para acompanhar.",
    }
```

---

### 5. ✍️ Validar Telefone
Editar `bot_telegram.py` - substituir função:

```python
# ANTES (linhas 68-72):
def _extrair_telefone(message):
    if message.contact and message.contact.phone_number:
        return message.contact.phone_number
    return str(message.chat.id)  # ❌ PROBLEMA

# DEPOIS:
def _extrair_telefone(message):
    """Extrai telefone do contato compartilhado.
    Retorna None se não disponível (força usuário compartilhar)."""
    if message.contact and message.contact.phone_number:
        return message.contact.phone_number
    logger.warning("Usuário %s não compartilhou contato", message.chat.id)
    return None  # Não usar chat_id como fallback!
```

Agora editar função que usa isso:
```python
# Em handle_text() ou equivalente:
telefone = _extrair_telefone(message)
if not telefone:
    bot.send_message(
        message.chat.id,
        "📱 Por favor, compartilhe seu telefone para que eu possa ajudar melhor!\n"
        "Use o botão 📱 de contato ou digite seu número manualmente."
    )
    return  # Não prosseguir sem telefone
```

---

### 6. 💨 Validar SerpAPI no Startup
Editar `agente_buscador.py` - adicionar validação no início:

```python
# ANTES (linha 13):
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

# DEPOIS:
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
if not SERPAPI_KEY:
    logger.error("❌ SERPAPI_KEY não definida!")
    raise SystemExit("Erro: SERPAPI_KEY não configurada nas variáveis de ambiente")
```

---

## 📋 Checklist de Verificação

Após aplicar as correções acima:

```bash
# 1. CONTEXT.md foi limpo?
[ ] git diff CONTEXT.md | grep -c "Last Sync" == 0

# 2. Startup falha sem variáveis?
[ ] python3 main.py  # (sem SERPAPI_KEY deve falhar)

# 3. Lock pode lidar com crash?
[ ] python3 -m pytest test_critical.py::test_pipeline_lock_doesnt_deadlock

# 4. Telefone validado?
[ ] Testar bot sem compartilhar contato (deve pedir)

# 5. DECISIONS.md foi atualizado?
[ ] git diff DECISIONS.md | grep "NVIDIA\|MUDOU"

# 6. Deploy testa variáveis?
[ ] Render deploy log mostra ✅ validation
```

---

## 🚀 Deploy Seguro

Após fixes, fazer deploy limpo:

```bash
# 1. Backup remoto
git tag -a v-backup-$(date +%s) -m "Before critical fixes"
git push origin --tags

# 2. Commit das correções
git add ANALISE_CRITICA.md CONTEXT.md main.py agente_orquestrador.py bot_telegram.py agente_buscador.py
git commit -m "🚨 FIX: Corrigir 3 erros críticos (lock, obsidian, validation)"
git push origin main

# 3. Monitorar Render deploy
# Ir para: https://dashboard.render.com/services/backend-saas-odonto-api
# Verificar se ambos os workers startam sem erro
```

---

## ❓ Perguntas para Responder

**Antes de fazer merge:**

1. Por que mudou de Gemini para NVIDIA LLaMA?
   - Documentar razão em DECISIONS.md
   
2. Qual é o custo mensal esperado?
   - NVIDIA: Quantos requests/mês?
   - Gemini: Qual era o limite anterior?
   
3. Quando último teste foi feito?
   - Testar `/lead` endpoint
   - Testar bot no Telegram
   - Testar buscas com SerpAPI
   
4. Backups do banco de dados?
   - Supabase está com backups diários?
   - Há plano de recuperação de desastres?

---

## 📞 Próximos Passos

- [ ] Fase 1: Parar vazamentos (30 min)
- [ ] Fase 2: Documentar decisões (45 min)  
- [ ] Fase 3: Corrigir lock (60 min)
- [ ] Fase 4: Validações (30 min)
- [ ] Deploy e monitorar (15 min)

**Total: ~2.5 horas de trabalho**

---

**Arquivo gerado:** 18 de maio de 2026  
**Status:** ⏳ Aguardando execução das correções
