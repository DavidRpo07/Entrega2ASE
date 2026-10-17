# Resultado A2-corr_20261017T005544Z

- Experimento: **A2** — Jitter lognormal en Logística (mediana ~245 ms, cola > 2 s)
- Configuración de la falla: `{"id": "A2", "familia": "latencia", "tipo": "latencia_lognormal", "target": "logistica.reservar_franja", "mu": 5.5, "sigma": 1.0, "max_ms": 10000, "probabilidad": 1.0, "duracion_s": 330, "semilla": 42}`
- Correcciones: **bulkhead** `{"pool_escritura": 3, "pool_lectura": 2, "pool_timeout_ms": 500, "lock_timeout_ms": 1000}`
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T00:55:52.566+00:00 · falla 2026-10-17T01:00:52.589+00:00 · kill switch 2026-10-17T01:05:52.935+00:00 · fin 2026-10-17T01:07:53.404+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792198522566&to=1792199288404

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 6002 | 0 | 20.01 | 5.3 | 11.8 | 27.9 | 0.0 | 0.0 | 0.0 | 1.2 |
| falla | 6007 | 6007 | 0 | 20.0 | 462.3 | 1325.7 | 2487.8 | 6.476 | 6.476 | 8.083 | 4.0 |
| recuperación | 2392 | 2392 | 0 | 20.01 | 5.6 | 12.9 | 29.0 | 0.0 | 0.0 | 0.0 | 1.1 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ❌ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 3808 (`evidencia/logs/A2-corr_20261017T005544Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 35 (`evidencia/traces/A2-corr_20261017T005544Z/indice.csv`)
- Métricas: `evidencia/metrics/A2-corr_20261017T005544Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/A2-corr_20261017T005544Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
