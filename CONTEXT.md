# CONTEXT.md - Dental SaaS

## Project Overview
- **Name:** Dental SaaS (Alex bot)
- **Core Purpose:** AI-driven receptionist for dental clinics via Telegram
- **Repository:** github.com/Jaoluka3/backend-saas-odonto
- **Deploy:** Render.com (backend-saas-odonto)

## Stack
- **Backend:** Python 3.x, FastAPI
- **Database:** Supabase (PostgreSQL)
- **AI/LLM:** NVIDIA LLaMA 3.1 (via nvidia.com API)
- **Bot:** pyTelegramBotAPI (Telebot)
- **Deployment:** Render (GitHub auto-deploy)
- **Knowledge:** Obsidian Vault + Graphify

## Current Status
- **Last updated:** 19/05/2026
- **Status:** 3 Critical Issues Fixed (deadlock, obsidian loop, validation)
- **Backend:** Deployed and running on Render
- **Bot Alex:** Online no Telegram
- **API Health:** `/health` endpoint returns "Cerebro IA Online e Conectado"

## Known Issues (from post-fix analysis)
1. **Hardcoded Fallbacks:** `bot_telegram.py` uses hardcoded fallback response, lacks robust error handling for AI API failures
2. **Environment Configuration:** `API_URL` defaults to localhost, may fail in production if not set in Render env vars
3. **Unused AI Keys:** Multiple `OPENROUTER_KEY` variables loaded but not used in failover logic
4. **Limited Logging:** Minimal production logging; relies on basic `print` statements
