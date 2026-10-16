> **B1 intento 1 — inválida: kill switch atascado en la API saturada.**
> Corrida original `B1_20261016T212444Z` (carpetas renombradas; los archivos internos conservan ese id).
> El runner mandó el kill switch como `DELETE /admin/faults` a través de nginx, a la misma API que la
> falla había saturado (pool 5/5 y hasta 43 peticiones en espera por réplica, delante de los 40 hilos
> de uvicorn). El DELETE esperó en esa fila y se aplicó a las 21:36:11, 82 s después de lo previsto:
> la fase de falla duró 382 s (no 300) y la falla ya había expirado sola a los 330 s (`duracion_s`),
> así que la "recuperación de 1 s" de abajo se midió desde una marca equivocada.
> Además k6 agotó sus 200 VUs y dejó de enviar 1733 peticiones (`dropped_iterations`, ~2,2/s), que este
> resumen no cuenta: el 51,9 % de errores es sobre lo enviado (11,6 req/s), no sobre los 20 req/s planificados.
> Hallazgo para el informe: el mecanismo de mitigación (kill switch por HTTP) depende del mismo recurso
> que la falla agota. Arreglo (commit 93911a5): kill switch escrito directo en `faults.yaml`, DELETE en
> segundo plano, 1000 VUs prealocados y carga no enviada en el resumen. La corrida válida es la siguiente `B1_*`.

# Resultado B1_20261016T212444Z

- Experimento: **B1** — Cada consulta retiene la conexión del pool +300 ms (pool max 5 por réplica)
- Configuración de la falla: `{"id": "B1", "familia": "base_de_datos", "tipo": "retencion_conexion", "target": "db.consulta", "ms_fijos": 300, "probabilidad": 1.0, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T21:24:48.994+00:00 · falla 2026-10-16T21:29:49.036+00:00 · kill switch 2026-10-16T21:36:11.397+00:00 · fin 2026-10-16T21:38:03.537+00:00
- Predicción: `evidencia/predictions/B1.md` sha256 `e0a184f9b6a1…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792185858994&to=1792186698537

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

| Fase | Peticiones | req/s | p50 POST ms | p95 POST ms | p99 POST ms | % errores | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6002 | 20.0 | 5.3 | 11.7 | 26.7 | 0.0 | 0.0 | 1.1 |
| falla | 4443 | 11.62 | 13741.4 | 16159.7 | 89042.8 | 51.924 | 56.577 | 75.5 |
| recuperación | 2222 | 20.01 | 5.2 | 12.7 | 37.6 | 0.0 | 0.0 | 4.2 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ❌ | ❌ |
| recuperacion | ✅ | ✅ | ✅ | ✅ |

**Recuperación tras el kill switch:** 1.0 s (cliente 1.0 s, lag 0.0 s) → ✅ SLO < 20 s

## Evidencia

- Inyecciones registradas: 10122 (`evidencia/logs/B1_20261016T212444Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 35 (`evidencia/traces/B1_20261016T212444Z/indice.csv`)
- Métricas: `evidencia/metrics/B1_20261016T212444Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/B1_20261016T212444Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
