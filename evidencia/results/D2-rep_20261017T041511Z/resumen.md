# Resultado D2-rep_20261017T041511Z

- Experimento: **D2** — ext-sap tarda 2 s y responde 503 en el 40 % de las llamadas
- Configuración de la falla: `{"id": "D2", "familia": "disponibilidad", "tipo": "error", "target": "ext_sap.notificar", "codigo_http": 503, "ms_fijos": 2000, "probabilidad": 0.4, "duracion_s": 210, "semilla": 42}`
- Correcciones: ninguna (sistema sin corregir)
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 120 s · falla 180 s · recuperación 60 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T04:15:15.532+00:00 · falla 2026-10-17T04:17:15.548+00:00 · kill switch 2026-10-17T04:20:15.813+00:00 · fin 2026-10-17T04:21:17.788+00:00
- Predicción: `evidencia/predictions/D2.md` sha256 `b0ebf310d53b…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792210485532&to=1792210892788

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2401 | 2401 | 0 | 20.01 | 5.7 | 12.2 | 19.4 | 0.0 | 0.0 | 0.0 | 1.0 |
| falla | 3606 | 3606 | 0 | 20.01 | 6.2 | 13.4 | 28.6 | 0.0 | 0.0 | 0.0 | 179.5 |
| recuperación | 1193 | 1193 | 0 | 20.02 | 5.0 | 10.1 | 26.2 | 0.0 | 0.0 | 0.0 | 180.1 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ✅ | ✅ | ✅ | ❌ |
| recuperacion | ✅ | ✅ | ✅ | ❌ |

**Recuperación tras el kill switch:** no se recuperó dentro de la fase de recuperación (cliente 0.0, lag None)

## Evidencia

- Inyecciones registradas: 72 (`evidencia/logs/D2-rep_20261017T041511Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 11 (`evidencia/traces/D2-rep_20261017T041511Z/indice.csv`)
- Métricas: `evidencia/metrics/D2-rep_20261017T041511Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/D2-rep_20261017T041511Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
