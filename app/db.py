"""Pool de conexiones y punto de falla db.consulta (B1)."""
import time
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar

from opentelemetry.trace import SpanKind
from psycopg_pool import ConnectionPool

from app import config
from app.metricas import POOL_ESPERA
from app.telemetria import TRACER
from lab.fallas.inyector import INYECTOR

# Clave de la petición en curso (id de orden, etc.): hace determinista el % de tráfico.
CLAVE_PETICION: ContextVar[str | None] = ContextVar("clave_peticion", default=None)

POOL: ConnectionPool | None = None


def clave_por_defecto(valor: str) -> None:
    """Usa `valor` como clave salvo que la petición ya traiga X-Clave-Carga."""
    if CLAVE_PETICION.get() is None:
        CLAVE_PETICION.set(valor)


def abrir_pool() -> ConnectionPool:
    global POOL
    if POOL is None:
        POOL = ConnectionPool(
            config.DB_DSN, min_size=config.POOL_MIN, max_size=config.POOL_MAX,
            timeout=config.POOL_TIMEOUT_S, open=False, name=config.INSTANCIA,
        )
        POOL.open(wait=False)
    return POOL


def cerrar_pool() -> None:
    global POOL
    if POOL is not None:
        POOL.close()
        POOL = None


class CursorConFallas:
    """Envuelve el cursor: cada consulta pasa por el punto db.consulta.
    Con B1 la espera ocurre con la conexión tomada, así que retiene el pool."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        sentencia = " ".join(str(sql).split())
        with TRACER.start_as_current_span("db.consulta", kind=SpanKind.CLIENT, attributes={
                "db.system": "postgresql", "db.statement": sentencia[:500]}):
            INYECTOR.punto("db.consulta", clave=CLAVE_PETICION.get())
            return self._cursor.execute(sql, params)

    def __getattr__(self, nombre):
        return getattr(self._cursor, nombre)

    def __setattr__(self, nombre, valor):
        if nombre == "_cursor":
            object.__setattr__(self, nombre, valor)
        else:
            setattr(self._cursor, nombre, valor)   # p. ej. row_factory


@contextmanager
def transaccion():
    """Toma una conexión del pool (bloquea hasta POOL_TIMEOUT_S) y abre una
    transacción: commit al salir, rollback si hay excepción."""
    with ExitStack() as pila:
        with TRACER.start_as_current_span("db.pool.adquirir") as span:
            t0 = time.perf_counter()
            try:
                conn = pila.enter_context(abrir_pool().connection())
            finally:
                espera = time.perf_counter() - t0
                POOL_ESPERA.observe(espera)
                span.set_attribute("db.pool.espera_ms", round(espera * 1000, 2))
        cur = pila.enter_context(conn.cursor())
        yield CursorConFallas(cur)
