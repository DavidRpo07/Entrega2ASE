"""Worker del outbox: publica ordenes.outbox_evento hacia ext-sap.

- Toma lotes con FOR UPDATE SKIP LOCKED (varios workers no se pisan).
- Por cada evento llama POST ext-sap/notificar; si responde 2xx marca el evento
  publicado y la orden pasa de PENDIENTE a CONFIRMADA.
- Si una llamada falla, el lote se corta: lo ya publicado se confirma y el resto
  queda pendiente para el siguiente ciclo (sin reintentos ni circuit breaker:
  esas correcciones son la fase 4).
- Punto de falla worker.outbox (C2): mientras esté pausado no consume.
- Observabilidad: métricas en :9100/metrics (outbox_pendientes, outbox_lag_segundos…)
  y un span por evento que continúa la traza del POST /ordenes que lo creó.
"""
import logging
import os
import signal
import threading
import time

import httpx
from opentelemetry import propagate
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import Gauge, start_http_server

from app import config, db, metricas, telemetria
from lab.fallas.inyector import INYECTOR

TRACER = telemetria.configurar("outbox-worker")
log = logging.getLogger("worker")

SQL_LOTE = """
    SELECT outbox_id, aggregate_id, payload FROM ordenes.outbox_evento
    WHERE NOT publicado ORDER BY outbox_id LIMIT %s FOR UPDATE SKIP LOCKED
"""
SQL_PUBLICADO = "UPDATE ordenes.outbox_evento SET publicado = true, fecha_publicacion = now() WHERE outbox_id = %s"
SQL_CONFIRMAR = "UPDATE ordenes.orden_compra SET estado = 'CONFIRMADA' WHERE orden_id = %s AND estado = 'PENDIENTE'"
SQL_LAG = ("SELECT count(*), COALESCE(EXTRACT(EPOCH FROM now() - min(fecha_creacion)), 0) "
           "FROM ordenes.outbox_evento WHERE NOT publicado")

OUTBOX_PENDIENTES = Gauge("outbox_pendientes", "Eventos del outbox sin publicar")
OUTBOX_LAG = Gauge("outbox_lag_segundos", "Antigüedad del evento pendiente más viejo")
WORKER_PAUSADO = Gauge("worker_pausado", "1 mientras el consumidor está pausado (C2)")

seguir = True


def _parar(*_):
    global seguir
    seguir = False


def medir_outbox():
    """Hilo aparte: el lag se sigue midiendo aunque el consumidor esté pausado o colgado."""
    while seguir:
        try:
            with db.abrir_pool().connection() as conn:
                n, lag = conn.execute(SQL_LAG).fetchone()
            OUTBOX_PENDIENTES.set(n)
            OUTBOX_LAG.set(float(lag))
        except Exception:
            log.exception("no se pudo medir el outbox")
        time.sleep(2)


def publicar(cliente: httpx.Client, outbox_id, orden_id, payload) -> bool:
    padre = propagate.extract(payload.get("trace") or {})
    with TRACER.start_as_current_span("outbox.publicar", context=padre, kind=SpanKind.CONSUMER,
                                      attributes={"outbox.id": outbox_id, "orden.id": orden_id}) as span:
        t0 = time.perf_counter()
        try:
            r = cliente.post(f"{config.EXT_SAP_URL}/notificar", json=payload)
            r.raise_for_status()
        except httpx.HTTPError as e:
            motivo = (f"http_{e.response.status_code}" if isinstance(e, httpx.HTTPStatusError)
                      else type(e).__name__)
            metricas.EXT_SAP_DURACION.labels("error").observe(time.perf_counter() - t0)
            metricas.OUTBOX_FALLOS.labels(motivo).inc()
            span.set_status(Status(StatusCode.ERROR, motivo))
            log.warning("ext-sap falló outbox_id=%s orden_id=%s: %s", outbox_id, orden_id, motivo,
                        extra={"outbox_id": outbox_id, "orden_id": orden_id, "motivo": motivo})
            return False
        metricas.EXT_SAP_DURACION.labels("ok").observe(time.perf_counter() - t0)
        return True


def procesar_lote(cliente: httpx.Client) -> tuple[int, bool]:
    """Devuelve (publicados, hubo_error)."""
    publicados = 0
    # Cursor directo (sin db.consulta): B1 apunta al pool de la API, no al worker.
    with db.abrir_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(SQL_LOTE, (config.WORKER_LOTE,))
        for outbox_id, orden_id, payload in cur.fetchall():
            if not publicar(cliente, outbox_id, orden_id, payload):
                return publicados, True   # sale del with: commit de lo publicado
            cur.execute(SQL_PUBLICADO, (outbox_id,))
            cur.execute(SQL_CONFIRMAR, (orden_id,))
            publicados += 1
            metricas.OUTBOX_PUBLICADOS.inc()
    return publicados, False


def main():
    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)
    metricas.registrar_colectores(lambda: db.POOL)
    start_http_server(int(os.environ.get("METRICS_PORT", "9100")))
    telemetria.instrumentar_httpx()
    db.abrir_pool().wait(timeout=60)
    threading.Thread(target=medir_outbox, daemon=True, name="medir-outbox").start()
    log.info("worker listo: lote=%s ext-sap=%s timeout=%ss", config.WORKER_LOTE, config.EXT_SAP_URL, config.SAP_TIMEOUT_S)
    estaba_pausado = False
    with httpx.Client(timeout=config.SAP_TIMEOUT_S) as cliente:
        while seguir:
            if INYECTOR.pausado("worker.outbox"):
                if not estaba_pausado:
                    log.warning("consumidor pausado por falla en worker.outbox")
                    WORKER_PAUSADO.set(1)
                estaba_pausado = True
                time.sleep(0.2)
                continue
            if estaba_pausado:
                log.warning("consumidor reanudado")
                WORKER_PAUSADO.set(0)
                estaba_pausado = False
            try:
                publicados, error = procesar_lote(cliente)
            except Exception:
                log.exception("error procesando el outbox")
                publicados, error = 0, True
            if publicados:
                log.info("publicados %s eventos", publicados, extra={"publicados": publicados})
            if error or publicados < config.WORKER_LOTE:
                time.sleep(config.WORKER_INTERVALO_S)
    db.cerrar_pool()
    log.info("worker detenido")


if __name__ == "__main__":
    main()
