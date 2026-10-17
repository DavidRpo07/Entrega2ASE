"""Correcciones de la fase 4 en la API y el worker. Se encienden y apagan en caliente con
lab/runtime/correcciones.yaml (ver lab/correcciones.yaml); apagadas, el código hace
exactamente lo mismo que en la fase 3.

- catalogo (A1): timeout de 200 ms sobre catalogo.validar_sku + circuit breaker + fallback
  al último precio conocido de (proveedor, sku) en esta réplica; sin precio → 503 inmediato.
- bulkhead (A2, B1, B2): en app/db.py (pools lectura/escritura, fail-fast, lock_timeout).
- worker (D2): en app/worker.py (retry con backoff, mensajes muertos, breaker hacia ext-sap).

Al cambiar el archivo (cada corrida del runner lo reescribe) se reinician los breakers y la
caché de precios: cada corrida parte del mismo estado.
"""
import logging
import threading

from opentelemetry import trace

from app import metricas
from lab.fallas.inyector import INYECTOR, FallaInyectada, PlazoAgotado
from lab.resiliencia.breaker import CircuitBreaker
from lab.resiliencia.config import CORRECCIONES

log = logging.getLogger("correcciones")


class DependenciaNoDisponible(Exception):
    """Fallback sin datos: la API responde 503 de inmediato."""

    def __init__(self, dependencia: str, motivo: str):
        self.dependencia, self.motivo = dependencia, motivo
        super().__init__(f"{dependencia} no disponible ({motivo}) y sin último valor conocido")


# ------------------------------------------------------------------ breakers
BREAKERS: dict[str, CircuitBreaker] = {}
_SECCION: dict[str, str] = {}        # breaker → sección de correcciones.yaml con sus parámetros


def _al_cambiar(nombre: str, desde: str, hacia: str) -> None:
    metricas.BREAKER_TRANSICIONES.labels(nombre, desde, hacia).inc()
    trace.get_current_span().add_event("circuit_breaker", {"breaker": nombre, "desde": desde, "hacia": hacia})
    log.warning("circuit breaker %s: %s -> %s", nombre, desde, hacia,
                extra={"breaker": nombre, "desde": desde, "hacia": hacia})


def _crear(nombre: str) -> CircuitBreaker:
    p = CORRECCIONES.parametros(_SECCION[nombre])["breaker"]
    return CircuitBreaker(nombre, p["fallos_para_abrir"], p["semiabierto_tras_s"], al_cambiar=_al_cambiar)


def registrar_breaker(nombre: str, seccion: str) -> CircuitBreaker:
    _SECCION[nombre] = seccion
    BREAKERS[nombre] = _crear(nombre)
    return BREAKERS[nombre]


# ------------------------------------------------------------------ catálogo (A1)
_precios: dict[tuple, float] = {}
_lock = threading.Lock()


def _fallback(clave: tuple, motivo: str) -> float:
    with _lock:
        valor = _precios.get(clave)
    resultado = "hit" if valor is not None else "miss"
    metricas.CATALOGO_FALLBACK.labels(motivo, resultado).inc()
    trace.get_current_span().add_event("fallback_catalogo", {"motivo": motivo, "resultado": resultado})
    log.info("fallback de catálogo motivo=%s resultado=%s", motivo, resultado,
             extra={"motivo": motivo, "resultado": resultado, "proveedor_id": clave[0], "sku_id": clave[1]})
    if valor is None:
        raise DependenciaNoDisponible("catalogo", motivo)
    return valor


def precio_catalogo(llamar, proveedor_id, sku_id) -> float:
    """Llama a Catálogo con timeout y breaker; si no se puede, devuelve el último precio conocido."""
    clave = (proveedor_id, sku_id)
    b = BREAKERS["catalogo"]
    if not b.permite():
        return _fallback(clave, "breaker_abierto")
    try:
        with INYECTOR.plazo(CORRECCIONES.parametros("catalogo")["timeout_ms"]):
            valor = llamar()
    except PlazoAgotado:
        metricas.CATALOGO_TIMEOUTS.inc()
        b.fallo()
        return _fallback(clave, "timeout")
    except FallaInyectada:
        b.fallo()
        return _fallback(clave, "error")
    except BaseException:
        b.cancelar()
        raise
    b.exito()
    with _lock:
        _precios[clave] = valor
    return valor


# ------------------------------------------------------------------ recarga
def _reiniciar(_anterior: dict, nueva: dict) -> None:
    for nombre in list(BREAKERS):
        BREAKERS[nombre] = _crear(nombre)
    with _lock:
        _precios.clear()
    log.warning("correcciones: breakers y caché de precios reiniciados (corrida=%s)", nueva.get("corrida"))


CORRECCIONES.observadores.append(_reiniciar)
