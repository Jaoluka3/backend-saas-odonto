#!/usr/bin/env python3
"""
DevAgent ReAct — Loop autônomo Android/Termux.
Arquitetura ReAct (Reasoning + Acting) com parsing determinístico.

Uso:
    python3 dev_agent_eco.py "seu objetivo aqui"
    python3 dev_agent_eco.py  # modo interativo
"""

import sys
import json
import subprocess
import os
import time

SYSTEM_PROMPT = """
Voce e o DevAgent, uma Inteligencia Artificial Autonoma de nivel Senior.
Seu ambiente de execucao e um terminal Linux (Termux) rodando nativamente em um dispositivo Android.
Sua missao e resolver o objetivo do usuario de forma autonoma e silenciosa, utilizando as ferramentas disponiveis.

=== RECURSOS E LIMITACOES ===
1. Voce tem acesso root indireto ao Android atraves do Shizuku usando o prefixo:
   `export RISH_APPLICATION_ID="com.termux" && sh ~/rish -c "COMANDO_AQUI"`
2. Ferramentas de Midia: ffmpeg instalado para edicao de video e audio.
3. Ferramentas de UI: uiautomator dump para ler a estrutura XML da tela atual e encontrar coordenadas X,Y de botoes.
4. Input de Tela: input tap X Y, input swipe X1 Y1 X2 Y2 Tempo, input text 'seu_texto'.
5. Voce nao tem acesso a um navegador web interativo. Toda extracao de dados deve ser feita via cURL ou APIs no terminal.

=== REGRAS ESTRITAS DE SAIDA ===
Sua resposta deve conter SEMPRE, e APENAS, dois blocos de texto perfeitamente formatados.
Nunca use formatacao Markdown, nunca adicione conversas, saudacoes ou explicacoes fora das tags.
Siga EXATAMENTE esta estrutura:

[PENSAMENTO]
Escreva aqui o seu raciocinio logico em uma linha. O que a ultima saida do terminal mostrou?
[COMANDO]
Escreva aqui EXATAMENTE a linha de comando bash que o terminal deve executar.
Se o objetivo final foi completamente atingido e confirmado, escreva a palavra FINALIZAR.

=== EXEMPLO ===
[PENSAMENTO] Preciso abrir o aplicativo do TikTok para comecar a missao de postagem.
[COMANDO] export RISH_APPLICATION_ID="com.termux" && sh ~/rish -c "monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1"

=== OBJETIVO ATUAL ===
{objetivo}
"""

API_KEY = os.environ.get("NVIDIA_API_KEY", "")
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "deepseek-ai/deepseek-v4-flash"

MAX_STEPS = 50
LOOP_DELAY = 2.0
TERMUX_HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
LOG_DIR = os.path.join(TERMUX_HOME, ".termux")
LOG_FILE = os.path.join(LOG_DIR, "devagent.log")


def log_event(message):
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def pensar(historico):
    payload = {
        "model": MODEL,
        "messages": historico,
        "max_tokens": 512,
        "temperature": 0.3
    }
    log_event(f"API request: {len(historico)} messages, model={MODEL}")

    if not API_KEY:
        print("❌ NVIDIA_API_KEY nao configurada")
        sys.exit(1)

    cmd = [
        "curl", "-s", API_URL,
        "-H", f"Authorization: Bearer {API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload)
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout)
        content = data["choices"][0]["message"]["content"]
        log_event(f"API response: {len(content)} chars")
        return content
    except json.JSONDecodeError as e:
        log_event(f"API JSON error: {e} | raw: {r.stdout[:500]}")
        return "[PENSAMENTO] Erro na API\n[COMANDO] echo 'API_ERROR'"
    except subprocess.TimeoutExpired:
        log_event("API timeout")
        return "[PENSAMENTO] Timeout na API\n[COMANDO] echo 'API_TIMEOUT'"
    except Exception as e:
        log_event(f"API error: {e}")
        return "[PENSAMENTO] Erro generico na API\n[COMANDO] echo 'API_ERROR'"


def parsear_resposta(texto):
    pensamento = ""
    comando = ""
    try:
        partes = texto.split("[COMANDO]")
        if len(partes) > 1:
            pensamento = partes[0].replace("[PENSAMENTO]", "").replace("[PENSAMENTO]", "").strip()
            comando = partes[1].strip()
            pensamento = " ".join(pensamento.split())
        else:
            pensamento = "Falha no parsing: tag [COMANDO] nao encontrada"
            comando = "echo 'ERRO DE SINTAXE: Use estritamente [PENSAMENTO] e [COMANDO]'"
    except Exception as e:
        pensamento = f"Erro de parsing: {e}"
        comando = "echo 'ERRO DE SINTAXE'"
    return pensamento, comando


def executar_comando(comando):
    log_event(f"Executando: {comando[:200]}")
    try:
        r = subprocess.run(
            ["bash", "-c", comando],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": TERMUX_HOME}
        )
        saida = r.stdout.strip() if r.stdout else ""
        erro = r.stderr.strip() if r.stderr else ""
        log_event(f"Exit: {r.returncode}, stdout: {len(saida)} chars, stderr: {len(erro)} chars")
        return saida, erro, r.returncode
    except subprocess.TimeoutExpired:
        log_event("COMANDO TIMEOUT")
        return "", "TIMEOUT: comando excedeu 120s", -1
    except Exception as e:
        log_event(f"COMANDO ERROR: {e}")
        return "", str(e), -1


def main():
    if not API_KEY:
        print("❌ Configure NVIDIA_API_KEY no ambiente")
        print("   export NVIDIA_API_KEY='nvapi-sua-chave-aqui'")
        sys.exit(1)

    objetivo = sys.argv[1] if len(sys.argv) > 1 else input("Objetivo: ")
    objetivo = objetivo.strip()
    if not objetivo:
        print("❌ Nenhum objetivo definido")
        sys.exit(1)

    log_event(f"=== DevAgent iniciado ===")
    log_event(f"Objetivo: {objetivo}")

    historico = [
        {"role": "system", "content": SYSTEM_PROMPT.format(objetivo=objetivo)}
    ]

    print(f"\n{'='*50}")
    print(f"🤖 DevAgent ReAct")
    print(f"🎯 Objetivo: {objetivo}")
    print(f"🧠 Modelo: {MODEL}")
    print(f"📝 Log: {LOG_FILE}")
    print(f"{'='*50}\n")

    for passo in range(1, MAX_STEPS + 1):
        print(f"\n⚡ Passo {passo}/{MAX_STEPS}")
        print(f"🤔 Pensando...", end=" ", flush=True)

        resposta = pensar(historico)
        pensamento, comando = parsear_resposta(resposta)

        print(f"\n🧠 {pensamento}")
        print(f"⌨️  {comando}")

        if comando == "FINALIZAR":
            print(f"\n{'='*50}")
            print("✅ Objetivo concluido com sucesso!")
            print(f"{'='*50}")
            log_event("Objetivo concluido com sucesso")
            historico.append({"role": "assistant", "content": resposta})
            break

        historico.append({"role": "assistant", "content": resposta})

        saida, erro, code = executar_comando(comando)

        if code == 0 and saida:
            print(f"📤 Saida ({len(saida)} chars):\n{saida[:500]}")
        elif erro:
            print(f"❌ Erro: {erro[:300]}")

        if code != 0:
            historico.append({
                "role": "user",
                "content": f"COMANDO FALHOU (exit={code}):\nSTDERR: {erro[:1000]}\nSTDOUT: {saida[:500]}"
            })
        else:
            historico.append({
                "role": "user",
                "content": f"COMANDO EXECUTADO (exit=0):\nSTDOUT: {saida[:2000]}"
            })

        # Verificar se o historico esta crescendo demais (limite de contexto)
        total_chars = sum(len(m["content"]) for m in historico)
        if total_chars > 20000:
            log_event(f"Contexto grande ({total_chars} chars), compactando...")
            historico = [historico[0]] + historico[-4:]

        time.sleep(LOOP_DELAY)

    else:
        print(f"\n⚠️  Limite de {MAX_STEPS} passos atingido sem conclusao")
        log_event(f"Limite de {MAX_STEPS} passos atingido")

    print(f"\n📝 Log salvo em: {LOG_FILE}")


if __name__ == "__main__":
    main()
