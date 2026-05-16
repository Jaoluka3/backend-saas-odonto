import time
import threading
from datetime import datetime
import schedule

import agente_buscador
import agente_qualificador
import agente_contato
import agente_followup

ultima_execucao = None
proxima_execucao = "09:00 (diario)"
ultimo_resultado = {}


def rodar_pipeline() -> dict:
    global ultima_execucao, ultimo_resultado
    inicio = datetime.now()
    print(f"\n=== PIPELINE INICIADO {inicio.isoformat()} ===")

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

        print(f"\n=== RESUMO DA PIPELINE ===")
        print(f"Clinicas encontradas: {r_busca}")
        print(f"Qualificadas: {r_qualif.get('qualificadas', 0)}")
        print(f"Descartadas: {r_qualif.get('descartadas', 0)}")
        print(f"Contactadas: {r_contato}")
        print(f"Followups enviados: {r_follow.get('followups_enviados', 0)}")
        print(f"Inativados: {r_follow.get('inativados', 0)}")
        print(f"=== PIPELINE FINALIZADA {(datetime.now() - inicio).seconds}s ===\n")

        ultima_execucao = inicio.isoformat()
        ultimo_resultado = resultado
        return resultado

    except Exception as e:
        print(f"Erro na pipeline: {e}")
        return {"error": str(e)}


schedule.every().day.at("09:00").do(rodar_pipeline)


def iniciar_agendador():
    print(f"Agendador iniciado. Proxima execucao: {proxima_execucao}")
    while True:
        schedule.run_pending()
        time.sleep(60)


threading.Thread(target=iniciar_agendador, daemon=True).start()

if __name__ == "__main__":
    rodar_pipeline()
