import time
import uuid
import logging
import threading
from datetime import datetime
from typing import Optional
import schedule

import agente_buscador
import agente_qualificador
import agente_email_resolver
import agente_contato
import agente_followup

logger = logging.getLogger(__name__)

ultima_execucao = None
proxima_execucao = "09:00 (diario)"
ultimo_resultado = {}
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()
_pipeline_lock = threading.Lock()


_TIMEOUT_PIPELINE = 900  # 15 minutos


def rodar_pipeline(run_id: Optional[str] = None) -> dict:
    """Executa a pipeline completa de aquisicao de clientes.
    Timeout global de 15 minutos para evitar lock preso."""
    global ultima_execucao, ultimo_resultado
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]
    inicio = datetime.now()
    logger.info("=== PIPELINE [%s] INICIADA %s ===", run_id, inicio.isoformat())

    try:
        def _verificar_timeout():
            if int((datetime.now() - inicio).total_seconds()) > _TIMEOUT_PIPELINE:
                raise TimeoutError(
                    f"Pipeline [{run_id}] excedeu {_TIMEOUT_PIPELINE}s"
                )

        _verificar_timeout()
        r_busca = agente_buscador.rodar()

        _verificar_timeout()
        r_qualif = agente_qualificador.rodar()

        _verificar_timeout()
        r_emails = agente_email_resolver.rodar()

        _verificar_timeout()
        r_contato = agente_contato.rodar()

        _verificar_timeout()
        r_follow = agente_followup.rodar()

        duracao = int((datetime.now() - inicio).total_seconds())
        resultado = {
            "run_id": run_id,
            "timestamp": inicio.isoformat(),
            "duracao_segundos": duracao,
            "buscador": {"inseridas": r_busca},
            "qualificador": r_qualif,
            "email_resolver": r_emails,
            "contato": {"contactadas": r_contato},
            "followup": r_follow,
        }

        logger.info("=== RESUMO DA PIPELINE [%s] ===", run_id)
        logger.info("Clinicas encontradas: %d", r_busca)
        logger.info("Qualificadas: %d", r_qualif.get("qualificadas", 0))
        logger.info("Descartadas: %d", r_qualif.get("descartadas", 0))
        logger.info("Emails resolvidos: %d", r_emails.get("resolvidos", 0))
        logger.info("Sem website: %d", r_emails.get("sem_website", 0))
        logger.info("Nao encontrados: %d", r_emails.get("nao_encontrados", 0))
        logger.info("Contactadas: %d", r_contato)
        logger.info("Followups: %d", r_follow.get("followups_enviados", 0))
        logger.info("Inativados: %d", r_follow.get("inativados", 0))
        logger.info("Duracao: %ds", duracao)
        logger.info("=== PIPELINE [%s] FINALIZADA ===", run_id)

        ultima_execucao = inicio.isoformat()
        ultimo_resultado = resultado
        return resultado
    except TimeoutError:
        erro = {"run_id": run_id, "error": "timeout", "timestamp": inicio.isoformat()}
        ultima_execucao = inicio.isoformat()
        ultimo_resultado = erro
        logger.error("Pipeline [%s] excedeu timeout de %ds", run_id, _TIMEOUT_PIPELINE)
        return erro
    except Exception as e:
        erro = {"run_id": run_id, "error": str(e), "timestamp": inicio.isoformat()}
        ultima_execucao = inicio.isoformat()
        ultimo_resultado = erro
        logger.error("Erro na pipeline [%s]: %s", run_id, e, exc_info=True)
        return erro


def rodar_pipeline_async() -> dict:
    """Dispara a pipeline em thread separada com timeout de 5s no lock.
    Evita deadlock permanente em caso de crash na thread."""
    try:
        acquired = _pipeline_lock.acquire(timeout=5.0)
    except Exception as e:
        logger.error("Erro ao adquirir lock: %s", e)
        return {"status": "erro", "mensagem": "Erro interno ao adquirir lock."}

    if not acquired:
        logger.warning("Pipeline ja esta em execucao (timeout 5s)")
        return {
            "status": "ocupado",
            "mensagem": "Pipeline ja esta em execucao. Aguarde e tente novamente.",
        }

    run_id = str(uuid.uuid4())[:8]

    def _executar_com_lock():
        try:
            logger.info(">>> Pipeline [%s] iniciada com lock", run_id)
            rodar_pipeline(run_id)
            logger.info("<<< Pipeline [%s] finalizada com sucesso", run_id)
        except Exception as e:
            logger.error("❌ Pipeline [%s] falhou: %s", run_id, e)
        finally:
            try:
                _pipeline_lock.release()
                logger.info("🔓 Lock liberado apos pipeline [%s]", run_id)
            except Exception as e:
                logger.error("❌ Erro ao liberar lock: %s", e)

    t = threading.Thread(
        target=_executar_com_lock,
        daemon=True,
        name=f"Pipeline-{run_id}"
    )
    t.start()
    logger.info("Pipeline [%s] disparada em background com lock timeout=5.0s", run_id)
    return {
        "run_id": run_id,
        "status": "iniciado",
        "mensagem": "Pipeline rodando em background. Use GET /agentes/status para acompanhar.",
    }


def _rodar_pipeline_agendada():
    """Wrapper para o scheduler usar rodar_pipeline_async (que tem lock).
    Previne execucao concorrente com chamadas manuais via API."""
    logger.info("Disparo agendado das 09:00 — usando rodar_pipeline_async")
    resultado = rodar_pipeline_async()
    if resultado.get("status") != "iniciado":
        logger.error("Pipeline agendada falhou: %s", resultado)


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
    schedule.every().day.at("09:00").do(_rodar_pipeline_agendada)
    _scheduler_thread = threading.Thread(target=_loop_agendador, daemon=True)
    _scheduler_thread.start()
    logger.info("Agendador iniciado em thread separada")


def parar_agendador():
    """Para o scheduler graceful."""
    _scheduler_stop.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
        logger.info("Agendador parado")


def status() -> dict:
    """Retorna status atual da pipeline."""
    em_execucao = _pipeline_lock.locked()
    return {
        "ultima_execucao": ultima_execucao,
        "proximo_agendamento": proxima_execucao,
        "em_execucao": em_execucao,
        "ultimo_resultado": ultimo_resultado,
    }


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
