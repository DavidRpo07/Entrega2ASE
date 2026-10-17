# Resultado B2-corr-rep_20261017T040853Z

- Experimento: **B2** — SELECT ... FOR UPDATE de 30 s cada 60 s sobre las franjas del CEDI 5
- Configuración de la falla: `{"id": "B2", "familia": "base_de_datos", "tipo": "externa", "target": "logistica.franja_descargue", "parametros": {"cedi_id": 5, "retencion_s": 30, "ciclo_s": 60}, "duracion_s": 210, "semilla": 42}`
- Correcciones: **bulkhead** `{"pool_escritura": 3, "pool_lectura": 2, "pool_timeout_ms": 500, "lock_timeout_ms": 1000}`
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 120 s · falla 180 s · recuperación 60 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T04:09:02.053+00:00 · falla 2026-10-17T04:11:02.082+00:00 · kill switch 2026-10-17T04:14:02.388+00:00 · fin 2026-10-17T04:15:03.366+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792210112053&to=1792210518366

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2402 | 2402 | 0 | 20.01 | 5.8 | 12.4 | 25.8 | 0.0 | 0.0 | 0.0 | 1.0 |
| falla | 3606 | 3606 | 0 | 20.01 | 7.0 | 1008.9 | 1109.0 | 7.404 | 7.404 | 7.417 | 1.1 |
| recuperación | 1192 | 1192 | 0 | 20.02 | 5.5 | 11.8 | 23.7 | 0.0 | 0.0 | 0.0 | 1.0 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ❌ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/B2-corr-rep_20261017T040853Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 35 (`evidencia/traces/B2-corr-rep_20261017T040853Z/indice.csv`)
- Métricas: `evidencia/metrics/B2-corr-rep_20261017T040853Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/B2-corr-rep_20261017T040853Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
