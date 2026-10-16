"""Métricas Prometheus compartidas por api, worker y ext-sap.

La etiqueta de instancia la pone Prometheus (ver infra/prometheus/prometheus.yml).
"""
import time
from pathlib import Path

import yaml
from prometheus_client import REGISTRY, Counter, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from app import config
from lab.fallas.inyector import INYECTOR

# Cubre desde respuestas sanas (ms) hasta las colas de A2/B1 y el timeout de SAP (30 s).
BUCKETS_S = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 8, 13, 20, 30, 60)

HTTP_DURACION = Histogram("http_peticion_duracion_segundos", "Duración de peticiones HTTP atendidas",
                          ["metodo", "ruta", "codigo"], buckets=BUCKETS_S)
POOL_ESPERA = Histogram("db_pool_espera_segundos", "Tiempo esperando una conexión del pool", buckets=BUCKETS_S)
OUTBOX_PUBLICADOS = Counter("outbox_publicados_total", "Eventos del outbox publicados a ext-sap")
OUTBOX_FALLOS = Counter("outbox_fallos_total", "Intentos fallidos de publicar a ext-sap", ["motivo"])
EXT_SAP_DURACION = Histogram("ext_sap_llamada_duracion_segundos", "Duración de llamadas del worker a ext-sap",
                             ["resultado"], buckets=BUCKETS_S)


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
    """Estado del pool psycopg_pool en cada scrape."""

    def __init__(self, obtener_pool):
        self._pool = obtener_pool

    def collect(self):
        pool = self._pool()
        if pool is None:
            return
        s = pool.get_stats()
        g = GaugeMetricFamily("db_pool_conexiones", "Conexiones del pool por estado", labels=["estado"])
        g.add_metric(["abiertas"], s.get("pool_size", 0))
        g.add_metric(["disponibles"], s.get("pool_available", 0))
        g.add_metric(["en_uso"], s.get("pool_size", 0) - s.get("pool_available", 0))
        yield g
        yield GaugeMetricFamily("db_pool_max", "Tamaño máximo del pool", value=s.get("pool_max", 0))
        yield GaugeMetricFamily("db_pool_esperando", "Peticiones esperando conexión", value=s.get("requests_waiting", 0))
        yield CounterMetricFamily("db_pool_timeouts", "Peticiones que agotaron el timeout del pool",
                                  value=s.get("requests_errors", 0))


_registrados: set[str] = set()


def registrar_colectores(obtener_pool=None) -> None:
    if "fallas" not in _registrados:
        REGISTRY.register(ColectorFallas())
        _registrados.add("fallas")
    if obtener_pool and "pool" not in _registrados:
        REGISTRY.register(ColectorPool(obtener_pool))
        _registrados.add("pool")


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
