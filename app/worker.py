"""Worker del outbox: publica ordenes.outbox_evento hacia ext-sap.

- Toma lotes con FOR UPDATE SKIP LOCKED (varios workers no se pisan).
- Por cada evento llama POST ext-sap/notificar; si responde 2xx marca el evento
  publicado y la orden pasa de PENDIENTE a CONFIRMADA.
- Si una llamada falla, el lote se corta: lo ya publicado se confirma y el resto
  queda pendiente para el siguiente ciclo (sin reintentos ni circuit breaker).
- Corrección `worker` (fase 4, lab/correcciones.yaml): un evento que falla se reprograma
  con backoff exponencial + jitter (proximo_intento) y el lote SIGUE con los demás (sin
  head-of-line blocking); al agotar max_intentos pasa a ordenes.outbox_muerto. Un circuit
  breaker hacia ext-sap corta el lote mientras está abierto, sin gastar intentos.
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

from app import config, correcciones, db, metricas, telemetria
from lab.fallas.inyector import INYECTOR
from lab.resiliencia.backoff import espera_s
from lab.resiliencia.config import CORRECCIONES

TRACER = telemetria.configurar("outbox-worker")
log = logging.getLogger("worker")

SQL_LOTE = """
    SELECT outbox_id, aggregate_id, payload FROM ordenes.outbox_evento
    WHERE NOT publicado ORDER BY outbox_id LIMIT %s FOR UPDATE SKIP LOCKED
"""
SQL_PUBLICADO = "UPDATE ordenes.outbox_evento SET publicado = true, fecha_publicacion = now() WHERE outbox_id = %s"
SQL_CONFIRMAR = "UPDATE ordenes.orden_compra SET estado = 'CONFIRMADA' WHERE orden_id = %s AND estado = 'PENDIENTE'"
# Con la corrección: solo eventos cuyo backoff ya venció.
SQL_LOTE_CORREGIDO = """
    SELECT outbox_id, aggregate_id, payload, intentos FROM ordenes.outbox_evento
    WHERE NOT publicado AND (proximo_intento IS NULL OR proximo_intento <= now())
    ORDER BY outbox_id LIMIT %s FOR UPDATE SKIP LOCKED
"""
SQL_REPROGRAMAR = ("UPDATE ordenes.outbox_evento SET intentos = %s, "
                   "proximo_intento = now() + make_interval(secs => %s) WHERE outbox_id = %s")
SQL_A_MUERTOS = """
    WITH movido AS (DELETE FROM ordenes.outbox_evento WHERE outbox_id = %(id)s
                    RETURNING outbox_id, aggregate_id, tipo_evento, payload, fecha_creacion)
    INSERT INTO ordenes.outbox_muerto (outbox_id, aggregate_id, tipo_evento, payload, intentos, ultimo_error, fecha_creacion)
    SELECT outbox_id, aggregate_id, tipo_evento, payload, %(intentos)s, %(error)s, fecha_creacion FROM movido
"""
SQL_MUERTOS = "SELECT count(*) FROM ordenes.outbox_muerto"
SQL_LAG = ("SELECT count(*), COALESCE(EXTRACT(EPOCH FROM now() - min(fecha_creacion)), 0) "
           "FROM ordenes.outbox_evento WHERE NOT publicado")

OUTBOX_PENDIENTES = Gauge("outbox_pendientes", "Eventos del outbox sin publicar")
OUTBOX_LAG = Gauge("outbox_lag_segundos", "Antigüedad del evento pendiente más viejo")
WORKER_PAUSADO = Gauge("worker_pausado", "1 mientras el consumidor está pausado (C2)")
OUTBOX_MUERTOS = Gauge("outbox_mensajes_muertos", "Eventos en ordenes.outbox_muerto")

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
                muertos = conn.execute(SQL_MUERTOS).fetchone()[0]
            OUTBOX_PENDIENTES.set(n)
            OUTBOX_LAG.set(float(lag))
            OUTBOX_MUERTOS.set(muertos)
        except Exception:
            log.exception("no se pudo medir el outbox")
        time.sleep(2)


def publicar(cliente: httpx.Client, outbox_id, orden_id, payload) -> str | None:
    """None si ext-sap aceptó el evento; si no, el motivo del fallo."""
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
            return motivo
        metricas.EXT_SAP_DURACION.labels("ok").observe(time.perf_counter() - t0)
        return None


def procesar_lote(cliente: httpx.Client) -> tuple[int, bool]:
    """Devuelve (publicados, hubo_error)."""
    publicados = 0
    # Cursor directo (sin db.consulta): B1 apunta al pool de la API, no al worker.
    with db.abrir_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(SQL_LOTE, (config.WORKER_LOTE,))
        for outbox_id, orden_id, payload in cur.fetchall():
            if publicar(cliente, outbox_id, orden_id, payload):
                return publicados, True   # sale del with: commit de lo publicado
            cur.execute(SQL_PUBLICADO, (outbox_id,))
            cur.execute(SQL_CONFIRMAR, (orden_id,))
            publicados += 1
            metricas.OUTBOX_PUBLICADOS.inc()
    return publicados, False


def procesar_lote_corregido(cliente: httpx.Client) -> tuple[int, int, bool]:
    """Corrección D2. Devuelve (publicados, procesados, cortado_por_breaker). Un fallo no
    corta el lote ni hace esperar al worker: el evento queda reprogramado y se sigue."""
    p = CORRECCIONES.parametros("worker")
    bk, breaker = p["backoff"], correcciones.BREAKERS["ext_sap"]
    publicados = procesados = 0
    with db.abrir_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(SQL_LOTE_CORREGIDO, (config.WORKER_LOTE,))
        for outbox_id, orden_id, payload, intentos in cur.fetchall():
            if not breaker.permite():
                # Breaker abierto: el resto queda pendiente sin gastar intentos.
                metricas.OUTBOX_DIFERIDOS.inc()
                return publicados, procesados, True
            procesados += 1
            motivo = publicar(cliente, outbox_id, orden_id, payload)
            if motivo is None:
                breaker.exito()
                cur.execute(SQL_PUBLICADO, (outbox_id,))
                cur.execute(SQL_CONFIRMAR, (orden_id,))
                publicados += 1
                metricas.OUTBOX_PUBLICADOS.inc()
                continue
            breaker.fallo()
            intentos += 1
            datos = {"outbox_id": outbox_id, "orden_id": orden_id, "intentos": intentos, "motivo": motivo}
            if intentos >= p["max_intentos"]:
                cur.execute(SQL_A_MUERTOS, {"id": outbox_id, "intentos": intentos, "error": motivo})
                metricas.OUTBOX_MUERTOS_TOTAL.inc()
                log.error("evento a mensajes muertos outbox_id=%s tras %s intentos (%s)", outbox_id, intentos, motivo,
                          extra=datos)
            else:
                espera = espera_s(intentos, outbox_id, bk["base_ms"], bk["factor"], bk["jitter"])
                cur.execute(SQL_REPROGRAMAR, (intentos, espera, outbox_id))
                metricas.OUTBOX_REINTENTOS.inc()
                log.info("evento reprogramado outbox_id=%s intento=%s en %.0f ms", outbox_id, intentos, espera * 1000,
                         extra={**datos, "espera_ms": round(espera * 1000, 1)})
    return publicados, procesados, False


def main():
    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)
    metricas.registrar_colectores(db.pools, lambda: correcciones.BREAKERS)
    correcciones.registrar_breaker("ext_sap", "worker")
    start_http_server(int(os.environ.get("METRICS_PORT", "9100")))
    telemetria.instrumentar_httpx()
    db.abrir_pool().wait(timeout=60)
    with db.abrir_pool().connection() as conn:   # columnas de reintento y outbox_muerto (idempotente)
        conn.execute("SELECT pg_advisory_xact_lock(7300301)")
        conn.execute(db.DDL_CORRECCIONES)
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
                if CORRECCIONES.activa("worker"):
                    publicados, procesados, error = procesar_lote_corregido(cliente)
                else:
                    publicados, error = procesar_lote(cliente)
                    procesados = publicados
            except Exception:
                log.exception("error procesando el outbox")
                publicados, procesados, error = 0, 0, True
            if publicados:
                log.info("publicados %s eventos", publicados, extra={"publicados": publicados})
            if error or procesados < config.WORKER_LOTE:
                time.sleep(config.WORKER_INTERVALO_S)
    db.cerrar_pool()
    log.info("worker detenido")


if __name__ == "__main__":
    main()
