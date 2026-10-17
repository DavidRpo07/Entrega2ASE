"""Pool de conexiones y punto de falla db.consulta (B1).

Corrección bulkhead (fase 4, lab/correcciones.yaml): con `bulkhead.activa`, las transacciones
de lectura y de escritura usan pools separados (2 + 3 conexiones), la espera por conexión
se corta a los 500 ms (fail-fast) y la de escritura lleva lock_timeout de 1 s. Apagada, todo
usa el pool `general` de siempre (POOL_MAX, POOL_TIMEOUT_S).
"""
import threading
import time
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar

from opentelemetry.trace import SpanKind
from psycopg_pool import ConnectionPool

from app import config
from app.metricas import POOL_ESPERA
from app.telemetria import TRACER
from lab.fallas.inyector import INYECTOR
from lab.resiliencia.config import CORRECCIONES

# Clave de la petición en curso (id de orden, etc.): hace determinista el % de tráfico.
CLAVE_PETICION: ContextVar[str | None] = ContextVar("clave_peticion", default=None)

POOL: ConnectionPool | None = None
POOLS_BULKHEAD: dict[str, ConnectionPool] = {}   # "lectura", "escritura" (se crean al encender la corrección)
_lock_pools = threading.Lock()

# Esquema que necesitan las correcciones del worker (D2). Idempotente y sin tomar el lock
# ACCESS EXCLUSIVE de ALTER TABLE si las columnas ya existen (api-2 rearranca en plena D1).
DDL_CORRECCIONES = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'ordenes'
                 AND table_name = 'outbox_evento' AND column_name = 'intentos') THEN
    ALTER TABLE ordenes.outbox_evento ADD COLUMN intentos integer NOT NULL DEFAULT 0,
                                      ADD COLUMN proximo_intento timestamptz;
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS ordenes.outbox_muerto (
    outbox_id      bigint PRIMARY KEY,
    aggregate_id   bigint NOT NULL,
    tipo_evento    varchar(50) NOT NULL,
    payload        jsonb NOT NULL,
    intentos       integer NOT NULL,
    ultimo_error   text,
    fecha_creacion timestamptz NOT NULL,
    fecha_muerte   timestamptz NOT NULL DEFAULT now()
);
"""


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
    with _lock_pools:
        for p in POOLS_BULKHEAD.values():
            p.close()
        POOLS_BULKHEAD.clear()


def pool_bulkhead(tipo: str) -> ConnectionPool:
    """Pool `lectura` o `escritura`, creado la primera vez que se usa con la corrección encendida
    (tamaño de correcciones.yaml en ese momento). Apagada la corrección deja de usarse."""
    with _lock_pools:
        pool = POOLS_BULKHEAD.get(tipo)
        if pool is None:
            tam = CORRECCIONES.parametros("bulkhead")[f"pool_{tipo}"]
            pool = ConnectionPool(config.DB_DSN, min_size=1, max_size=tam, open=False,
                                  name=f"{config.INSTANCIA}-{tipo}")
            pool.open(wait=False)
            POOLS_BULKHEAD[tipo] = pool
        return pool


def pools() -> dict[str, ConnectionPool]:
    """Para las métricas: {"general": …, "lectura": …, "escritura": …} (los que existan)."""
    return {"general": POOL, **POOLS_BULKHEAD}


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
def transaccion(tipo: str = "escritura"):
    """Toma una conexión del pool (bloquea hasta POOL_TIMEOUT_S) y abre una
    transacción: commit al salir, rollback si hay excepción.
    `tipo` ("lectura" | "escritura") elige el pool cuando el bulkhead está encendido."""
    bulkhead = CORRECCIONES.parametros("bulkhead")
    if bulkhead["activa"]:
        pool, nombre, timeout = pool_bulkhead(tipo), tipo, bulkhead["pool_timeout_ms"] / 1000.0
    else:
        pool, nombre, timeout = abrir_pool(), "general", None   # None: POOL_TIMEOUT_S del pool
    with ExitStack() as pila:
        with TRACER.start_as_current_span("db.pool.adquirir", attributes={"db.pool": nombre}) as span:
            t0 = time.perf_counter()
            try:
                conn = pila.enter_context(pool.connection(timeout=timeout))
            finally:
                espera = time.perf_counter() - t0
                POOL_ESPERA.labels(nombre).observe(espera)
                span.set_attribute("db.pool.espera_ms", round(espera * 1000, 2))
        cur = pila.enter_context(conn.cursor())
        if bulkhead["activa"] and tipo == "escritura":
            # Sin pasar por db.consulta: B1 no debe cobrar esta sentencia. Aplica a toda la
            # transacción de POST /ordenes; la única espera de locks es la reserva de franjas (Q3).
            cur.execute("SELECT set_config('lock_timeout', %s, true)", (f"{int(bulkhead['lock_timeout_ms'])}ms",))
        yield CursorConFallas(cur)
