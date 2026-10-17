# Resultado O1-trazas-on_20261017T014501Z

- Experimento: **O1** — Overhead de observabilidad, trazas OpenTelemetry encendidas vs. TRAZAS=off, misma carga sin falla
- Sin falla: las tres fases son la misma carga (los nombres de fase quedan solo como marcas de tiempo)
- Correcciones: ninguna (sistema sin corregir)
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T01:45:06.933+00:00 · falla 2026-10-17T01:50:06.937+00:00 · kill switch 2026-10-17T01:55:06.942+00:00 · fin 2026-10-17T01:57:07.986+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792201476933&to=1792202242986

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6001 | 6001 | 0 | 20.0 | 5.5 | 12.5 | 27.6 | 0.0 | 0.0 | 0.0 | 104.6 |
| falla | 6000 | 6000 | 0 | 20.0 | 5.7 | 13.1 | 28.2 | 0.0 | 0.0 | 0.0 | 1.2 |
| recuperación | 2400 | 2400 | 0 | 20.01 | 5.8 | 14.0 | 53.9 | 0.0 | 0.0 | 0.0 | 1.5 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ❌ |
| falla | ✅ | ✅ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/O1-trazas-on_20261017T014501Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 10 (`evidencia/traces/O1-trazas-on_20261017T014501Z/indice.csv`)
- Métricas: `evidencia/metrics/O1-trazas-on_20261017T014501Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/O1-trazas-on_20261017T014501Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
