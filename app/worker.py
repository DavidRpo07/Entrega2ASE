"""Worker del outbox: publica ordenes.outbox_evento hacia ext-sap.

- Toma lotes con FOR UPDATE SKIP LOCKED (varios workers no se pisan).
- Por cada evento llama POST ext-sap/notificar; si responde 2xx marca el evento
  publicado y la orden pasa de PENDIENTE a CONFIRMADA.
- Si una llamada falla, el lote se corta: lo ya publicado se confirma y el resto
  queda pendiente para el siguiente ciclo (sin reintentos ni circuit breaker:
  esas correcciones son la fase 4).
- Punto de falla worker.outbox (C2): mientras esté pausado no consume.
"""
import logging
import signal
import time

import httpx

from app import config, db
from lab.fallas.inyector import INYECTOR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s [" + config.INSTANCIA + "] %(message)s")
log = logging.getLogger("worker")

SQL_LOTE = """
    SELECT outbox_id, aggregate_id, payload FROM ordenes.outbox_evento
    WHERE NOT publicado ORDER BY outbox_id LIMIT %s FOR UPDATE SKIP LOCKED
"""
SQL_PUBLICADO = "UPDATE ordenes.outbox_evento SET publicado = true, fecha_publicacion = now() WHERE outbox_id = %s"
SQL_CONFIRMAR = "UPDATE ordenes.orden_compra SET estado = 'CONFIRMADA' WHERE orden_id = %s AND estado = 'PENDIENTE'"

seguir = True


def _parar(*_):
    global seguir
    seguir = False


def procesar_lote(cliente: httpx.Client) -> tuple[int, bool]:
    """Devuelve (publicados, hubo_error)."""
    publicados = 0
    # Cursor directo (sin db.consulta): B1 apunta al pool de la API, no al worker.
    with db.abrir_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(SQL_LOTE, (config.WORKER_LOTE,))
        for outbox_id, orden_id, payload in cur.fetchall():
            try:
                r = cliente.post(f"{config.EXT_SAP_URL}/notificar", json=payload)
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("ext-sap falló outbox_id=%s orden_id=%s: %s", outbox_id, orden_id, e)
                return publicados, True   # sale del with: commit de lo publicado
            cur.execute(SQL_PUBLICADO, (outbox_id,))
            cur.execute(SQL_CONFIRMAR, (orden_id,))
            publicados += 1
    return publicados, False


def main():
    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)
    db.abrir_pool().wait(timeout=60)
    log.info("worker listo: lote=%s ext-sap=%s timeout=%ss", config.WORKER_LOTE, config.EXT_SAP_URL, config.SAP_TIMEOUT_S)
    estaba_pausado = False
    with httpx.Client(timeout=config.SAP_TIMEOUT_S) as cliente:
        while seguir:
            if INYECTOR.pausado("worker.outbox"):
                if not estaba_pausado:
                    log.warning("consumidor pausado por falla en worker.outbox")
                estaba_pausado = True
                time.sleep(0.2)
                continue
            if estaba_pausado:
                log.warning("consumidor reanudado")
                estaba_pausado = False
            try:
                publicados, error = procesar_lote(cliente)
            except Exception:
                log.exception("error procesando el outbox")
                publicados, error = 0, True
            if publicados:
                log.info("publicados %s eventos", publicados)
            if error or publicados < config.WORKER_LOTE:
                time.sleep(config.WORKER_INTERVALO_S)
    db.cerrar_pool()
    log.info("worker detenido")


if __name__ == "__main__":
    main()
