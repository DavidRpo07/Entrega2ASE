"""Mock del sistema externo SAP: recibe las notificaciones del worker.

Punto de falla ext_sap.notificar (D2: responde 503 en un % de llamadas).
SAP_LATENCIA_MS fija la latencia base de una respuesta sana.
"""
import time

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app import admin_fallas, config, metricas, telemetria
from lab.fallas.inyector import INYECTOR

telemetria.configurar("ext-sap")

app = FastAPI(title="Mock ext-sap")
admin_fallas.instalar(app)
metricas.instalar_http(app)
metricas.registrar_colectores()
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
recibidas = 0


@app.post("/notificar")
def notificar(evento: dict):
    global recibidas
    INYECTOR.punto("ext_sap.notificar", clave=str(evento.get("orden_id")))
    time.sleep(config.SAP_LATENCIA_MS / 1000.0)
    recibidas += 1
    return {"ack": True, "orden_id": evento.get("orden_id")}


@app.get("/health")
def health():
    return {"status": "ok", "instancia": config.INSTANCIA, "recibidas": recibidas}
