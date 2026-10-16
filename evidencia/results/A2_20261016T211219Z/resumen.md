# Resultado A2_20261016T211219Z

- Experimento: **A2** — Jitter lognormal en Logística (mediana ~245 ms, cola > 2 s)
- Configuración de la falla: `{"id": "A2", "familia": "latencia", "tipo": "latencia_lognormal", "target": "logistica.reservar_franja", "mu": 5.5, "sigma": 1.0, "max_ms": 10000, "probabilidad": 1.0, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T21:12:23.401+00:00 · falla 2026-10-16T21:17:23.425+00:00 · kill switch 2026-10-16T21:22:23.443+00:00 · fin 2026-10-16T21:24:23.912+00:00
- Predicción: `evidencia/predictions/A2.md` sha256 `e15c49f91488…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792185113401&to=1792185878912

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

| Fase | Peticiones | req/s | p50 POST ms | p95 POST ms | p99 POST ms | % errores | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6001 | 20.0 | 5.8 | 13.6 | 30.4 | 0.0 | 0.0 | 1.3 |
| falla | 6000 | 20.0 | 263.2 | 1203.7 | 2381.0 | 0.0 | 0.0 | 4.0 |
| recuperación | 2400 | 20.01 | 5.3 | 11.3 | 25.4 | 0.0 | 0.0 | 0.9 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 4193 (`evidencia/logs/A2_20261016T211219Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 25 (`evidencia/traces/A2_20261016T211219Z/indice.csv`)
- Métricas: `evidencia/metrics/A2_20261016T211219Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/A2_20261016T211219Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
