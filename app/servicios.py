"""Módulos del modulith (Entregable 2) con sus puntos de falla.

Las clases de dominio se importan sin cambios desde datos/ejecutar_fase4_modulith.py
(así `make fase4` sigue intacto); aquí solo se antepone INYECTOR.punto() a cada
operación para poder inyectar fallas focalizadas por módulo.
"""
import functools
import json

from opentelemetry import propagate

from ejecutar_fase4_modulith import (
    CatalogoService, LogisticaService, OrdenesService, ProveedorService,
)

from app import correcciones
from app.db import CLAVE_PETICION
from app.telemetria import TRACER
from lab.fallas.inyector import INYECTOR
from lab.resiliencia.config import CORRECCIONES


def modulo(target: str):
    """Span por operación de módulo + punto de falla antes de ejecutarla."""
    def deco(fn):
        @functools.wraps(fn)
        def envoltura(*args, **kwargs):
            with TRACER.start_as_current_span(target, attributes={"modulo": target.split(".")[0]}):
                INYECTOR.punto(target, clave=CLAVE_PETICION.get())
                return fn(*args, **kwargs)
        return envoltura
    return deco


class ProveedorConFallas(ProveedorService):
    def __init__(self, cursor, preparar=False):   # E2: sin sentencias preparadas (ver modulith)
        super().__init__(cursor, preparar=preparar)

    @modulo("proveedores.validar_contrato")
    def validar_contrato_vigente(self, proveedor_id, fecha_evaluacion):
        return super().validar_contrato_vigente(proveedor_id, fecha_evaluacion)


class CatalogoConFallas(CatalogoService):
    def __init__(self, cursor, preparar=False):
        super().__init__(cursor, preparar=preparar)

    @modulo("catalogo.validar_sku")
    def _validar_sku(self, proveedor_id, sku_id, fecha_evaluacion):
        return super().validar_sku_y_obtener_precio(proveedor_id, sku_id, fecha_evaluacion)

    def validar_sku_y_obtener_precio(self, proveedor_id, sku_id, fecha_evaluacion):
        llamar = lambda: self._validar_sku(proveedor_id, sku_id, fecha_evaluacion)  # noqa: E731
        if CORRECCIONES.activa("catalogo"):   # A1 corregido: timeout + breaker + último precio
            return correcciones.precio_catalogo(llamar, proveedor_id, sku_id)
        return llamar()


class LogisticaConFallas(LogisticaService):
    def __init__(self, cursor, una_franja=False, preparar=False):   # E2: UPDATE de todas las franjas
        super().__init__(cursor, una_franja=una_franja, preparar=preparar)

    @modulo("logistica.reservar_franja")
    def reservar_franja(self, cedi_id, fecha_entrega):
        return super().reservar_franja(cedi_id, fecha_entrega)


class OrdenesConFallas(OrdenesService):
    def __init__(self, cursor, prov_svc, cat_svc, log_svc, validar_estado_primero=False, preparar=False):
        super().__init__(cursor, prov_svc, cat_svc, log_svc, validar_estado_primero=validar_estado_primero,
                         preparar=preparar)

    _insert_outbox = """
        INSERT INTO ordenes.outbox_evento (aggregate_id, tipo_evento, payload)
        VALUES (%s, 'OrdenCreada', %s::jsonb);
    """

    @modulo("ordenes.crear")
    def crear_orden_transaccional(self, dto):
        super().crear_orden_transaccional(dto)
        # Outbox en la misma transacción que la orden: el worker lo publica a ext-sap.
        ord_id, prov_id, cedi_id, f_crea, f_ent, _f_rec, estado, total = dto
        payload = {"orden_id": ord_id, "proveedor_id": prov_id, "cedi_id": cedi_id,
                   "fecha_creacion": f_crea, "fecha_entrega_solicitada": f_ent,
                   "estado": estado, "total": total, "clave": CLAVE_PETICION.get()}
        # traceparent: el worker continúa la misma traza al publicar a ext-sap.
        propagate.inject(payload.setdefault("trace", {}))
        self.cursor.execute(self._insert_outbox, (ord_id, json.dumps(payload)))


def modulith(cursor) -> OrdenesConFallas:
    # La API del lab conserva el comportamiento con el que se corrieron los experimentos de
    # fallas (E2), para que sus repeticiones sean comparables: las optimizaciones del E3 sobre
    # la ruta de la Fase 4 (evidencia/optimizaciones/) quedan desactivadas aquí.
    return OrdenesConFallas(cursor, ProveedorConFallas(cursor, preparar=False),
                            CatalogoConFallas(cursor, preparar=False),
                            LogisticaConFallas(cursor, una_franja=False, preparar=False),
                            validar_estado_primero=False, preparar=False)
