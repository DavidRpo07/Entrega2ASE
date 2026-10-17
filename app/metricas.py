"""Métricas Prometheus compartidas por api, worker y ext-sap.

La etiqueta de instancia la pone Prometheus (ver infra/prometheus/prometheus.yml).
"""
import time
from pathlib import Path

import yaml
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from app import config
from lab.fallas.inyector import INYECTOR
from lab.resiliencia.breaker import VALOR as VALOR_BREAKER
from lab.resiliencia.config import CORRECCIONES

# Cubre desde respuestas sanas (ms) hasta las colas de A2/B1 y el timeout de SAP (30 s).
BUCKETS_S = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 8, 13, 20, 30, 60)

HTTP_DURACION = Histogram("http_peticion_duracion_segundos", "Duración de peticiones HTTP atendidas",
                          ["metodo", "ruta", "codigo"], buckets=BUCKETS_S)
POOL_ESPERA = Histogram("db_pool_espera_segundos", "Tiempo esperando una conexión del pool", ["pool"], buckets=BUCKETS_S)
OUTBOX_PUBLICADOS = Counter("outbox_publicados_total", "Eventos del outbox publicados a ext-sap")
OUTBOX_FALLOS = Counter("outbox_fallos_total", "Intentos fallidos de publicar a ext-sap", ["motivo"])
Gauge("trazas_activas", "1 si OpenTelemetry está activo en este proceso (TRAZAS)").set(1 if config.TRAZAS else 0)
EXT_SAP_DURACION = Histogram("ext_sap_llamada_duracion_segundos", "Duración de llamadas del worker a ext-sap",
                             ["resultado"], buckets=BUCKETS_S)

# ---- Correcciones (fase 4)
BREAKER_TRANSICIONES = Counter("circuit_breaker_transiciones_total", "Cambios de estado del circuit breaker",
                               ["nombre", "desde", "hacia"])
CATALOGO_TIMEOUTS = Counter("catalogo_timeouts_total", "Llamadas a Catálogo cortadas por el timeout de la corrección")
CATALOGO_FALLBACK = Counter("catalogo_fallback_total", "Fallback de Catálogo: último precio conocido (hit) o 503 (miss)",
                            ["motivo", "resultado"])
DB_LOCK_TIMEOUTS = Counter("db_lock_timeouts_total", "Transacciones abortadas por lock_timeout (corrección bulkhead)")
OUTBOX_REINTENTOS = Counter("outbox_reintentos_total", "Eventos reprogramados con backoff tras un fallo")
OUTBOX_MUERTOS_TOTAL = Counter("outbox_muertos_total", "Eventos movidos a ordenes.outbox_muerto (agotaron sus intentos)")
OUTBOX_DIFERIDOS = Counter("outbox_breaker_diferidos_total", "Lotes cortados porque el breaker hacia ext-sap no dejó pasar")


class ColectorFallas:
    """falla_activa{falla_id,tipo,target} = 1 mientras la falla esté activa en este
    proceso, y 0 para las demás fallas del catálogo (así la serie existe siempre)."""

    def __init__(self):
        try:
            datos = yaml.safe_load(Path(config.CATALOGO_FALLAS).read_text(encoding="utf-8")) or {}
            self._catalogo = {f["id"]: f for f in datos.get("fallas", [])}
        except OSError:
            self._catalogo = {}

    def collect(self):
        activa = GaugeMetricFamily("falla_activa", "Falla activa en este proceso", labels=["falla_id", "tipo", "target"])
        activas = {f.id: f for f in INYECTOR.activas()}
        for f in activas.values():
            activa.add_metric([f.id, f.tipo, f.target], 1)
        for fid, f in self._catalogo.items():
            if fid not in activas:
                activa.add_metric([fid, f.get("tipo", ""), f.get("target", "")], 0)
        yield activa
        inyectadas = CounterMetricFamily("fallas_inyectadas", "Veces que se aplicó cada falla", labels=["falla_id"])
        for fid, n in dict(INYECTOR.contadores).items():
            inyectadas.add_metric([fid], n)
        yield inyectadas


class ColectorPool:
    """Estado de los pools psycopg_pool en cada scrape, con etiqueta `pool`: `general` (el
    único sin corrección) y, con el bulkhead, `lectura` y `escritura`."""

    def __init__(self, obtener_pools):
        self._pools = obtener_pools

    def collect(self):
        pools = self._pools()
        if not isinstance(pools, dict):
            pools = {"general": pools}
        pools = {k: p for k, p in pools.items() if p is not None}
        if not pools:
            return
        g = GaugeMetricFamily("db_pool_conexiones", "Conexiones del pool por estado", labels=["estado", "pool"])
        mx = GaugeMetricFamily("db_pool_max", "Tamaño máximo del pool", labels=["pool"])
        esp = GaugeMetricFamily("db_pool_esperando", "Peticiones esperando conexión", labels=["pool"])
        to = CounterMetricFamily("db_pool_timeouts", "Peticiones que agotaron el timeout del pool", labels=["pool"])
        for nombre, pool in pools.items():
            s = pool.get_stats()
            g.add_metric(["abiertas", nombre], s.get("pool_size", 0))
            g.add_metric(["disponibles", nombre], s.get("pool_available", 0))
            g.add_metric(["en_uso", nombre], s.get("pool_size", 0) - s.get("pool_available", 0))
            mx.add_metric([nombre], s.get("pool_max", 0))
            esp.add_metric([nombre], s.get("requests_waiting", 0))
            to.add_metric([nombre], s.get("requests_errors", 0))
        yield from (g, mx, esp, to)


class ColectorCorrecciones:
    """correccion_activa{correccion} (1/0) y estado de los circuit breakers del proceso
    (circuit_breaker_estado: 0 cerrado, 1 semiabierto, 2 abierto)."""

    def __init__(self, obtener_breakers):
        self._breakers = obtener_breakers

    def collect(self):
        activa = GaugeMetricFamily("correccion_activa", "Corrección de la fase 4 encendida en este proceso",
                                   labels=["correccion"])
        encendidas = set(CORRECCIONES.activas())
        for s in ("catalogo", "bulkhead", "worker"):
            activa.add_metric([s], 1 if s in encendidas else 0)
        yield activa
        estado = GaugeMetricFamily("circuit_breaker_estado", "0 cerrado, 1 semiabierto, 2 abierto", labels=["nombre"])
        rechazos = CounterMetricFamily("circuit_breaker_rechazos", "Llamadas rechazadas por el breaker", labels=["nombre"])
        for nombre, b in (self._breakers() or {}).items():
            estado.add_metric([nombre], VALOR_BREAKER[b.estado])
            rechazos.add_metric([nombre], b.rechazos)
        yield estado
        yield rechazos


_registrados: set[str] = set()


def registrar_colectores(obtener_pool=None, obtener_breakers=None) -> None:
    if "fallas" not in _registrados:
        REGISTRY.register(ColectorFallas())
        _registrados.add("fallas")
    if obtener_pool and "pool" not in _registrados:
        REGISTRY.register(ColectorPool(obtener_pool))
        _registrados.add("pool")
    if "correcciones" not in _registrados:
        REGISTRY.register(ColectorCorrecciones(obtener_breakers or dict))
        _registrados.add("correcciones")


def instalar_http(app) -> None:
    """Middleware: histograma por ruta (plantilla, no URL cruda) + access log JSON
    con trace_id, y endpoint /metrics."""
    import logging

    from opentelemetry import trace
    from prometheus_client import make_asgi_app

    acceso = logging.getLogger("acceso")
    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def medir(request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)
        t0 = time.perf_counter()
        codigo = 500
        try:
            resp = await call_next(request)
            codigo = resp.status_code
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:   # permite buscar en Jaeger la traza de una respuesta concreta
                resp.headers["X-Trace-Id"] = format(ctx.trace_id, "032x")
            return resp
        finally:
            dur = time.perf_counter() - t0
            ruta = getattr(request.scope.get("route"), "path", None) or "sin_ruta"
            HTTP_DURACION.labels(request.method, ruta, str(codigo)).observe(dur)
            if ruta != "/health":
                acceso.info("%s %s %s", request.method, request.url.path, codigo,
                            extra={"metodo": request.method, "ruta": ruta, "codigo": codigo,
                                   "duracion_ms": round(dur * 1000, 2)})
