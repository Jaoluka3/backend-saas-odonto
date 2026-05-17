import time
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
_scheduler_thread = None
_scheduler_stop = threading.Event()


def rodar_pipeline() -> dict:
    """Executa a pipeline completa de aquisicao de clientes."""
    global ultima_execucao, ultimo_resultado
    inicio = datetime.now()
    logger.info("=== PIPELINE INICIADA %s ===", inicio.isoformat())

    try:
        r_busca = agente_buscador.rodar()
        r_qualif = agente_qualificador.rodar()
        r_contato = agente_contato.rodar()
        r_follow = agente_followup.rodar()

        resultado = {
            "timestamp": inicio.isoformat(),
            "buscador": {"inseridas": r_busca},
            "qualificador": r_qualif,
            "contato": {"contactadas": r_contato},
            "followup": r_follow,
        }

        logger.info("=== RESUMO DA PIPELINE ===")
        logger.info("Clinicas encontradas: %d", r_busca)
        logger.info("Qualificadas: %d", r_qualif.get("qualificadas", 0))
        logger.info("Descartadas: %d", r_qualif.get("descartadas", 0))
        logger.info("Contactadas: %d", r_contato)
        logger.info("Followups enviados: %d", r_follow.get("followups_enviados", 0))
        logger.info("Inativados: %d", r_follow.get("inativados", 0))
        duracao = (datetime.now() - inicio).seconds
        logger.info("=== PIPELINE FINALIZADA em %ds ===", duracao)

        ultima_execucao = inicio.isoformat()
        ultimo_resultado = resultado
        return resultado

    except Exception as e:
        logger.error("Erro na pipeline: %s", e)
        return {"error": str(e)}


def _loop_agendador():
    """Loop do scheduler que roda em thread separada."""
    logger.info("Agendador iniciado. Proxima execucao: %s", proxima_execucao)
    while not _scheduler_stop.is_set():
        schedule.run_pending()
        _scheduler_stop.wait(60)


def iniciar_agendador():
    """Inicia o scheduler em thread daemon com controle de parada."""
    global _scheduler_thread
    schedule.every().day.at("09:00").do(rodar_pipeline)
    _scheduler_thread = threading.Thread(target=_loop_agendador, daemon=True)
    _scheduler_thread.start()


def parar_agendador():
    """Para o scheduler graceful."""
    _scheduler_stop.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
        logger.info("Agendador parado")


# Inicia automaticamente ao importar
iniciar_agendador()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        rodar_pipeline()
    except KeyboardInterrupt:
        parar_agendador()
