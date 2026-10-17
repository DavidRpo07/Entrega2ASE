"""Circuit breaker con estados cerrado / abierto / semiabierto.

- Cerrado: deja pasar; cuenta fallos consecutivos y abre al llegar a `fallos_para_abrir`.
- Abierto: rechaza sin llamar a la dependencia (el llamador usa su fallback).
- Semiabierto: pasados `semiabierto_tras_s` desde que abrió, deja pasar UNA llamada de
  prueba; si sale bien cierra, si falla vuelve a abrir. Las demás se rechazan mientras
  la prueba está en curso.

Quien obtiene permiso con permite() debe reportar exito(), fallo() o cancelar() (este
último si la llamada terminó por otra causa que no dice nada de la dependencia).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

CERRADO, SEMIABIERTO, ABIERTO = "cerrado", "semiabierto", "abierto"
VALOR = {CERRADO: 0, SEMIABIERTO: 1, ABIERTO: 2}   # para la métrica circuit_breaker_estado


class CircuitBreaker:
    def __init__(self, nombre: str, fallos_para_abrir: int = 5, semiabierto_tras_s: float = 30.0,
                 reloj: Callable[[], float] = time.monotonic,
                 al_cambiar: Optional[Callable[[str, str, str], None]] = None):
        if fallos_para_abrir < 1 or semiabierto_tras_s <= 0:
            raise ValueError("fallos_para_abrir >= 1 y semiabierto_tras_s > 0")
        self.nombre = nombre
        self.fallos_para_abrir = fallos_para_abrir
        self.semiabierto_tras_s = semiabierto_tras_s
        self._reloj = reloj
        self._al_cambiar = al_cambiar
        self._lock = threading.Lock()
        self._estado = CERRADO
        self._fallos = 0
        self._abierto_en = 0.0
        self._prueba_en_curso = False
        self.rechazos = 0

    def _pasar(self, nuevo: str) -> None:
        anterior, self._estado = self._estado, nuevo
        if nuevo == ABIERTO:
            self._abierto_en = self._reloj()
        if nuevo != SEMIABIERTO:
            self._prueba_en_curso = False
        if anterior != nuevo and self._al_cambiar:
            self._al_cambiar(self.nombre, anterior, nuevo)

    def _actualizar(self) -> str:
        if self._estado == ABIERTO and self._reloj() - self._abierto_en >= self.semiabierto_tras_s:
            self._pasar(SEMIABIERTO)
        return self._estado

    @property
    def estado(self) -> str:
        with self._lock:
            return self._actualizar()

    def permite(self) -> bool:
        with self._lock:
            e = self._actualizar()
            if e == CERRADO:
                return True
            if e == SEMIABIERTO and not self._prueba_en_curso:
                self._prueba_en_curso = True
                return True
            self.rechazos += 1
            return False

    def exito(self) -> None:
        with self._lock:
            self._fallos = 0
            if self._estado != CERRADO:
                self._pasar(CERRADO)

    def fallo(self) -> None:
        with self._lock:
            e = self._actualizar()
            if e == SEMIABIERTO:
                self._pasar(ABIERTO)          # la prueba falló: otros semiabierto_tras_s abierto
                return
            self._fallos += 1
            if e == CERRADO and self._fallos >= self.fallos_para_abrir:
                self._pasar(ABIERTO)

    def cancelar(self) -> None:
        """La llamada de prueba terminó sin veredicto: libera el turno de prueba."""
        with self._lock:
            self._prueba_en_curso = False

    def reiniciar(self) -> None:
        with self._lock:
            self._fallos = 0
            self.rechazos = 0
            self._pasar(CERRADO)
