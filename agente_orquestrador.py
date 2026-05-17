import time
import uuid
import logging
import threading
from datetime import datetime
import schedule

import agente_buscador
import agente_qualificador
import agente_contato
import agente_followup

logger = logging.getLogger(__name__)

ultima_execucao = None
proxima_execucao = "09:00 (diario)"
ultimo_resultado = {}
_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()


def rodar_pipeline() -> dict:
    """Executa a pipeline completa de aquisicao de clientes."""
    global ultima_execucao, ultimo_resultado
    run_id = str(uuid.uuid4())[:8]
    inicio = datetime.now()
    logger.info("=== PIPELINE [%s] INICIADA %s ===", run_id, inicio.isoformat())

    try:
        r_busca = agente_buscador.rodar()
        r_qualif = agente_qualificador.rodar()
        r_contato = agente_contato.rodar()
        r_follow = agente_followup.rodar()

        resultado = {
            "run_id": run_id,
            "timestamp": inicio.isoformat(),
            "buscador": {"inseridas": r_busca},
            "qualificador": r_qualif,
            "contato": {"contactadas": r_contato},
            "followup": r_follow,
        }

        logger.info("=== RESUMO DA PIPELINE [%s] ===", run_id)
        logger.info("Clinicas encontradas: %d", r_busca)
        logger.info("Qualificadas: %d", r_qualif.get("qualificadas", 0))
        logger.info("Descartadas: %d", r_qualif.get("descartadas", 0))
        logger.info("Contactadas: %d", r_contato)
        logger.info("Followups: %d", r_follow.get("followups_enviados", 0))
        logger.info("Inativados: %d", r_follow.get("inativados", 0))

        duracao = (datetime.now() - inicio).seconds
        logger.info("=== PIPELINE [%s] FINALIZADA em %ds ===", run_id, duracao)

        ultima_execucao = inicio.isoformat()
        ultimo_resultado = resultado
        return resultado
    except Exception as e:
        logger.error("Erro na pipeline [%s]: %s", run_id, e)
        return {"run_id": run_id, "error": str(e)}


def rodar_pipeline_async() -> dict:
    """Dispara a pipeline em thread separada e retorna imediatamente."""
    t = threading.Thread(target=rodar_pipeline, daemon=True)
    t.start()
    run_id = str(uuid.uuid4())[:8]
    logger.info("Pipeline [%s] disparada em background", run_id)
    return {
        "run_id": run_id,
        "status": "iniciado",
        "mensagem": "Pipeline rodando em background. Use GET /agentes/status para acompanhar.",
    }


def _loop_agendador():
    """Loop do scheduler que roda em thread separada."""
    logger.info("Agendador iniciado. Proxima execucao: %s", proxima_execucao)
    while not _scheduler_stop.is_set():
        schedule.run_pending()
        _scheduler_stop.wait(60)


def iniciar_agendador():
    """Inicia o scheduler em thread daemon com controle de parada."""
    global _scheduler_thread
    # Evita duplicacao se ja estiver rodando
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.warning("Agendador ja esta rodando")
        return
    # Garante que o job seja registrado apenas uma vez
    schedule.clear()
    schedule.every().day.at("09:00").do(rodar_pipeline)
    _scheduler_thread = threading.Thread(target=_loop_agendador, daemon=True)
    _scheduler_thread.start()
    logger.info("Agendador iniciado em thread separada")


def parar_agendador():
    """Para o scheduler graceful."""
    _scheduler_stop.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
        logger.info("Agendador parado")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    try:
        iniciar_agendador()
        rodar_pipeline()
    except KeyboardInterrupt:
        parar_agendador()
