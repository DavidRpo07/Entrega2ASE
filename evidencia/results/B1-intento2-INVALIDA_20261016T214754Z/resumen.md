> **B1 intento 2 — inválida: reposo del host.**
> Corrida original `B1_20261016T214754Z` (carpetas renombradas; los archivos internos conservan ese id).
> El Mac entró en reposo por inactividad (con batería) de 21:54:57 a 21:55:53 UTC, en plena fase de
> falla (`pmset -g log`): Docker, k6 y el runner quedaron congelados 56 s. El kill switch (ya escrito
> sin pasar por la API) se aplicó 54 s tarde (falla de 354 s), el monitor tiene un hueco de 65 s,
> hay latencias de 106–114 s (por encima del timeout de 60 s de k6) y 1092 respuestas 502 por
> conexiones reseteadas al despertar. Los números de abajo no son válidos.
> Arreglo: el runner corre bajo `caffeinate -i` y aborta si detecta una suspensión del host.
> La corrida válida es la siguiente `B1_*`.

# Resultado B1_20261016T214754Z

- Experimento: **B1** — Cada consulta retiene la conexión del pool +300 ms (pool max 5 por réplica)
- Configuración de la falla: `{"id": "B1", "familia": "base_de_datos", "tipo": "retencion_conexion", "target": "db.consulta", "ms_fijos": 300, "probabilidad": 1.0, "duracion_s": 330, "semilla": 42}`
- Fases: baseline 300 s · falla 300 s · recuperación 120 s · tasa 20 req/s
- Marcas (UTC): baseline 2026-10-16T21:47:58.118+00:00 · falla 2026-10-16T21:52:58.120+00:00 · kill switch 2026-10-16T21:58:52.715+00:00 · fin 2026-10-16T22:00:53.694+00:00
- Predicción: `evidencia/predictions/B1.md` sha256 `e0a184f9b6a1…`
- Grafana: http://localhost:3000/d/lab-entregable3?from=1792187248118&to=1792188068694

## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)

No enviadas = iteraciones que k6 no pudo lanzar por falta de VUs (`dropped_iterations`). % errores (enviadas) = 5xx o sin respuesta / enviadas; % errores (planificada) = (errores + no enviadas) / planificadas; la peor ventana de 60 s y el SLO usan la carga planificada.

| Fase | Planificadas | Enviadas | No enviadas | req/s enviadas | p50 POST ms | p95 POST ms | p99 POST ms | % errores (enviadas) | % errores (planificada) | peor ventana 60 s % | lag máx s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6001 | 6001 | 0 | 20.0 | 5.5 | 11.8 | 26.7 | 0.0 | 0.0 | 0.0 | 1.1 |
| falla | 6006 | 5815 | 191 | 16.4 | 26811.5 | 106582.9 | 114299.9 | 68.186 | 69.197 | 100.0 | 56.2 |
| recuperación | 2394 | 2394 | 0 | 20.01 | 5.3 | 13.5 | 73.8 | 0.0 | 0.0 | 0.0 | 10.2 |

## SLO

| Fase | p95 ≤ 100 ms | p99 ≤ 250 ms | errores < 1.0 % (60 s) | lag < 10 s |
| --- | --- | --- | --- | --- |
| baseline | ✅ | ✅ | ✅ | ✅ |
| falla | ❌ | ❌ | ❌ | ❌ |
| recuperacion | ✅ | ✅ | ✅ | ❌ |

**Recuperación tras el kill switch:** 20.4 s (cliente 1.0 s, lag 20.4 s) → ❌ SLO < 20 s

## Evidencia

- Inyecciones registradas: 9771 (`evidencia/logs/B1_20261016T214754Z/inyecciones.csv`, con la clave de cada petición)
- Trazas guardadas: 35 (`evidencia/traces/B1_20261016T214754Z/indice.csv`)
- Métricas: `evidencia/metrics/B1_20261016T214754Z/` (peticiones.csv.gz de k6 y series de Prometheus)
- Logs: `evidencia/logs/B1_20261016T214754Z/` (JSON por servicio con trace_id; nginx con upstream/status)

## Predicción vs. resultado (lo completa el equipo)

| Señal | Predicción | Resultado | Diferencia y por qué |
| --- | --- | --- | --- |
| | | | |
