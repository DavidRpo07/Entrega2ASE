"""Módulos del modulith (Entregable 2) con sus puntos de falla.

Las clases de dominio se importan sin cambios desde datos/ejecutar_fase4_modulith.py
(así `make fase4` sigue intacto); aquí solo se antepone INYECTOR.punto() a cada
operación para poder inyectar fallas focalizadas por módulo.
"""
import json

from ejecutar_fase4_modulith import (
    CatalogoService, LogisticaService, OrdenesService, ProveedorService,
)

from app.db import CLAVE_PETICION
from lab.fallas.inyector import INYECTOR


def _punto(target: str) -> None:
    INYECTOR.punto(target, clave=CLAVE_PETICION.get())


class ProveedorConFallas(ProveedorService):
    def validar_contrato_vigente(self, proveedor_id, fecha_evaluacion):
        _punto("proveedores.validar_contrato")
        return super().validar_contrato_vigente(proveedor_id, fecha_evaluacion)


class CatalogoConFallas(CatalogoService):
    def validar_sku_y_obtener_precio(self, proveedor_id, sku_id, fecha_evaluacion):
        _punto("catalogo.validar_sku")                       # A1
        return super().validar_sku_y_obtener_precio(proveedor_id, sku_id, fecha_evaluacion)


class LogisticaConFallas(LogisticaService):
    def reservar_franja(self, cedi_id, fecha_entrega):
        _punto("logistica.reservar_franja")                  # A2
        return super().reservar_franja(cedi_id, fecha_entrega)


class OrdenesConFallas(OrdenesService):
    _insert_outbox = """
        INSERT INTO ordenes.outbox_evento (aggregate_id, tipo_evento, payload)
        VALUES (%s, 'OrdenCreada', %s::jsonb);
    """

    def crear_orden_transaccional(self, dto):
        _punto("ordenes.crear")
        super().crear_orden_transaccional(dto)
        # Outbox en la misma transacción que la orden: el worker lo publica a ext-sap.
        ord_id, prov_id, cedi_id, f_crea, f_ent, _f_rec, estado, total = dto
        payload = {"orden_id": ord_id, "proveedor_id": prov_id, "cedi_id": cedi_id,
                   "fecha_creacion": f_crea, "fecha_entrega_solicitada": f_ent,
                   "estado": estado, "total": total}
        self.cursor.execute(self._insert_outbox, (ord_id, json.dumps(payload)))


def modulith(cursor) -> OrdenesConFallas:
    return OrdenesConFallas(cursor, ProveedorConFallas(cursor),
                            CatalogoConFallas(cursor), LogisticaConFallas(cursor))
