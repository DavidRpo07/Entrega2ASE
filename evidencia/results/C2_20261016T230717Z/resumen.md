# Resultado C2_20261016T230717Z

- Experimento: **C2** — Consumidor del outbox pausado
- Configuración de la falla: `{"id": "C2", "familia": "degradacion", "tipo": "pausa", "target": "worker.outbox", "duracion_s": 180, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T23:07:22.961+00:00 · falla 2026-10-16T23:12:22.988+00:00 · kill switch 2026-10-16T23:17:23.270+00:00 · fin 2026-10-16T23:19:23.625+00:00
- Predicción: `evidencia/predictions/C2.md` sha256 `70b3c08b956e…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792192012961&to=1792192778625

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 6002 | 0 | 20.0 | 5.5 | 14.4 | 26.5 | 0.0 | 0.0 | 0.0 | 1.2 |
| falla | 6005 | 6005 | 0 | 20.0 | 5.6 | 23.1 | 97.4 | 0.0 | 0.0 | 0.0 | 178.5 |
| recuperación | 2394 | 2394 | 0 | 20.01 | 5.8 | 17.8 | 43.2 | 0.0 | 0.0 | 0.0 | 1.1 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ✅ | ✅ | ✅ | ❌ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/C2_20261016T230717Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 18 (`evidencia/traces/C2_20261016T230717Z/indice.csv`)
- Métricas: `evidencia/metrics/C2_20261016T230717Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/C2_20261016T230717Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
