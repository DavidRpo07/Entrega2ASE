# Resultado O1-trazas-off_20261017T015738Z

- Experimento: **O1** — Overhead de observabilidad, trazas OpenTelemetry encendidas vs. TRAZAS=off, misma carga sin falla
- Sin falla: las tres fases son la misma carga (los nombres de fase quedan solo como marcas de tiempo)
- Correcciones: ninguna (sistema sin corregir)
- Trazas (OpenTelemetry): APAGADAS (TRAZAS=off)
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T01:57:42.976+00:00 · falla 2026-10-17T02:02:42.980+00:00 · kill switch 2026-10-17T02:07:42.983+00:00 · fin 2026-10-17T02:09:43.856+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792202232976&to=1792202998856

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 6002 | 0 | 20.01 | 5.3 | 9.6 | 13.4 | 0.0 | 0.0 | 0.0 | 1.1 |
| falla | 6000 | 6000 | 0 | 20.0 | 5.5 | 9.9 | 14.2 | 0.0 | 0.0 | 0.0 | 1.1 |
| recuperación | 2398 | 2398 | 0 | 20.01 | 5.5 | 9.6 | 14.2 | 0.0 | 0.0 | 0.0 | 0.9 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ✅ | ✅ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/O1-trazas-off_20261017T015738Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 0 (`evidencia/traces/O1-trazas-off_20261017T015738Z/indice.csv`)
- Métricas: `evidencia/metrics/O1-trazas-off_20261017T015738Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/O1-trazas-off_20261017T015738Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
