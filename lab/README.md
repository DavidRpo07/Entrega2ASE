# Laboratorio de fallas — Entregable 3

`lab/fallas/inyector.py` implementa las fallas configurables:

| Condición | Cómo se cumple |
| --- | --- |
| Sin redespliegue | `lab/faults.yaml` se relee cada segundo; `activar()` para `POST /admin/faults` |
| Parametrizada | `probabilidad`, `porcentaje_trafico`, `duracion_s`, intensidad (`ms_fijos`, `mu`/`sigma`, `codigo_http`, `hilos`, `carga_cpu`) |
| Focalizable | `target` por punto de falla (`catalogo.validar_sku`, `catalogo.*`, `api-1`), `rutas` (`["POST /ordenes"]`), `instancias` (`["api-1"]`), `porcentaje_trafico` |
| Reversible | `kill_switch()` / `kill_switch: true` en el archivo / `DELETE /admin/faults`; cubre también B2 (libera el lock) y D1 (levanta api-2) vía `fallas-ext` |
| Reproducible | decisión por hash de (`semilla`, falla, clave de petición): la clave es `X-Clave-Carga` (índice de la carga, la envía k6), así que se afectan las mismas peticiones en cada corrida, sin importar orden de llegada ni réplica |

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
- Sin correcciones (por defecto) el worker no reintenta con backoff ni tiene circuit breaker: ver fase 4.

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

## Revisión contra ENTREGABLE3.md (antes de la fase 3)

- **Focalización**: además de `target`, cada falla acepta `rutas` (`"POST /ordenes"` o `"/catalogo/precio"`
  para cualquier método) e `instancias` (`["api-1"]`). La ruta la fija la API por petición
  (`RUTA_ACTUAL`); sin ruta (worker) una falla con `rutas` no aplica.
- **Reproducibilidad**: con clave, `probabilidad`, `porcentaje_trafico` y la demora lognormal se
  deciden por hash de (`semilla`, `id`, clave). k6 envía `X-Clave-Carga: c<i>`; la clave viaja en el
  outbox hasta ext-sap (D2 afecta las mismas órdenes). Sin clave se usa el generador por falla.
- **Fallas externas (B2, D1)**: las ejecuta el servicio `fallas-ext` (`app/fallas_externas.py`), que lee
  el mismo `faults.yaml` y reconcilia cada 250 ms; se activan con `POST /admin/faults` como las demás
  y el kill switch las revierte (B2: ROLLBACK del `SELECT … FOR UPDATE`; D1: `docker start`).
  Parámetros en `parametros:` (ver catálogo). Usa el socket de Docker (solo para este lab local).
- **D2**: `ms_fijos` es la latencia antes del 503 (2 s por defecto).
- **Recursos**: paneles de memoria residente y GC por proceso; CPU y memoria por contenedor con
  cAdvisor (incluido postgres). En Docker Desktop (snapshotter de containerd) cAdvisor no puede leer
  los metadatos de Docker, así que mide los cgroups en crudo y el nombre del servicio sale del join
  con `contenedor_info`, que publica `fallas-ext`.
- **Overhead de observabilidad**: `TRAZAS=off make lab-up` apaga OpenTelemetry (sin spans ni
  instrumentación); `make lab-up` lo vuelve a encender. La métrica `trazas_activas` deja constancia.
- **SLO** en `lab/slo.yaml` (tasa 20 req/s; p95 POST ≤ 100 ms, p99 ≤ 250 ms, errores < 1 % en
  ventanas de 60 s, lag < 10 s, recuperación < 20 s; fases 5 + 5 + 2 min). El dashboard toma de ahí
  sus umbrales: `python3 infra/grafana/generar_dashboard.py` (venv activo).
- **Hallazgo para B2** (no se corrige): el `UPDATE` de Q3 del Entregable 2 incrementa todas las franjas
  disponibles del día, ~32 filas por orden; cada `POST /ordenes` bloquea esas filas.

## Fase 3 — Experimentos

```bash
# 1. El equipo escribe la predicción y la commitea (Estado: LISTA):  evidencia/predictions/A1.md
# 2. Corrida (≈ 12 min: baseline 5 + falla 5 + recuperación 2, a 20 req/s):
make experimento ID=A1
# Ensayo corto del runner (30 + 30 + 25 s, prefijo PRUEBA-, ignorado por git):
make experimento-prueba ID=A1      # make limpiar-pruebas para borrarlos
```

- Definiciones (configuración sobre el catálogo): `lab/experimentos/definiciones/<ID>.yaml`.
  Protocolo, tasa y SLO: `lab/slo.yaml`. Evidencia: `evidencia/` (ver `evidencia/README.md`).
- El runner (`lab/experimentos/runner.py`): kill switch → `make lab-reset` → k6 a tasa constante →
  baseline (desde la primera petición real, según nginx) → `POST /admin/faults` → falla →
  kill switch → recuperación → recolecta k6, Prometheus, logs, trazas y escribe
  `results/<RUN>/resumen.md` (por fase, SLO, tiempo de recuperación). Las fases se asignan por la
  hora de inicio de cada petición. La falla lleva `duracion_s` = fase + 30 s: si el runner muere,
  expira sola (y Ctrl+C dispara el kill switch).
- El kill switch del runner escribe `kill_switch: true` en `faults.yaml` desde dentro de
  `fallas-ext` (`docker compose exec`) y, en paralelo, manda `DELETE /admin/faults`. No depende de
  la API, que en B1 está saturada (pool 5/5 y decenas de peticiones en fila). Se escribe
  desde un contenedor porque con Docker Desktop el `os.replace` hecho en el host no llega atómico al
  montaje (una API leyó el archivo a medias). La demora del DELETE queda en `logs/<RUN>/runner.jsonl`.
- k6 prealoca `vus_max` VUs (`lab/slo.yaml`, 1000): con la API a 15 s por petición, 200 VUs se
  agotaron y k6 dejó de enviar carga. Las iteraciones no enviadas (`dropped_iterations`) quedan en
  `metrics/<RUN>/no_enviadas.csv.gz` y en el resumen; el % de errores se da sobre lo enviado y
  sobre la carga planificada, y el SLO de errores y la recuperación usan la planificada.
- Reposo del host: `make experimento` corre el runner bajo `caffeinate -i` (macOS) y el runner aborta
  (código 3, `results/<RUN>/ABORTADA.md`, kill switch aplicado) si el reloj de pared salta respecto del
  monotónico o el proceso estuvo congelado: en B1 el Mac se durmió en plena falla dos veces.
- Se niega a correr si la predicción falta o sigue en PENDIENTE; guarda su sha256 y el commit.
- B2 y D1 se activan igual que las demás (los ejecuta `fallas-ext`).
- Reproducibilidad: `python3 lab/experimentos/comparar_inyecciones.py <RUN1> <RUN2>` compara qué
  claves afectó la falla en dos corridas (excluye 0,5 s tras activación y kill switch, la ventana
  en que cada proceso relee `faults.yaml`; `FAULTS_RECARGA_S=0.25`).
- Overhead de observabilidad: `TRAZAS=off make lab-up` y luego `make experimento …` (el manifest y
  la métrica `trazas_activas` registran el estado); `make lab-up` lo restaura.

## Fase 4 — Correcciones y re-experimentación

Cada corrección se enciende y apaga **en caliente** con `lab/runtime/correcciones.yaml` (plantilla:
`lab/correcciones.yaml`, todo apagado; `make lab-up` la copia si falta). API, worker y fallas-ext lo
releen cada 0,25 s (`lab/resiliencia/config.py`). Apagadas, el código hace lo mismo que en la fase 3.

```bash
make experimento ID=A1                    # antes: correcciones apagadas → A1_<UTC>
make experimento ID=A1 CORRECCION=on      # después: misma falla, misma semilla → A1-corr_<UTC>
curl -X PUT localhost:8080/admin/correcciones -H 'Content-Type: application/json' -d '{"activas":["catalogo"]}'
curl localhost:8080/admin/correcciones    # estado de la réplica (config y breakers)
curl -X PUT localhost:8080/admin/correcciones -H 'Content-Type: application/json' -d '{"activas":[]}'
```

| Corrección | Experimentos | Qué hace | Señales |
| --- | --- | --- | --- |
| `catalogo` | A1 | Timeout de 200 ms sobre `catalogo.validar_sku`; circuit breaker por réplica (abre tras 5 fallos seguidos, semiabierto a los 30 s con una sola llamada de prueba); fallback al último precio conocido de (proveedor, sku) en la réplica; sin precio → 503 inmediato | `circuit_breaker_estado{nombre="catalogo"}` (0/1/2), `circuit_breaker_transiciones_total`, `circuit_breaker_rechazos_total`, `catalogo_timeouts_total`, `catalogo_fallback_total{motivo,resultado}` |
| `bulkhead` | A2, B1, B2 | Pools separados por réplica: `escritura` 3 (POST /ordenes) y `lectura` 2 (todos los GET), mismo total de 5; espera por conexión de 500 ms (fail-fast → 503); `lock_timeout` de 1 s en la transacción de POST /ordenes (reserva de franjas) → 503 | `db_pool_*{pool}`, `db_pool_timeouts_total{pool}`, `db_lock_timeouts_total` |
| `worker` | D2 | Un evento que falla se reprograma (`proximo_intento`) con backoff 100 · 2^(n-1) ms + hasta 50 % de jitter determinista por `outbox_id`, y el lote **sigue** con los demás (sin *head-of-line blocking*); al 3.er fallo pasa a `ordenes.outbox_muerto`; breaker hacia ext-sap (5 fallos / 30 s): abierto, corta el lote sin gastar intentos | `outbox_reintentos_total`, `outbox_muertos_total`, `outbox_mensajes_muertos`, `outbox_breaker_diferidos_total`, `circuit_breaker_estado{nombre="ext_sap"}` |

- **Runner** (`--correccion on|off`, `CORRECCION=on` en make): enciende solo las correcciones de
  `experimentos.<ID>` en `lab/correcciones.yaml`, antes del `lab-reset` (el baseline ya corre corregido y
  mide su costo); escribe el archivo desde `fallas-ext` (como el kill switch) con `corrida: <RUN>`, lo que
  reinicia breakers y caché de precios en cada corrida; espera a ver `correccion_activa` en api-1, api-2 y
  worker; y al terminar (también si aborta) las apaga. No exige ficha de predicción (decisión del
  equipo: el entregable la pide por falla; sigue siendo obligatoria sin corrección). Manifest y resumen
  registran la configuración aplicada. `caffeinate` y el detector de
  reposo funcionan igual.
- **Timeout de Catálogo, cómo funciona**: la latencia de A1 la inyecta un `sleep` en el mismo hilo y con
  el cursor de la transacción, así que el timeout es un *deadline* cooperativo (`INYECTOR.plazo(ms)`): una
  latencia inyectada que no cabe en el plazo duerme solo hasta el plazo y lanza `PlazoAgotado`. Equivale
  a un cliente que deja de esperar a una dependencia remota. No corta una consulta SQL ya lanzada.
- **Caché de precios**: por réplica y en memoria; ignora la fecha (es el "último conocido"). Se llena
  solo con la corrección encendida; POST /ordenes siempre consulta el SKU 101.
- **Esquema**: `intentos`, `proximo_intento` en `ordenes.outbox_evento` y la tabla `ordenes.outbox_muerto`
  los crean la API y el worker al arrancar y `make lab-reset` (idempotente, sin `ALTER` si ya existen).
  `lab-reset` borra los muertos de la API y los reintentos pendientes.
- **Límites conocidos**: el bulkhead separa conexiones, no los 40 hilos de uvicorn (en B1 la fila de
  hilos sigue existiendo); `SAP_TIMEOUT_S` sigue en 30 s; los pools `lectura`/`escritura` se crean al
  encender la corrección y no se cierran al apagarla (quedan ociosos, `pool=general` vuelve a atender todo).

### O1 — Overhead de observabilidad

Misma carga sin falla (`definiciones/O1.yaml`, `falla: null`), con y sin trazas:

```bash
make lab-up            && make experimento ID=O1   # → O1-trazas-on_<UTC>
TRAZAS=off make lab-up && make experimento ID=O1   # → O1-trazas-off_<UTC>
make lab-up                                        # restaura las trazas
```

El runner toma el estado de `trazas_activas` (debe ser igual en todos los procesos) y lo pone en el nombre
de la corrida. No exige ficha de predicción.
