"""Backoff exponencial con jitter, determinista por evento.

espera(n) = base_ms · factor^(n-1) · (1 + jitter · u),  u ∈ [0, 1)
con u derivado de (semilla, clave, n): misma semilla y mismo evento → misma espera en
cada corrida (reproducible), y eventos distintos se desfasan (sin thundering herd).
Con base 100 ms, factor 2: ~100, ~200, ~400 ms… más hasta un 50 % de jitter por defecto.
"""
import random


def espera_s(intento: int, clave, base_ms: float = 100.0, factor: float = 2.0,
             jitter: float = 0.5, semilla: int = 42) -> float:
    """Espera antes del reintento número `intento` + 1 (intento = fallos acumulados, ≥ 1)."""
    if intento < 1:
        raise ValueError("intento debe ser >= 1")
    u = random.Random(f"{semilla}|{clave}|{intento}").random()
    return base_ms * factor ** (intento - 1) * (1.0 + jitter * u) / 1000.0
