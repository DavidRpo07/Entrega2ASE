# Laboratorio de fallas — Entregable 3

`lab/fallas/inyector.py` implementa las fallas configurables:

| Condición | Cómo se cumple |
| --- | --- |
| Sin redespliegue | `lab/faults.yaml` se relee cada segundo; `activar()` para `POST /admin/faults` |
| Parametrizada | `probabilidad`, `porcentaje_trafico`, `duracion_s`, intensidad (`ms_fijos`, `mu`/`sigma`, `codigo_http`, `hilos`, `carga_cpu`) |
| Focalizable | `target` por punto de falla (`catalogo.validar_sku`, `catalogo.*`, `api-1`) |
| Reversible | `kill_switch()` / `kill_switch: true` en el archivo / `DELETE /admin/faults` |
| Reproducible | `semilla` por falla; % de tráfico determinista por clave de petición |

- `lab/fallas/catalogo.yaml`: las 8 fallas (A1–D2) con sus parámetros.
- `lab/faults.yaml`: fallas activas (vacío por defecto).
- Tests: `make test-lab` (ver "Entorno de Python" abajo).

## Puesta en marcha (clon limpio)

```bash
python3 -m venv venv && . venv/bin/activate      # una vez
pip install -r requirements.txt                  # psycopg2 + pyyaml (scripts del host)
make datos        # postgres (compose, volumen pgdata) + datos con semilla 42
make lab-up       # laboratorio completo
make lab-smoke    # verificación end-to-end
```

**Entorno de Python.** Los scripts del host (`make datos`, `make test-lab`, `make lab-smoke`,
generador de carga) usan `python3`. Active el venv antes de `make` (`. venv/bin/activate`) o
instale `requirements.txt` en el Python que use: sin `pyyaml`, `make test-lab` falla con
`ModuleNotFoundError: No module named 'yaml'`. La API, el worker y ext-sap no dependen del venv:
corren en la imagen Docker (`app/requirements.txt`).

**Después de `make datos` reinicie el laboratorio** (`make lab-down lab-up`): `make datos`
recrea los esquemas y borra la secuencia `ordenes.api_orden_seq` y el índice del outbox, que la
API crea al arrancar. Sin reinicio, `POST /ordenes` responde 500.

**Postgres viejo.** Si `postgres-escalables` se creó con `docker run` (antes del Entregable 3),
`make db-up` se detiene y explica cómo renombrarlo; luego `make datos` crea el de compose.

## Uso en el modulith

```python
from lab.fallas.inyector import INYECTOR, FallaInyectada

INYECTOR.punto("catalogo.validar_sku", clave=str(orden_id))  # latencia/errores
if INYECTOR.pausado("worker.outbox"): ...                    # consumidor (C2)
```

Variables de entorno: `FAULTS_FILE` (ruta del YAML) e `INSTANCIA` (`api-1`, `api-2`).
B2 (bloqueo en BD) y D1 (caída de instancia) son de tipo `externa`: las ejecuta el runner
de experimentos y el inyector solo las registra.

## Fase 1 — API, worker y ext-sap en Docker

```bash
make datos       # base cargada (Entregable 2)
make lab-up      # api-1, api-2 (nginx :8080), worker, ext-sap
make lab-smoke   # verificación end-to-end (balanceo, outbox, A1/B1/C1/C2/D2, kill switch)
make lab-down
```

| Servicio | Qué hace | Puntos de falla |
| --- | --- | --- |
| `api-1`, `api-2` | FastAPI sobre las clases de `datos/ejecutar_fase4_modulith.py`; pool `psycopg_pool` max 5 | `proveedores.validar_contrato`, `catalogo.validar_sku` (A1), `logistica.reservar_franja` (A2), `ordenes.crear`, `db.consulta` (B1), `api-1`/`api-2` (C1) |
| `worker` | Publica `ordenes.outbox_evento` → ext-sap; la orden pasa a `CONFIRMADA` | `worker.outbox` (C2) |
| `ext-sap` | Mock de SAP, `POST /notificar` (latencia base `SAP_LATENCIA_MS`) | `ext_sap.notificar` (D2) |
| `nginx` | Balancea las dos réplicas en `:8080`; tolera que api-2 esté detenida (D1) | — |

Endpoints: `POST /ordenes`, `GET /ordenes/{id}`, `GET /proveedores/{id}/ordenes` (Q5),
`GET /proveedores/{id}/otif` (Q4), `GET /catalogo/precio` (Q2), `GET /logistica/franjas`,
`GET /outbox/pendientes`, `GET /health`. Documentación interactiva en `/docs`.

Fallas en caliente (en cualquier réplica o en ext-sap; llegan a todos los procesos en ≤ 1 s
porque se escriben en el `lab/runtime/faults.yaml` compartido):

```bash
curl -X POST localhost:8080/admin/faults -H 'Content-Type: application/json' -d '{"id":"A1"}'           # del catálogo
curl -X POST localhost:8080/admin/faults -H 'Content-Type: application/json' -d '{"id":"A1","probabilidad":0.5}'
curl localhost:8080/admin/faults           # estado de la réplica que responde + archivo
curl -X DELETE localhost:8080/admin/faults # kill switch
```

Notas:
- Las órdenes de la API usan la secuencia `ordenes.api_orden_seq` (desde 1.000.001); la API la
  crea al arrancar junto con un índice parcial del outbox (por eso hay que reiniciar el lab tras
  `make datos`).
- `POST /admin/faults` guarda `inicio_utc` (hora absoluta de activación) en `faults.yaml`: un
  proceso que arranca después (p. ej. api-2 al volver en D1) aplica solo la duración restante, y
  nada si ya expiró. Las fallas expiradas se podan del archivo en la siguiente escritura.
- nginx escribe su access log en JSON (`status`, `upstream`, `upstream_status`,
  `upstream_response_time`, `instancia`, `trace_id`): evidencia de 502 cuando cae una réplica.
- Sin correcciones todavía: el worker no reintenta con backoff ni tiene circuit breaker (fase 4).

## Fase 2 — Observabilidad

`make lab-up` levanta también Prometheus, Grafana, Jaeger y postgres-exporter;
`make lab-smoke` verifica además targets, trazas, logs y el dashboard.

| Herramienta | URL | Qué hay |
| --- | --- | --- |
| Grafana | http://localhost:3000 | Dashboard *Laboratorio de fallas — Entregable 3* (home, sin login) |
| Prometheus | http://localhost:9090 | Scrape cada 5 s de api-1, api-2, worker, ext-sap y postgres-exporter |
| Jaeger | http://localhost:16686 | Trazas OTLP de `ordenes-api`, `outbox-worker`, `ext-sap` |

Métricas propias (etiqueta `instancia` puesta por Prometheus):

| Métrica | Uso |
| --- | --- |
| `http_peticion_duracion_segundos{metodo,ruta,codigo}` | p50/p95/p99, throughput y % 5xx por ruta y réplica |
| `db_pool_conexiones{estado}`, `db_pool_max`, `db_pool_esperando`, `db_pool_timeouts_total`, `db_pool_espera_segundos` | Pool de conexiones (B1) |
| `outbox_pendientes`, `outbox_lag_segundos`, `outbox_publicados_total`, `outbox_fallos_total{motivo}`, `worker_pausado` | Outbox y consumidor (C2, D2) |
| `ext_sap_llamada_duracion_segundos{resultado}` | Dependencia externa vista desde el worker |
| `falla_activa{falla_id,tipo,target}` (1/0), `fallas_inyectadas_total{falla_id}` | Qué falla está activa y cuántas veces se aplicó |
| `process_cpu_seconds_total` | CPU por proceso (C1) |
| `pg_locks_count`, `pg_stat_activity_count`, `pg_stat_database_*` | PostgreSQL (B2) |

Trazas: un span por módulo (`proveedores.validar_contrato`, `catalogo.validar_sku`, …), por
consulta (`db.consulta`) y por espera de conexión (`db.pool.adquirir`); cada inyección es un
evento `falla_inyectada` del span. El `traceparent` viaja en el payload del outbox, así que la
publicación del worker y la llamada a ext-sap quedan en la misma traza que el `POST /ordenes`.
Toda respuesta trae `X-Trace-Id`.

Logs: una línea JSON por evento con `ts`, `nivel`, `logger`, `instancia`, `msg`, `trace_id`,
`span_id` (y `ruta`, `codigo`, `duracion_ms` en el access log): `make lab-logs`.

## Carga reproducible

```bash
make lab-carga-datos SEMILLA=42 N=30000   # genera lab/carga/datos/carga_s42_n30000.json (+ .meta.json con sha256)
make lab-reset                            # borra órdenes de la API, reinicia la secuencia, restaura franjas
make lab-carga RATE=20 DURACION=2m ETIQUETA=baseline   # k6 → lab/carga/salida/baseline/resumen_k6.json
```

- `lab/carga/generar_carga.py` solo lee los CSV del Entregable 2 (no usa su generador): proveedores
  ACTIVOS con contrato VIGENTE en la fecha de creación, (CEDI, fecha) con franjas DISPONIBLES sin
  pasarse de su cupo, y fechas explícitas (independientes del día en que se corra). Mezcla por
  defecto: 70 % `POST /ordenes`, 20 % Q5, 10 % Q2.
- k6 recorre la secuencia en orden a tasa constante (`constant-arrival-rate`), así que misma
  semilla + `make lab-reset` → mismas peticiones y mismos `orden_id`.
- El cupo depende del estado inicial de las franjas: corra `make lab-reset` antes de cada corrida.
