"""Ejecutor de fallas 'externa' (B2, D1) — servicio fallas-ext.

Lee el mismo faults.yaml que el resto (vía el inyector) y reconcilia cada 250 ms
el estado deseado con el real, así que /admin/faults activa estas fallas igual
que las demás y el kill switch (DELETE /admin/faults) las revierte en segundos:

- target logistica.franja_descargue (B2): mantiene una transacción con
  SELECT ... FOR UPDATE sobre las franjas de `cedi_id` durante `retencion_s`
  de cada `ciclo_s`. Revertir = ROLLBACK (libera el lock).
- target = servicio de compose (D1, p. ej. api-2): docker stop entre
  `caida_tras_s` y `caida_tras_s + caida_s` desde la activación. Revertir =
  docker start. Solo arranca contenedores que este servicio detuvo.

El tiempo se mide desde la activación (inicio_utc), así que si este servicio se
reinicia a mitad de una falla retoma la fase correcta.
"""
import json
import logging
import os
import signal
import socket
import time
from pathlib import Path

import httpx
import psycopg
from prometheus_client import Gauge, start_http_server

from app import config, metricas, telemetria
from lab.fallas.inyector import INYECTOR

telemetria.configurar("fallas-ext")
log = logging.getLogger("fallas_ext")

CONTENEDOR = Gauge("contenedor_info", "Contenedores del proyecto: id del cgroup (como cAdvisor) → servicio",
                   ["id", "servicio", "proyecto"])
EFECTO = Gauge("falla_externa_efecto", "1 mientras el efecto de una falla externa está aplicado",
               ["falla_id", "efecto"])
TARGET_LOCK = "logistica.franja_descargue"
# Contenedores detenidos por este servicio: sobrevive a un reinicio de fallas-ext,
# para no dejar api-2 abajo si el kill switch llega mientras se reinicia.
ESTADO = Path(config.FAULTS_FILE or "/tmp/faults.yaml").with_name("externas_estado.json")
seguir = True


def _parar(*_):
    global seguir
    seguir = False


class Docker:
    """Cliente mínimo de la API de Docker por el socket montado."""

    def __init__(self):
        self.http = httpx.Client(transport=httpx.HTTPTransport(uds="/var/run/docker.sock"),
                                 base_url="http://docker", timeout=30)
        propio = self.http.get(f"/containers/{socket.gethostname()}/json").json()
        self.proyecto = propio["Config"]["Labels"]["com.docker.compose.project"]

    def contenedor(self, servicio: str) -> dict | None:
        filtros = {"label": [f"com.docker.compose.project={self.proyecto}",
                             f"com.docker.compose.service={servicio}"]}
        r = self.http.get("/containers/json", params={"all": "1", "filters": json.dumps(filtros)})
        r.raise_for_status()
        return (r.json() or [None])[0]

    def contenedores(self) -> list[dict]:
        filtros = {"label": [f"com.docker.compose.project={self.proyecto}"]}
        r = self.http.get("/containers/json", params={"filters": json.dumps(filtros)})
        r.raise_for_status()
        return r.json()

    def detener(self, cid: str) -> None:
        self.http.post(f"/containers/{cid}/stop", params={"t": "5"}).raise_for_status()

    def arrancar(self, cid: str) -> None:
        r = self.http.post(f"/containers/{cid}/start")
        if r.status_code not in (204, 304):   # 304: ya estaba arriba
            r.raise_for_status()


class Ejecutor:
    def __init__(self):
        self.lock_conn: psycopg.Connection | None = None
        self.lock_de: str | None = None
        self.docker: Docker | None = None
        self.detenidos: dict[str, tuple[str, str]] = {}   # servicio -> (container id, falla_id)
        try:
            self.detenidos = {k: tuple(v) for k, v in json.loads(ESTADO.read_text()).items()}
            if self.detenidos:
                log.warning("estado previo: servicios detenidos por fallas-ext %s", sorted(self.detenidos))
        except (OSError, ValueError):
            pass

    def _guardar(self) -> None:
        ESTADO.write_text(json.dumps(self.detenidos))

    # ------------------------------------------------------------- B2: lock
    def tomar_lock(self, f, cedi_id: int) -> None:
        if self.lock_conn is not None:
            return
        conn = psycopg.connect(config.DB_DSN, autocommit=False, application_name="fallas-ext-B2")
        conn.execute("SET lock_timeout = '10s'")
        n = len(conn.execute("SELECT franja_id FROM logistica.franja_descargue WHERE cedi_id = %s FOR UPDATE",
                             (cedi_id,)).fetchall())
        self.lock_conn, self.lock_de = conn, f.id
        EFECTO.labels(f.id, "lock_franjas").set(1)
        log.warning("%s: lock FOR UPDATE tomado sobre %s franjas del CEDI %s", f.id, n, cedi_id,
                    extra={"falla_id": f.id, "efecto": "lock_franjas", "estado": "aplicado", "filas": n})

    def soltar_lock(self, motivo: str) -> None:
        if self.lock_conn is None:
            return
        try:
            self.lock_conn.rollback()
            self.lock_conn.close()
        finally:
            EFECTO.labels(self.lock_de, "lock_franjas").set(0)
            log.warning("%s: lock liberado (%s)", self.lock_de, motivo,
                        extra={"falla_id": self.lock_de, "efecto": "lock_franjas", "estado": "revertido"})
            self.lock_conn, self.lock_de = None, None

    # ------------------------------------------------------------- D1: caída
    def _docker(self) -> Docker:
        if self.docker is None:
            self.docker = Docker()
        return self.docker

    def caer(self, f, servicio: str) -> None:
        if servicio in self.detenidos:
            return
        c = self._docker().contenedor(servicio)
        if c is None:
            log.error("%s: no existe el servicio %s", f.id, servicio)
            return
        self._docker().detener(c["Id"])
        self.detenidos[servicio] = (c["Id"], f.id)
        self._guardar()
        EFECTO.labels(f.id, "servicio_detenido").set(1)
        log.warning("%s: docker stop %s", f.id, servicio,
                    extra={"falla_id": f.id, "efecto": "servicio_detenido", "estado": "aplicado", "servicio": servicio})

    def levantar(self, servicio: str, motivo: str) -> None:
        cid, fid = self.detenidos[servicio]
        self._docker().arrancar(cid)
        del self.detenidos[servicio]
        self._guardar()
        EFECTO.labels(fid, "servicio_detenido").set(0)
        log.warning("%s: docker start %s (%s)", fid, servicio, motivo,
                    extra={"falla_id": fid, "efecto": "servicio_detenido", "estado": "revertido", "servicio": servicio})

    # ------------------------------------------------------------- reconciliación
    def reconciliar(self) -> None:
        externas = [f for f in INYECTOR.activas() if f.tipo == "externa"]
        ahora = time.monotonic()
        quiero_lock, quiero_abajo = None, {}
        for f in externas:
            p = f.parametros or {}
            t = ahora - f.activada_en
            if f.target == TARGET_LOCK:
                ciclo = float(p.get("ciclo_s", 60))
                if t % ciclo < float(p.get("retencion_s", 30)):
                    quiero_lock = (f, int(p["cedi_id"]))
            else:
                servicio = p.get("servicio", f.target)
                desde = float(p.get("caida_tras_s", 0))
                if desde <= t < desde + float(p.get("caida_s", f.duracion_s or 1e12)):
                    quiero_abajo[servicio] = f

        if quiero_lock:
            self.tomar_lock(*quiero_lock)
        else:
            self.soltar_lock("fin de retención, expiración o kill switch")
        for servicio, f in quiero_abajo.items():
            self.caer(f, servicio)
        for servicio in [s for s in self.detenidos if s not in quiero_abajo]:
            self.levantar(servicio, "fin de la caída, expiración o kill switch")

    def publicar_contenedores(self) -> None:
        """Etiquetas para unir las métricas de cAdvisor (id del cgroup) con el servicio."""
        d = self._docker()
        CONTENEDOR.clear()
        for c in d.contenedores():
            servicio = c["Labels"].get("com.docker.compose.service", "?")
            CONTENEDOR.labels(f"/docker/{c['Id']}", servicio, d.proyecto).set(1)

    def revertir_todo(self) -> None:
        self.soltar_lock("apagado de fallas-ext")
        for servicio in list(self.detenidos):
            self.levantar(servicio, "apagado de fallas-ext")


def main():
    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)
    metricas.registrar_colectores()
    start_http_server(int(os.environ.get("METRICS_PORT", "9100")))
    ej = Ejecutor()
    log.info("fallas-ext listo (faults=%s)", config.FAULTS_FILE)
    ultima_lista = 0.0
    while seguir:
        try:
            if time.monotonic() - ultima_lista > 10:
                ej.publicar_contenedores()
                ultima_lista = time.monotonic()
            ej.reconciliar()
        except Exception:
            log.exception("error reconciliando fallas externas")
            time.sleep(1)
        time.sleep(0.25)
    ej.revertir_todo()


if __name__ == "__main__":
    main()
