# Resultado D1_20261016T232015Z

- Experimento: **D1** — Caída de api-2: docker stop al min 1 de la falla, start al min 4
- Configuración de la falla: `{"id": "D1", "familia": "disponibilidad", "tipo": "externa", "target": "api-2", "parametros": {"servicio": "api-2", "caida_tras_s": 60, "caida_s": 180}, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T23:20:19.438+00:00 · falla 2026-10-16T23:25:19.463+00:00 · kill switch 2026-10-16T23:30:19.755+00:00 · fin 2026-10-16T23:32:20.048+00:00
- Predicción: `evidencia/predictions/D1.md` sha256 `e7e682cfd9f1…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792192789438&to=1792193555048

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6001 | 6001 | 0 | 20.0 | 5.6 | 19.0 | 37.4 | 0.0 | 0.0 | 0.0 | 1.2 |
| falla | 6006 | 6006 | 0 | 20.0 | 5.3 | 16.8 | 32.3 | 0.0 | 0.0 | 0.0 | 1.3 |
| recuperación | 2394 | 2394 | 0 | 20.02 | 5.6 | 17.2 | 31.4 | 0.0 | 0.0 | 0.0 | 1.0 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ✅ | ✅ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/D1_20261016T232015Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 10 (`evidencia/traces/D1_20261016T232015Z/indice.csv`)
- Métricas: `evidencia/metrics/D1_20261016T232015Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/D1_20261016T232015Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
