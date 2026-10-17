# Resultado A1-rep_20261017T040244Z

- Experimento: **A1** — Latencia fija de 800 ms en Catálogo (30 % de las llamadas)
- Configuración de la falla: `{"id": "A1", "familia": "latencia", "tipo": "latencia_fija", "target": "catalogo.validar_sku", "ms_fijos": 800, "probabilidad": 0.3, "duracion_s": 210, "semilla": 42}`
- Correcciones: ninguna (sistema sin corregir)
- Trazas (OpenTelemetry): encendidas
- Fases: baseline 120 s · falla 180 s · recuperación 60 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-17T04:02:49.437+00:00 · falla 2026-10-17T04:04:49.457+00:00 · kill switch 2026-10-17T04:07:49.733+00:00 · fin 2026-10-17T04:08:50.676+00:00
- Predicción: `evidencia/predictions/A1.md` sha256 `b8b8350361c7…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792209739437&to=1792210145676

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2402 | 2402 | 0 | 20.01 | 6.0 | 14.8 | 32.1 | 0.0 | 0.0 | 0.0 | 1.1 |
| falla | 3605 | 3605 | 0 | 20.01 | 8.2 | 813.0 | 837.6 | 0.0 | 0.0 | 0.0 | 1.9 |
| recuperación | 1193 | 1193 | 0 | 20.02 | 5.5 | 10.8 | 19.7 | 0.0 | 0.0 | 0.0 | 1.7 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 838 (`evidencia/logs/A1-rep_20261017T040244Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 25 (`evidencia/traces/A1-rep_20261017T040244Z/indice.csv`)
- Métricas: `evidencia/metrics/A1-rep_20261017T040244Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/A1-rep_20261017T040244Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
