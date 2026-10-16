# Resultado C1_20261016T225444Z

- Experimento: **C1** — Saturación de CPU en api-1 (2 hilos al 90 %)
- Configuración de la falla: `{"id": "C1", "familia": "degradacion", "tipo": "cpu", "target": "api-1", "hilos": 2, "carga_cpu": 0.9, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T22:54:48.873+00:00 · falla 2026-10-16T22:59:48.997+00:00 · kill switch 2026-10-16T23:04:49.270+00:00 · fin 2026-10-16T23:06:50.202+00:00
- Predicción: `evidencia/predictions/C1.md` sha256 `8e445264941d…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792191258873&to=1792192025202

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6003 | 6003 | 0 | 20.0 | 5.7 | 15.0 | 29.9 | 0.0 | 0.0 | 0.0 | 1.3 |
| falla | 6006 | 6006 | 0 | 20.0 | 45.9 | 429.7 | 592.2 | 0.0 | 0.0 | 0.0 | 1.5 |
| recuperación | 2392 | 2392 | 0 | 20.01 | 5.4 | 15.0 | 29.5 | 0.0 | 0.0 | 0.0 | 0.9 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/C1_20261016T225444Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 25 (`evidencia/traces/C1_20261016T225444Z/indice.csv`)
- Métricas: `evidencia/metrics/C1_20261016T225444Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/C1_20261016T225444Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
