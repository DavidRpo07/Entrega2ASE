# Resultado B2_20261016T224212Z

- Experimento: **B2** — SELECT ... FOR UPDATE de 30 s cada 60 s sobre las franjas del CEDI 5
- Configuración de la falla: `{"id": "B2", "familia": "base_de_datos", "tipo": "externa", "target": "logistica.franja_descargue", "parametros": {"cedi_id": 5, "retencion_s": 30, "ciclo_s": 60}, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T22:42:17.348+00:00 · falla 2026-10-16T22:47:17.387+00:00 · kill switch 2026-10-16T22:52:17.638+00:00 · fin 2026-10-16T22:54:18.024+00:00
- Predicción: `evidencia/predictions/B2.md` sha256 `b149687b0ff0…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792190507348&to=1792191273024

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6003 | 6003 | 0 | 20.01 | 5.5 | 13.9 | 31.4 | 0.0 | 0.0 | 0.0 | 1.3 |
| falla | 6005 | 6005 | 0 | 20.0 | 9.0 | 10417.8 | 25735.0 | 24.796 | 24.796 | 26.167 | 4.6 |
| recuperación | 2393 | 2393 | 0 | 20.01 | 5.3 | 15.2 | 28.4 | 0.0 | 0.0 | 0.0 | 1.1 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ❌ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 0 (`evidencia/logs/B2_20261016T224212Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 35 (`evidencia/traces/B2_20261016T224212Z/indice.csv`)
- Métricas: `evidencia/metrics/B2_20261016T224212Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/B2_20261016T224212Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
