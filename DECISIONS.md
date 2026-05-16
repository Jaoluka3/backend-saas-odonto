# DECISIONS.md - Architectural Decisions Log

## [2024-05-04] - FastAPI + Supabase Stack
- **Context:** Need lightweight backend for dental clinic leads management
- **Choice:** FastAPI for REST API + Supabase for PostgreSQL
- **Alternatives rejected:** Django (overkill), Flask (less features), MongoDB (different use case)
- **Impact:** `main.py`, `bot_telegram.py` integration

## [2024-05-04] - AI Engine: Gemini 2.0 Flash
- **Context:** Need low-latency AI responses for Alex bot
- **Choice:** Gemini 2.0 Flash via Google Generative Language API
- **Alternatives rejected:** OpenAI (expensive), Claude (slower), Local LLMs (no GPU)
- **Impact:** `bot_telegram.py:gerar_resposta_ia()`

## [2024-05-04] - Knowledge: Graphify + Obsidian
- **Context:** Project info spread across 73+ Obsidian documents
- **Choice:** Graphify for knowledge graph, Obsidian for sync
- **Alternatives rejected:** Simple grep (no relationships), manual docs (outdated fast)
- **Impact:** `graphify-out/`, `sync_to_obsidian.sh`

## [2024-05-04] - Deployment: Render via GitHub
- **Context:** Need reliable auto-deploy for Python backend
- **Choice:** Render.com with GitHub integration
- **Alternatives rejected:** Vercel (limited Python), Fly.io (less familiar), Heroku (expensive)
- **Impact:** `render.yaml`, `Procfile`, `runtime.txt`
