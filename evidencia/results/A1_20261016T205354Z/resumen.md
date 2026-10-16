# Resultado A1_20261016T205354Z

- Experimento: **A1** — Latencia fija de 800 ms en Catálogo (30 % de las llamadas)
- Configuración de la falla: `{"id": "A1", "familia": "latencia", "tipo": "latencia_fija", "target": "catalogo.validar_sku", "ms_fijos": 800, "probabilidad": 0.3, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T20:54:00.099+00:00 · falla 2026-10-16T20:59:00.128+00:00 · kill switch 2026-10-16T21:04:00.148+00:00 · fin 2026-10-16T21:06:00.719+00:00
- Predicción: `evidencia/predictions/A1.md` sha256 `b8b8350361c7…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792184010099&to=1792184775719

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

| Fase | Peticiones | req/s | p50 POST ms | p95 POST ms | p99 POST ms | % errores | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 20.0 | 5.5 | 11.8 | 26.3 | 0.0 | 0.0 | 1.1 |
| falla | 6000 | 20.0 | 7.4 | 811.0 | 820.7 | 0.0 | 0.0 | 1.8 |
| recuperación | 2399 | 20.01 | 5.7 | 11.8 | 24.8 | 0.0 | 0.0 | 1.1 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ✅ | ✅ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 0.0 s (cliente 0.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 1421 (`evidencia/logs/A1_20261016T205354Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 25 (`evidencia/traces/A1_20261016T205354Z/indice.csv`)
- Métricas: `evidencia/metrics/A1_20261016T205354Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/A1_20261016T205354Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
