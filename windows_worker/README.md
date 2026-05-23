# Worker Local — Google Maps Scraper (Windows)

Script standalone de prospeccao odontologica que varre o Google Maps
via scrapling (StealthyFetcher + Camoufox) e injeta direto no Supabase.

## Setup (Windows)

### 1. Instalar Python 3.12+

https://www.python.org/downloads/

### 2. Instalar scrapling + dependencias

```powershell
# Clone ou copie este diretorio para o Windows
cd windows_worker

# Criar venv
python -m venv venv
venv\Scripts\activate

# Instalar
pip install "scrapling[fetchers]" supabase python-dotenv

# Baixar browsers (Chromium + Camoufox)
scrapling install
```

### 3. Configurar .env

```powershell
copy .env.example .env
# Editar .env com SUPABASE_URL e SUPABASE_KEY reais
notepad .env
```

### 4. Rodar

```powershell
# Modo headless (padrao)
python scraper_local.py

# Modo visivel (debug — util para CAPTCHA manual)
python scraper_local.py --visible

# Apenas extrair sem injetar no Supabase
python scraper_local.py --json-only

# Salvar resultado em JSON
python scraper_local.py --salvar-json
```

## Funcionamento

O script:
1. Abre Google Maps como usuario humano (Camoufox + fingerprint realista)
2. Pesquisa por "clinica odontologica Betim, MG"
3. Faz scroll humano no painel lateral ate o fim da lista
4. Extrai: nome, telefone, endereco, website, avaliacao Google
5. Faz upsert no Supabase em batches de 20 (on_conflict=pelo telefone)
6. Gera relatorio de quantos inseriu/atualizou

## Solucao de Problemas

| Problema | Solucao |
|----------|---------|
| CAPTCHA | Rodar com `--visible` e resolver manualmente |
| "scrapling nao encontrado" | `pip install "scrapling[fetchers]"` |
| Browser nao abre | `scrapling install --force` |
| "Supabase nao configurado" | Verificar `.env` — precisa de `SUPABASE_URL` + `SUPABASE_KEY` |
| 0 registros extraidos | Rodar `--visible` para ver o que carregou. Google pode ter mudado selectores. |