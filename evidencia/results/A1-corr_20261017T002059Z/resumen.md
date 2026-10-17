# Resultado A1-corr_20261017T002059Z

- Experimento: **A1** — Latencia fija de 800 ms en Catálogo (30 % de las llamadas)
- Configuración de la falla: `{"id": "A1", "familia": "latencia", "tipo": "latencia_fija", "target": "catalogo.validar_sku", "ms_fijos": 800, "probabilidad": 0.3, "duracion_s": 330, "semilla": 42}`
- Correcciones: **catalogo** `{"timeout_ms": 200, "breaker": {"fallos_para_abrir": 5, "semiabierto_tras_s": 30}}`
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T00:21:08.533+00:00 · falla 2026-10-17T00:26:08.565+00:00 · kill switch 2026-10-17T00:31:08.858+00:00 · fin 2026-10-17T00:33:09.732+00:00
- Predicción: no se exige (corrida con corrección o sin falla)
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792196438533&to=1792197204732

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 6002 | 0 | 20.0 | 5.6 | 18.9 | 42.2 | 0.0 | 0.0 | 0.0 | 1.2 |
| falla | 6006 | 6006 | 0 | 20.0 | 8.2 | 211.4 | 224.2 | 25.558 | 25.558 | 37.833 | 1.1 |
| recuperación | 2393 | 2393 | 0 | 20.01 | 6.1 | 28.4 | 53.4 | 0.0 | 0.0 | 0.0 | 1.2 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ✅ | ❌ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 1208 (`evidencia/logs/A1-corr_20261017T002059Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 30 (`evidencia/traces/A1-corr_20261017T002059Z/indice.csv`)
- Métricas: `evidencia/metrics/A1-corr_20261017T002059Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/A1-corr_20261017T002059Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Antes vs. después (lo completa el equipo)

| Señal | Antes | Después | Por qué |
| --- | --- | --- | --- |
| | | | |
