"""Pool de conexiones y punto de falla db.consulta (B1)."""
from contextlib import contextmanager
from contextvars import ContextVar

from psycopg_pool import ConnectionPool

from app import config
from lab.fallas.inyector import INYECTOR

# Clave de la petición en curso (id de orden, etc.): hace determinista el % de tráfico.
CLAVE_PETICION: ContextVar[str | None] = ContextVar("clave_peticion", default=None)

POOL: ConnectionPool | None = None


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
    with abrir_pool().connection() as conn:
        with conn.cursor() as cur:
            yield CursorConFallas(cur)
