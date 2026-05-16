#!/bin/bash
# check_daemon.sh - Verifica se watch_sync.py esta rodando e reinicia se necessario

set -e

LOG_DIR="${HOME}/.termux"
LOG_FILE="${LOG_DIR}/daemon.log"
PID_FILE="${LOG_DIR}/watch_sync.pid"
WATCH_SCRIPT="${HOME}/meu-backend/watch_sync.py"

mkdir -p "${LOG_DIR}"

log() {
    echo "[$(date)] $1" | tee -a "${LOG_FILE}"
}

echo "=== Daemon check started at $(date) ===" >> "${LOG_FILE}"

# Verifica se PID existe
if [ ! -f "${PID_FILE}" ]; then
    log "PID file not found, starting daemon..."
    cd "${HOME}/meu-backend"
    nohup python3 -u "${WATCH_SCRIPT}" >> "${LOG_FILE}" 2>&1 &
    NEW_PID=$!
    echo "${NEW_PID}" > "${PID_FILE}"
    log "Daemon started (new PID: ${NEW_PID})"
    echo "SUCCESS: Daemon started with PID ${NEW_PID}"
    exit 0
fi

PID=$(cat "${PID_FILE}")

# Verifica se processo esta vivo
if kill -0 "${PID}" 2>/dev/null; then
    log "Daemon running normally (PID: ${PID})"
    echo "SUCCESS: Daemon running (PID: ${PID})"
    exit 0
else
    log "Daemon dead, restarting..."
    cd "${HOME}/meu-backend"
    nohup python3 -u "${WATCH_SCRIPT}" >> "${LOG_FILE}" 2>&1 &
    NEW_PID=$!
    echo "${NEW_PID}" > "${PID_FILE}"
    log "Daemon restarted (new PID: ${NEW_PID})"
    echo "SUCCESS: Daemon restarted with PID ${NEW_PID}"
    exit 0
fi