# Resultado D2-corr_20261017T013242Z

- Experimento: **D2** — ext-sap tarda 2 s y responde 503 en el 40 % de las llamadas
- Configuración de la falla: `{"id": "D2", "familia": "disponibilidad", "tipo": "error", "target": "ext_sap.notificar", "codigo_http": 503, "ms_fijos": 2000, "probabilidad": 0.4, "duracion_s": 330, "semilla": 42}`
- Correcciones: **worker** `{"max_intentos": 3, "backoff": {"base_ms": 100, "factor": 2, "jitter": 0.5}, "breaker": {"fallos_para_abrir": 5, "semiabierto_tras_s": 30}}`
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T01:32:50.975+00:00 · falla 2026-10-17T01:37:51.003+00:00 · kill switch 2026-10-17T01:42:51.268+00:00 · fin 2026-10-17T01:44:51.816+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792200740975&to=1792201506816

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6001 | 6001 | 0 | 20.0 | 5.4 | 12.0 | 27.4 | 0.0 | 0.0 | 0.0 | 1.1 |
| falla | 6006 | 6006 | 0 | 20.0 | 6.0 | 12.1 | 27.1 | 0.0 | 0.0 | 0.0 | 296.2 |
| recuperación | 2394 | 2394 | 0 | 20.01 | 5.1 | 10.8 | 25.8 | 0.0 | 0.0 | 0.0 | 312.3 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ✅ | ✅ | ✅ | ❌ |
| recuperacion | ✅ | ✅ | ✅ | ❌ |

**Recuperación tras el kill switch:** no se recuperó dentro de la fase de recuperación (cliente 0.0, lag None)

## Evidencia

- Inyecciones registradas: 34 (`evidencia/logs/D2-corr_20261017T013242Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 15 (`evidencia/traces/D2-corr_20261017T013242Z/indice.csv`)
- Métricas: `evidencia/metrics/D2-corr_20261017T013242Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/D2-corr_20261017T013242Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
