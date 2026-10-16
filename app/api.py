"""API del modulith (Entregable 3, fase 1).

Endpoints síncronos (def): FastAPI los corre en su pool de hilos, y cada uno
toma una conexión del pool de PostgreSQL (máx. POOL_MAX por réplica).
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, Field

from medir_q4 import QUERY_Q4
from medir_q5 import QUERY_Q5

from app import admin_fallas, config, db
from app.servicios import CatalogoConFallas, modulith

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s [" + config.INSTANCIA + "] %(message)s")
log = logging.getLogger("api")

# Las órdenes de la API usan su propio rango para no chocar con datos ni con fase 4 (600001+).
DDL_ARRANQUE = """
SELECT pg_advisory_xact_lock(7300301);
CREATE SEQUENCE IF NOT EXISTS ordenes.api_orden_seq START 1000001;
CREATE INDEX IF NOT EXISTS ix_outbox_pendiente ON ordenes.outbox_evento (outbox_id) WHERE NOT publicado;
"""


@asynccontextmanager
async def ciclo_de_vida(_app):
    pool = db.abrir_pool()
    pool.wait(timeout=60)
    with pool.connection() as conn:
        conn.execute(DDL_ARRANQUE)
    log.info("pool listo (max=%s) y DDL de arranque aplicado", config.POOL_MAX)
    yield
    db.cerrar_pool()


app = FastAPI(title="Modulith órdenes — laboratorio de fallas", lifespan=ciclo_de_vida)
admin_fallas.instalar(app)


@app.exception_handler(PoolTimeout)
async def pool_agotado(_request, exc):
    return JSONResponse(status_code=503, content={"error": f"pool de conexiones agotado: {exc}",
                                                  "instancia": config.INSTANCIA})


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ escritura
class OrdenIn(BaseModel):
    proveedor_id: int
    cedi_id: int = Field(ge=1)
    total: float = Field(ge=0)
    fecha_entrega_solicitada: datetime | None = None   # por defecto: ahora + 2 días
    fecha_creacion: datetime | None = None             # por defecto: ahora


@app.post("/ordenes", status_code=201)
def crear_orden(orden: OrdenIn):
    f_crea = orden.fecha_creacion or _ahora()
    f_ent = orden.fecha_entrega_solicitada or (f_crea + timedelta(days=2))
    fmt = "%Y-%m-%d %H:%M:%S%z"   # LogisticaService toma la fecha con split(" ")[0]
    with db.transaccion() as cur:
        cur.execute("SELECT nextval('ordenes.api_orden_seq')")
        orden_id = cur.fetchone()[0]
        db.CLAVE_PETICION.set(str(orden_id))
        dto = (orden_id, orden.proveedor_id, orden.cedi_id, f_crea.strftime(fmt), f_ent.strftime(fmt),
               None, "PENDIENTE", orden.total)
        try:
            modulith(cur).crear_orden_transaccional(dto)
        except ValueError as e:  # regla de negocio (p. ej. sin contrato vigente)
            raise HTTPException(422, str(e))
    return {"orden_id": orden_id, "estado": "PENDIENTE", "instancia": config.INSTANCIA}


# ------------------------------------------------------------------ lectura
@app.get("/ordenes/{orden_id}")
def obtener_orden(orden_id: int):
    db.CLAVE_PETICION.set(str(orden_id))
    with db.transaccion() as cur:
        cur.row_factory = dict_row
        cur.execute("SELECT * FROM ordenes.orden_compra WHERE orden_id = %s", (orden_id,))
        orden = cur.fetchone()
        if not orden:
            raise HTTPException(404, f"orden {orden_id} no existe")
        cur.execute("SELECT sku_id, categoria, cantidad_solicitada, cantidad_recibida, precio_unitario "
                    "FROM ordenes.linea_orden WHERE orden_id = %s", (orden_id,))
        orden["lineas"] = cur.fetchall()
        cur.execute("SELECT outbox_id, tipo_evento, publicado, fecha_creacion, fecha_publicacion "
                    "FROM ordenes.outbox_evento WHERE aggregate_id = %s ORDER BY outbox_id", (orden_id,))
        orden["eventos"] = cur.fetchall()
    return orden


@app.get("/proveedores/{proveedor_id}/ordenes")
def ordenes_de_proveedor(proveedor_id: int, offset: int = Query(0, ge=0)):
    """Q5 del Entregable 2: últimas órdenes del proveedor (paginado de 50)."""
    db.CLAVE_PETICION.set(str(proveedor_id))
    with db.transaccion() as cur:
        cur.row_factory = dict_row
        cur.execute(QUERY_Q5, (proveedor_id, offset))
        return cur.fetchall()


@app.get("/proveedores/{proveedor_id}/otif")
def otif_de_proveedor(proveedor_id: int):
    """Q4 del Entregable 2: fill rate y OTIF por categoría y mes."""
    db.CLAVE_PETICION.set(str(proveedor_id))
    with db.transaccion() as cur:
        cur.row_factory = dict_row
        cur.execute(QUERY_Q4, (proveedor_id,))
        return cur.fetchall()


@app.get("/catalogo/precio")
def precio(proveedor_id: int, sku_id: int):
    """Q2 del Entregable 2 a través del módulo de catálogo (punto catalogo.validar_sku)."""
    db.CLAVE_PETICION.set(f"{proveedor_id}:{sku_id}")
    with db.transaccion() as cur:
        valor = CatalogoConFallas(cur).validar_sku_y_obtener_precio(proveedor_id, sku_id, _ahora().isoformat())
    return {"proveedor_id": proveedor_id, "sku_id": sku_id, "precio": valor}


@app.get("/logistica/franjas")
def franjas(cedi_id: int, fecha: str):
    with db.transaccion() as cur:
        cur.row_factory = dict_row
        cur.execute("SELECT franja_id, hora_inicio, hora_fin, capacidad, reservas_actuales, estado "
                    "FROM logistica.franja_descargue WHERE cedi_id = %s AND fecha = %s::date "
                    "ORDER BY hora_inicio", (cedi_id, fecha))
        return cur.fetchall()


@app.get("/outbox/pendientes")
def outbox_pendientes():
    with db.transaccion() as cur:
        cur.execute("SELECT count(*), EXTRACT(EPOCH FROM now() - min(fecha_creacion)) "
                    "FROM ordenes.outbox_evento WHERE NOT publicado")
        n, edad = cur.fetchone()
    return {"pendientes": n, "lag_s": float(edad or 0)}


@app.get("/health")
def health():
    # Sin puntos de falla: el healthcheck no debe verse afectado por las fallas de dominio.
    with db.abrir_pool().connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "instancia": config.INSTANCIA, "pool": db.abrir_pool().get_stats()}
