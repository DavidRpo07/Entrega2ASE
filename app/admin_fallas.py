"""/admin/faults: activar, consultar y apagar (kill switch) fallas sin redespliegue.

Las réplicas detrás de nginx, el worker y ext-sap son procesos distintos, así que
activar en memoria solo afectaría al proceso que recibió la petición. Por eso el
endpoint escribe el faults.yaml compartido (FAULTS_FILE, montado en todos los
contenedores); el inyector de cada proceso lo relee en <= 1 s. El proceso que
recibe la petición además recarga en el acto.
"""
import fcntl
import os
import tempfile
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app import config
from app.db import CLAVE_PETICION
from lab.fallas.inyector import (INYECTOR, RUTA_ACTUAL, ConfiguracionInvalida, FallaInyectada,
                                 epoch_de_iso, falla_desde_dict, iso_de_epoch)

router = APIRouter(prefix="/admin/faults", tags=["admin"])


def _ruta() -> Path:
    if not config.FAULTS_FILE:
        raise HTTPException(500, "FAULTS_FILE no configurado")
    return Path(config.FAULTS_FILE)


def _catalogo() -> dict[str, dict]:
    datos = yaml.safe_load(Path(config.CATALOGO_FALLAS).read_text(encoding="utf-8")) or {}
    return {f["id"]: f for f in datos.get("fallas", [])}


def _leer(ruta: Path) -> dict:
    if not ruta.exists():
        return {"kill_switch": False, "fallas": []}
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    datos.setdefault("kill_switch", False)
    datos["fallas"] = datos.get("fallas") or []
    return datos


def _vigente(f: dict, ahora: float) -> bool:
    if f.get("inicio_utc") is None or f.get("duracion_s") is None:
        return True
    try:
        return epoch_de_iso(f["inicio_utc"]) + float(f["duracion_s"]) > ahora
    except (TypeError, ValueError):
        return True   # que la valide el inyector


def _modificar(cambio) -> dict:
    """Lee-modifica-escribe faults.yaml bajo un lock de archivo y con reemplazo
    atómico (os.replace), para que ningún lector vea un YAML a medias."""
    ruta = _ruta()
    with open(ruta.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        datos = _leer(ruta)
        ahora = time.time()
        datos["fallas"] = [f for f in datos["fallas"] if _vigente(f, ahora)]  # poda las expiradas
        datos = cambio(datos)
        fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".faults-", suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Escrito por /admin/faults. Ver lab/faults.yaml para el formato.\n")
            yaml.safe_dump(datos, f, sort_keys=False, allow_unicode=True)
        os.chmod(tmp, 0o644)
        os.replace(tmp, ruta)
    INYECTOR.recargar(forzar=True)
    return datos


@router.get("")
def estado():
    return {"instancia": config.INSTANCIA, "archivo": _leer(_ruta()), **INYECTOR.estado()}


@router.post("", status_code=201)
def activar(falla: dict = Body(..., examples=[{"id": "A1"}, {"id": "A1", "probabilidad": 0.5}])):
    """Activa una falla. Con solo {"id": "A1"} se toma la entrada del catálogo;
    cualquier otro campo la sobrescribe (p. ej. probabilidad, duracion_s, target)."""
    if "id" not in falla:
        raise HTTPException(422, "falta 'id'")
    base = _catalogo().get(falla["id"], {})
    # inicio_utc: hora absoluta, para que un proceso que arranque después aplique
    # solo la duración restante (y nada si ya expiró).
    final = {**base, **falla, "inicio_utc": iso_de_epoch(time.time())}
    try:
        falla_desde_dict(dict(final))  # valida antes de escribir
    except (ConfiguracionInvalida, TypeError) as e:
        raise HTTPException(422, str(e))

    def cambio(datos):
        datos["kill_switch"] = False
        datos["fallas"] = [f for f in datos["fallas"] if f.get("id") != final["id"]] + [final]
        return datos

    return {"activada": final, "archivo": _modificar(cambio)}


@router.delete("")
def kill_switch():
    """Kill switch: apaga todas las fallas en todos los procesos."""
    apagadas = INYECTOR.kill_switch(motivo=f"DELETE /admin/faults en {config.INSTANCIA}")
    datos = _modificar(lambda d: {"kill_switch": True, "fallas": []})
    return {"kill_switch": True, "apagadas_localmente": apagadas, "archivo": datos}


@router.delete("/{falla_id}")
def desactivar(falla_id: str):
    def cambio(datos):
        datos["fallas"] = [f for f in datos["fallas"] if f.get("id") != falla_id]
        return datos
    return {"desactivada": falla_id, "archivo": _modificar(cambio)}


async def manejar_falla_inyectada(_request: Request, exc: FallaInyectada):
    return JSONResponse(status_code=exc.codigo_http,
                        content={"error": str(exc), "falla_id": exc.falla_id,
                                 "instancia": config.INSTANCIA})


async def contexto_peticion(request: Request):
    """Ruta ("POST /ordenes") para el filtro `rutas` de las fallas, y clave de la
    petición desde X-Clave-Carga (la envía k6: índice de la carga generada), para que
    la decisión de inyectar sea la misma en cada corrida."""
    ruta = getattr(request.scope.get("route"), "path", None) or request.url.path
    RUTA_ACTUAL.set(f"{request.method} {ruta}")
    clave = request.headers.get("x-clave-carga")
    if clave:
        CLAVE_PETICION.set(clave)


def instalar(app) -> None:
    """Llamar justo después de crear la app (antes de declarar rutas)."""
    app.router.dependencies.append(Depends(contexto_peticion))
    app.include_router(router)
    app.add_exception_handler(FallaInyectada, manejar_falla_inyectada)

    @app.middleware("http")
    async def cabecera_instancia(request, call_next):
        resp = await call_next(request)
        resp.headers["X-Instancia"] = config.INSTANCIA
        return resp
