# Resultado B1-corr_20261017T010803Z

- Experimento: **B1** — Cada consulta retiene la conexión del pool +300 ms (pool max 5 por réplica)
- Configuración de la falla: `{"id": "B1", "familia": "base_de_datos", "tipo": "retencion_conexion", "target": "db.consulta", "ms_fijos": 300, "probabilidad": 1.0, "duracion_s": 330, "semilla": 42}`
- Correcciones: **bulkhead** `{"pool_escritura": 3, "pool_lectura": 2, "pool_timeout_ms": 500, "lock_timeout_ms": 1000}`
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T01:08:13.341+00:00 · falla 2026-10-17T01:13:13.362+00:00 · kill switch 2026-10-17T01:18:13.634+00:00 · fin 2026-10-17T01:20:14.250+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792199263341&to=1792200029250

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6003 | 6003 | 0 | 20.01 | 5.6 | 12.4 | 25.3 | 0.0 | 0.0 | 0.0 | 1.1 |
| falla | 6005 | 6005 | 0 | 20.0 | 507.1 | 2580.5 | 2620.9 | 56.053 | 56.053 | 57.5 | 3.2 |
| recuperación | 2393 | 2393 | 0 | 20.01 | 5.7 | 13.7 | 29.8 | 0.0 | 0.0 | 0.0 | 2.8 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ❌ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 7595 (`evidencia/logs/B1-corr_20261017T010803Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 35 (`evidencia/traces/B1-corr_20261017T010803Z/indice.csv`)
- Métricas: `evidencia/metrics/B1-corr_20261017T010803Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/B1-corr_20261017T010803Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
