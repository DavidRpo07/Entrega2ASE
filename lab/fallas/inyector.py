"""Inyector de fallas configurable — Entregable 3.

Cumple las cinco condiciones de "falla configurable":
  1. Sin redespliegue: se lee de faults.yaml (recarga en caliente) o se activa
     en memoria con activar() (lo usa POST /admin/faults).
  2. Parametrizada: intensidad, probabilidad, % de tráfico, duración.
  3. Focalizable: cada falla apunta a un "punto de falla" (target) por nombre.
  4. Reversible: kill_switch() apaga todo en el acto.
  5. Reproducible: cada falla tiene su propia semilla; misma configuración +
     misma semilla + misma secuencia de llamadas = mismas decisiones.

Uso en el código del modulith:

    from lab.fallas.inyector import INYECTOR

    def validar_sku_y_obtener_precio(self, ...):
        INYECTOR.punto("catalogo.validar_sku")   # aplica la falla si hay una activa
        ...

o como decorador:  @punto_de_falla("catalogo.validar_sku")
"""
from __future__ import annotations

import functools
import logging
import math
import os
import random
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

import yaml

log = logging.getLogger("fallas")

# Tipos soportados por el inyector en proceso. B2 (bloqueo en BD) y D1 (caída de
# instancia) se ejecutan con scripts externos del runner, pero se registran aquí
# como "externa" para que aparezcan en el estado y en las métricas.
TIPOS = {
    "latencia_fija",       # A1: duerme ms_fijos
    "latencia_lognormal",  # A2: duerme exp(N(mu, sigma)) ms
    "retencion_conexion",  # B1: duerme mientras retiene la conexión del pool
    "error",               # D2: lanza FallaInyectada con codigo_http
    "cpu",                 # C1: hilos quemando CPU mientras la falla está activa
    "pausa",               # C2: el consumidor consulta pausado() y espera
    "externa",             # B2, D1: solo registro (los ejecuta el runner)
}


class FallaInyectada(Exception):
    """Error producido por el inyector. La API la traduce a codigo_http."""

    def __init__(self, falla_id: str, codigo_http: int = 503, mensaje: str = ""):
        self.falla_id = falla_id
        self.codigo_http = codigo_http
        super().__init__(mensaje or f"Falla inyectada {falla_id} (HTTP {codigo_http})")


class ConfiguracionInvalida(ValueError):
    pass


@dataclass
class Falla:
    id: str
    tipo: str
    target: str
    familia: str = ""
    descripcion: str = ""
    habilitada: bool = True
    probabilidad: float = 1.0         # 0..1, por llamada
    porcentaje_trafico: float = 100.0  # 0..100, se decide por clave de petición
    duracion_s: Optional[float] = None  # None = hasta kill switch
    semilla: int = 42
    # parámetros de intensidad (según tipo)
    ms_fijos: float = 0.0
    mu: float = 0.0
    sigma: float = 0.0
    max_ms: float = 30_000.0
    codigo_http: int = 503
    hilos: int = 1
    carga_cpu: float = 0.9            # fracción de un núcleo por hilo
    # estado (no se configura)
    activada_en: Optional[float] = field(default=None, repr=False)
    _rng: random.Random = field(default=None, repr=False, compare=False)

    def validar(self) -> None:
        if self.tipo not in TIPOS:
            raise ConfiguracionInvalida(f"{self.id}: tipo '{self.tipo}' no soportado ({sorted(TIPOS)})")
        if not 0.0 <= self.probabilidad <= 1.0:
            raise ConfiguracionInvalida(f"{self.id}: probabilidad debe estar entre 0 y 1")
        if not 0.0 <= self.porcentaje_trafico <= 100.0:
            raise ConfiguracionInvalida(f"{self.id}: porcentaje_trafico debe estar entre 0 y 100")
        if self.duracion_s is not None and self.duracion_s <= 0:
            raise ConfiguracionInvalida(f"{self.id}: duracion_s debe ser positiva")
        if self.tipo == "latencia_lognormal" and self.sigma <= 0:
            raise ConfiguracionInvalida(f"{self.id}: latencia_lognormal requiere sigma > 0")
        if self.tipo == "error" and not 400 <= self.codigo_http <= 599:
            raise ConfiguracionInvalida(f"{self.id}: codigo_http debe ser 4xx o 5xx")
        if not 0.0 < self.carga_cpu <= 1.0:
            raise ConfiguracionInvalida(f"{self.id}: carga_cpu debe estar en (0, 1]")

    def publica(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        return d


_CAMPOS = {f for f in Falla.__dataclass_fields__ if not f.startswith("_") and f != "activada_en"}


def falla_desde_dict(d: dict) -> Falla:
    desconocidos = set(d) - _CAMPOS
    if desconocidos:
        raise ConfiguracionInvalida(f"{d.get('id', '?')}: campos desconocidos {sorted(desconocidos)}")
    for requerido in ("id", "tipo", "target"):
        if requerido not in d:
            raise ConfiguracionInvalida(f"falta el campo '{requerido}' en {d}")
    f = Falla(**d)
    f.validar()
    return f


class Inyector:
    """Registro de fallas activas, thread-safe."""

    def __init__(self, ruta_config: Optional[str | Path] = None,
                 reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], None] = time.sleep,
                 intervalo_recarga_s: float = 1.0,
                 instancia: Optional[str] = None):
        self.instancia = instancia or os.environ.get("INSTANCIA", "local")
        self._lock = threading.RLock()
        self._fallas: dict[str, Falla] = {}
        self._reloj = reloj
        self._dormir = dormir
        self._ruta = Path(ruta_config) if ruta_config else None
        self._mtime: Optional[float] = None
        self._ultima_revision = -math.inf
        self._intervalo = intervalo_recarga_s
        self._cpu_hilos: dict[str, list[threading.Thread]] = {}
        self._cpu_stop: dict[str, threading.Event] = {}
        self.contadores: dict[str, int] = {}          # inyecciones aplicadas por falla
        self.observadores: list[Callable[[str, Falla], None]] = []  # p. ej. métricas Prometheus
        if self._ruta:
            self.recargar(forzar=True)

    # ------------------------------------------------------------------ config
    def recargar(self, forzar: bool = False) -> bool:
        """Relee faults.yaml si cambió. Devuelve True si aplicó cambios."""
        if not self._ruta:
            return False
        ahora = self._reloj()
        if not forzar and ahora - self._ultima_revision < self._intervalo:
            return False
        self._ultima_revision = ahora
        try:
            mtime = self._ruta.stat().st_mtime
        except FileNotFoundError:
            mtime = None
        if not forzar and mtime == self._mtime:
            return False
        self._mtime = mtime
        datos = {}
        if mtime is not None:
            datos = yaml.safe_load(self._ruta.read_text(encoding="utf-8")) or {}
        if datos.get("kill_switch"):
            self.kill_switch(motivo="kill_switch: true en archivo")
            return True
        nuevas = [falla_desde_dict(d) for d in datos.get("fallas", []) or []]
        with self._lock:
            ids_nuevos = {f.id for f in nuevas if f.habilitada}
            for fid in list(self._fallas):
                if fid not in ids_nuevos:
                    self._desactivar(fid)
            for f in nuevas:
                if not f.habilitada:
                    continue
                previa = self._fallas.get(f.id)
                if previa and previa.publica() | {"activada_en": None} == f.publica():
                    continue  # sin cambios: conserva semilla avanzada y reloj
                self._activar(f)
        log.info("faults.yaml recargado: %s", sorted(self._fallas))
        return True

    def activar(self, config: dict) -> Falla:
        """Activa (o reemplaza) una falla en memoria. Lo usa POST /admin/faults."""
        f = falla_desde_dict(config)
        with self._lock:
            self._activar(f)
        return f

    def desactivar(self, falla_id: str) -> bool:
        with self._lock:
            return self._desactivar(falla_id)

    def kill_switch(self, motivo: str = "manual") -> list[str]:
        """Apaga todas las fallas de inmediato."""
        with self._lock:
            ids = list(self._fallas)
            for fid in ids:
                self._desactivar(fid)
        log.warning("KILL SWITCH (%s): desactivadas %s", motivo, ids)
        return ids

    def _activar(self, f: Falla) -> None:
        if f.id in self._fallas:
            self._desactivar(f.id)
        f.activada_en = self._reloj()
        f._rng = random.Random(f"{f.semilla}:{f.id}")
        self._fallas[f.id] = f
        self.contadores.setdefault(f.id, 0)
        if f.tipo == "cpu" and f.target in (self.instancia, "*"):
            self._arrancar_cpu(f)
        log.warning("falla activada %s tipo=%s target=%s", f.id, f.tipo, f.target)
        for obs in self.observadores:
            obs("activada", f)

    def _desactivar(self, fid: str) -> bool:
        f = self._fallas.pop(fid, None)
        if not f:
            return False
        ev = self._cpu_stop.pop(fid, None)
        if ev:
            ev.set()
            self._cpu_hilos.pop(fid, None)
        log.warning("falla desactivada %s", fid)
        for obs in self.observadores:
            obs("desactivada", f)
        return True

    # ------------------------------------------------------------------ estado
    def _expirar(self) -> None:
        ahora = self._reloj()
        for fid, f in list(self._fallas.items()):
            if f.duracion_s is not None and ahora - f.activada_en >= f.duracion_s:
                self._desactivar(fid)

    def activas(self) -> list[Falla]:
        self.recargar()
        with self._lock:
            self._expirar()
            return list(self._fallas.values())

    def estado(self) -> dict:
        return {
            "activas": [f.publica() for f in self.activas()],
            "contadores": dict(self.contadores),
        }

    # ------------------------------------------------------------------ decisión
    @staticmethod
    def _en_porcentaje(falla_id: str, clave: str, porcentaje: float) -> bool:
        """Decide si una petición cae en el % de tráfico afectado.
        Es determinista por clave (p. ej. id de orden): la misma petición
        siempre cae del mismo lado, independiente del orden de llegada."""
        if porcentaje >= 100.0:
            return True
        if porcentaje <= 0.0:
            return False
        h = random.Random(f"{falla_id}|{clave}").random()
        return h * 100.0 < porcentaje

    def _aplica(self, f: Falla, clave: Optional[str]) -> bool:
        if clave is not None and not self._en_porcentaje(f.id, clave, f.porcentaje_trafico):
            return False
        if clave is None and f.porcentaje_trafico < 100.0:
            # sin clave, el % de tráfico se trata como probabilidad adicional
            if f._rng.random() * 100.0 >= f.porcentaje_trafico:
                return False
        return f._rng.random() < f.probabilidad

    def _coincide(self, f: Falla, target: str) -> bool:
        # "catalogo.*" coincide con "catalogo.validar_sku"
        if f.target.endswith(".*"):
            return target.startswith(f.target[:-1])
        return f.target == target

    # ------------------------------------------------------------------ efectos
    def punto(self, target: str, clave: Optional[str] = None) -> float:
        """Aplica las fallas activas sobre este punto. Devuelve ms de retraso
        inyectados (útil para logs/trazas). Puede lanzar FallaInyectada."""
        retraso_ms = 0.0
        for f in self.activas():
            if f.tipo in ("cpu", "pausa", "externa") or not self._coincide(f, target):
                continue
            with self._lock:
                if not self._aplica(f, clave):
                    continue
                if f.tipo == "latencia_lognormal":
                    ms = min(math.exp(f._rng.gauss(f.mu, f.sigma)), f.max_ms)
                elif f.tipo in ("latencia_fija", "retencion_conexion"):
                    ms = f.ms_fijos
                else:
                    ms = 0.0
                self.contadores[f.id] = self.contadores.get(f.id, 0) + 1
            for obs in self.observadores:
                obs("inyectada", f)
            log.info("falla inyectada id=%s target=%s ms=%.1f", f.id, target, ms)
            if f.tipo == "error":
                raise FallaInyectada(f.id, f.codigo_http)
            if ms > 0:
                self._dormir(ms / 1000.0)
                retraso_ms += ms
        return retraso_ms

    def pausado(self, target: str) -> bool:
        """Para consumidores (C2): True mientras haya una falla 'pausa' activa."""
        return any(f.tipo == "pausa" and self._coincide(f, target) for f in self.activas())

    def _arrancar_cpu(self, f: Falla) -> None:
        stop = threading.Event()
        self._cpu_stop[f.id] = stop
        periodo = 0.1

        def quemar():
            while not stop.is_set():
                fin = time.perf_counter() + periodo * f.carga_cpu
                while time.perf_counter() < fin and not stop.is_set():
                    pass
                stop.wait(periodo * (1.0 - f.carga_cpu))

        hilos = [threading.Thread(target=quemar, daemon=True, name=f"cpu-{f.id}-{i}") for i in range(f.hilos)]
        self._cpu_hilos[f.id] = hilos
        for h in hilos:
            h.start()
        if f.duracion_s is not None:
            # garantiza que la CPU se libere aunque nadie consulte activas()
            t = threading.Timer(f.duracion_s, lambda: self.activas())
            t.daemon = True
            t.start()


def punto_de_falla(target: str, inyector: Optional["Inyector"] = None):
    """Decorador: aplica las fallas del target antes de ejecutar la función."""
    def deco(fn):
        @functools.wraps(fn)
        def envoltura(*args, **kwargs):
            (inyector or INYECTOR).punto(target)
            return fn(*args, **kwargs)
        return envoltura
    return deco


INYECTOR = Inyector(os.environ.get("FAULTS_FILE")) if os.environ.get("FAULTS_FILE") else Inyector()
