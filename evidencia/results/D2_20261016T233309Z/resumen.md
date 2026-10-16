# Resultado D2_20261016T233309Z

- Experimento: **D2** — ext-sap tarda 2 s y responde 503 en el 40 % de las llamadas
- Configuración de la falla: `{"id": "D2", "familia": "disponibilidad", "tipo": "error", "target": "ext_sap.notificar", "codigo_http": 503, "ms_fijos": 2000, "probabilidad": 0.4, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T23:33:13.910+00:00 · falla 2026-10-16T23:38:13.939+00:00 · kill switch 2026-10-16T23:43:14.241+00:00 · fin 2026-10-16T23:45:15.089+00:00
- Predicción: `evidencia/predictions/D2.md` sha256 `b0ebf310d53b…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792193563910&to=1792194330089

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 6002 | 0 | 20.0 | 5.8 | 19.0 | 35.6 | 0.0 | 0.0 | 0.0 | 1.4 |
| falla | 6006 | 6006 | 0 | 20.0 | 6.2 | 19.8 | 44.5 | 0.0 | 0.0 | 0.0 | 296.5 |
| recuperación | 2393 | 2393 | 0 | 20.01 | 5.3 | 18.7 | 44.6 | 0.0 | 0.0 | 0.0 | 300.5 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ✅ | ✅ | ✅ | ❌ |
| recuperacion | ✅ | ✅ | ✅ | ❌ |

**Recuperación tras el kill switch:** no se recuperó dentro de la fase de recuperación (cliente 0.0, lag None)

## Evidencia

- Inyecciones registradas: 119 (`evidencia/logs/D2_20261016T233309Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 11 (`evidencia/traces/D2_20261016T233309Z/indice.csv`)
- Métricas: `evidencia/metrics/D2_20261016T233309Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/D2_20261016T233309Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
