"""Lectura en caliente de correcciones.yaml (CORRECCIONES_FILE).

Igual que el inyector con faults.yaml: el archivo se revisa cada `intervalo_recarga_s` y, si
cambió, se valida y se aplica. Sin archivo (o con un archivo inválido al arrancar) todas las
correcciones quedan apagadas: el sistema se comporta como en la fase 3.

Los observadores (al_cambiar) se llaman cuando el contenido cambia; la API y el worker los
usan para reiniciar breakers y la caché de precios, así cada corrida parte del mismo estado.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import logging
import math
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import yaml

log = logging.getLogger("correcciones")

DEFECTOS = {
    "catalogo": {"activa": False, "timeout_ms": 200,
                 "breaker": {"fallos_para_abrir": 5, "semiabierto_tras_s": 30}},
    "bulkhead": {"activa": False, "pool_escritura": 3, "pool_lectura": 2,
                 "pool_timeout_ms": 500, "lock_timeout_ms": 1000},
    "worker": {"activa": False, "max_intentos": 3,
               "backoff": {"base_ms": 100, "factor": 2, "jitter": 0.5},
               "breaker": {"fallos_para_abrir": 5, "semiabierto_tras_s": 30}},
}
SECCIONES = tuple(DEFECTOS)


class ConfiguracionInvalida(ValueError):
    pass


def _fusionar(base: dict, extra: dict, ruta: str) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if k not in base:
            raise ConfiguracionInvalida(f"{ruta}.{k}: campo desconocido")
        if isinstance(base[k], dict):
            if not isinstance(v, dict):
                raise ConfiguracionInvalida(f"{ruta}.{k}: debe ser un diccionario")
            out[k] = _fusionar(base[k], v, f"{ruta}.{k}")
        elif isinstance(base[k], bool):
            if not isinstance(v, bool):
                raise ConfiguracionInvalida(f"{ruta}.{k}: debe ser true/false")
            out[k] = v
        else:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ConfiguracionInvalida(f"{ruta}.{k}: debe ser un número >= 0")
            out[k] = v
    return out


def normalizar(datos: dict) -> dict:
    """Valida y completa con los valores por defecto. Lanza ConfiguracionInvalida."""
    datos = datos or {}
    if not isinstance(datos, dict):
        raise ConfiguracionInvalida("correcciones.yaml debe ser un diccionario")
    out = {s: _fusionar(DEFECTOS[s], datos.get(s), s) for s in SECCIONES}
    b = out["bulkhead"]
    if b["pool_escritura"] < 1 or b["pool_lectura"] < 1:
        raise ConfiguracionInvalida("bulkhead: cada pool necesita al menos 1 conexión")
    if out["worker"]["max_intentos"] < 1:
        raise ConfiguracionInvalida("worker.max_intentos debe ser >= 1")
    for s in ("catalogo", "worker"):
        if out[s]["breaker"]["fallos_para_abrir"] < 1 or out[s]["breaker"]["semiabierto_tras_s"] <= 0:
            raise ConfiguracionInvalida(f"{s}.breaker: fallos_para_abrir >= 1 y semiabierto_tras_s > 0")
    exp = datos.get("experimentos") or {}
    if not isinstance(exp, dict) or any(not isinstance(v, list) or set(v) - set(SECCIONES) for v in exp.values()):
        raise ConfiguracionInvalida(f"experimentos: cada entrada es una lista de {list(SECCIONES)}")
    out["experimentos"] = exp
    out["corrida"] = datos.get("corrida")   # la escribe el runner (trazabilidad)
    return out


def escribir_activas(destino: str | Path, base: str | Path, activas: list[str], corrida: Optional[str] = None) -> dict:
    """Escribe `destino` a partir de `base` (lab/correcciones.yaml) con solo `activas` encendidas.
    Bajo lock de archivo y con reemplazo atómico (ningún lector ve un YAML a medias). Lo usan
    PUT /admin/correcciones y el runner (desde dentro de fallas-ext, como el kill switch)."""
    destino, base = Path(destino), Path(base)
    desconocidas = set(activas) - set(SECCIONES)
    if desconocidas:
        raise ConfiguracionInvalida(f"correcciones desconocidas: {sorted(desconocidas)} (válidas: {list(SECCIONES)})")
    datos = yaml.safe_load(base.read_text(encoding="utf-8")) or {}
    for s in SECCIONES:
        datos.setdefault(s, {})["activa"] = s in activas
    datos["corrida"] = corrida
    normalizar(copy.deepcopy(datos))     # valida antes de escribir
    with open(destino.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".correcciones-", suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"# Escrito a partir de {base.name}: activas={sorted(activas)}. Ver lab/correcciones.yaml.\n")
            yaml.safe_dump(datos, f, sort_keys=False, allow_unicode=True)
        os.chmod(tmp, 0o644)
        os.replace(tmp, destino)
    return datos


class Correcciones:
    def __init__(self, ruta: Optional[str | Path] = None, intervalo_recarga_s: float = 1.0,
                 reloj: Callable[[], float] = time.monotonic):
        self._ruta = Path(ruta) if ruta else None
        self._intervalo = intervalo_recarga_s
        self._reloj = reloj
        self._lock = threading.RLock()
        self._ultima_revision = -math.inf
        self._huella = None
        self._config = normalizar({})
        self.observadores: list[Callable[[dict, dict], None]] = []
        self.recargar(forzar=True)

    def recargar(self, forzar: bool = False) -> bool:
        if not self._ruta:
            return False
        with self._lock:
            ahora = self._reloj()
            if not forzar and ahora - self._ultima_revision < self._intervalo:
                return False
            self._ultima_revision = ahora
            # Se compara el contenido (archivo pequeño), no el mtime: dos escrituras seguidas del
            # runner pueden caer en el mismo instante según la resolución del montaje.
            try:
                texto = self._ruta.read_text(encoding="utf-8")
            except FileNotFoundError:
                texto = ""
            huella = hashlib.sha256(texto.encode()).hexdigest()
            if huella == self._huella:
                return False
            try:
                nueva = normalizar(yaml.safe_load(texto) or {})
            except (yaml.YAMLError, ConfiguracionInvalida) as e:
                # Se conserva la configuración vigente (al arrancar: todo apagado).
                log.error("correcciones.yaml inválido, se conserva la configuración anterior: %s", e)
                self._huella = huella
                return False
            anterior, self._config, self._huella = self._config, nueva, huella
        log.warning("correcciones recargadas: activas=%s corrida=%s", self.activas(recargar=False), nueva["corrida"])
        for obs in self.observadores:
            obs(anterior, nueva)
        return True

    def activa(self, seccion: str) -> bool:
        self.recargar()
        return bool(self._config[seccion]["activa"])

    def parametros(self, seccion: str) -> dict:
        self.recargar()
        return self._config[seccion]

    def activas(self, recargar: bool = True) -> list[str]:
        if recargar:
            self.recargar()
        return [s for s in SECCIONES if self._config[s]["activa"]]

    def estado(self) -> dict:
        self.recargar()
        return copy.deepcopy(self._config)


CORRECCIONES = Correcciones(os.environ.get("CORRECCIONES_FILE") or None,
                            intervalo_recarga_s=float(os.environ.get("CORRECCIONES_RECARGA_S", "1.0")))
