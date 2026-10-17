# Notas de sesión — laboratorio del Entregable 3

Estado al 2026-10-16. Para una sesión nueva: léelo antes de tocar el lab o correr experimentos.
La documentación completa está en `lab/README.md`, los requisitos en `ENTREGABLE3.md` y la
evidencia en `evidencia/README.md`.

## Estado actual

- **Fases 1–3 terminadas**:
  - Fase 1: API, outbox, ext-sap y nginx con 2 réplicas.
  - Fase 2: Prometheus, Grafana, Jaeger y logs JSON.
  - Fase 3: runner y los 8 experimentos.
- **Fase 4 implementada y corrida** (2026-10-16/17): 5 corridas corregidas válidas y O1 ×2. Ver "Fase 4" en `lab/README.md`:
  - correcciones en `lab/correcciones.yaml` (`catalogo` → A1, `bulkhead` → A2/B1/B2, `worker` → D2),
    en caliente, todas apagadas por defecto; `make experimento ID=<ID> CORRECCION=on` → `<ID>-corr_<UTC>`;
  - O1 (overhead de observabilidad): `make experimento ID=O1` con y sin `TRAZAS=off make lab-up`;
  - decisiones del equipo: pools 3 escritura + 2 lectura (total 5), A1 sin precio conocido → 503 rápido;
  - sin fichas de predicción para las correcciones ni O1 (decisión del equipo: el entregable las exige
    por falla); siguen obligatorias para las corridas sin corrección.
- **Predicciones**: las 8 de `evidencia/predictions/` están en `Estado: LISTA`, con commit
  `b07f00e` antes de correr. **No se modifican.**
- **Tablas "Predicción vs. resultado"** de cada `results/<RUN>/resumen.md`: vacías, las llena el equipo.
- **El lab queda levantado** con `kill_switch: true` en `lab/runtime/faults.yaml`, sin fallas
  activas. Postgres corre en compose (`postgres-escalables`, volumen `pgdata`).
- **Restos fuera de git** (no tocar sin preguntar):
  - archivos: `0001-…patch`, `Entregable3.pdf`, `lab-entregable3/`;
  - contenedor viejo: `postgres-escalables-viejo`, detenido. Se borra con `docker rm -v`
    solo si el usuario lo pide.

## Comandos clave

```bash
make datos && make lab-up        # clon limpio: datos E2 + lab completo (reiniciar el lab tras make datos)
make lab-smoke                   # verificación end-to-end
make test-lab                    # tests del inyector (usar el venv: PATH=venv/bin:$PATH)
make experimento ID=B1           # corrida real (~12 min): exige la predicción en LISTA
make experimento ID=B1 CORRECCION=on   # fase 4: misma falla con la corrección (sin ficha de predicción)
make experimento-prueba ID=A1    # corrida corta (30/30/25 s, prefijo PRUEBA-, ignorada por git)
make limpiar-pruebas             # borra las corridas PRUEBA-*
make lab-reset                   # restaura los datos de partida (lo hace el runner)
curl -X DELETE localhost:8080/admin/faults   # kill switch manual
TRAZAS=off make lab-up           # experimento de overhead sin OpenTelemetry
```

- Dashboard: http://localhost:3000/d/lab-entregable3 · Jaeger: http://localhost:16686 · Prometheus: :9090.
- Cada corrida real ocupa ~3–4 MB en `evidencia/`. Después de cada una se hace commit de sus 6
  carpetas: `baseline`, `experiments`, `logs`, `metrics`, `results`, `traces`.

## Decisiones tomadas

- **Carga**: 20 req/s, semilla 42, 30.000 operaciones (crear 70 %, listar 20 %, precio 10 %).
  Su configuración y la de los SLO están en `lab/slo.yaml`:
  - p95 POST ≤ 100 ms, p99 ≤ 250 ms;
  - errores < 1 % por ventana de 60 s;
  - lag del outbox < 10 s;
  - recuperación < 20 s.
- **Protocolo por experimento**: `lab-reset`, baseline 5 min, falla 5 min, kill switch,
  recuperación 2 min. C2 pausa 3 min (`duracion_s: 180`, como el catálogo), no toda la fase.
- **Fases**: las peticiones se asignan a una fase por su hora de **inicio**, y el baseline arranca
  con la primera petición real de k6, según `$msec` de nginx.
- **Decisión de inyección**: hash de (semilla, falla, clave de petición `X-Clave-Carga`). Las mismas
  peticiones quedan afectadas en cada corrida (`comparar_inyecciones.py`, margen de 0,5 s).
  Consecuencia: el reintento de una clave afectada falla siempre (ver D2).
- **El `UPDATE` de Q3** (reserva todas las franjas del día) **no se cambia**: es un hallazgo para B2.
- **`lab-reset`** desactiva los triggers de FK solo al borrar `orden_compra` (`session_replication_role`),
  porque `make datos` no crea `idx_linea_orden_id`.

## Problemas conocidos y sus arreglos

- **Reposo del Mac.** El Mac se durmió en plena falla en los intentos 1 y 2 de B1: 74 s y 56 s con
  batería, según `pmset -g log`. Docker, k6 y el runner se congelan, y las fases y latencias quedan
  contaminadas. Para evitarlo hay dos defensas:
  - **caffeinate**: `make experimento` corre el runner bajo `caffeinate -i` (macOS). Además, mejor
    tener el Mac en corriente durante las corridas.
  - **Detector de reposo** (`VigiaReposo` en `runner.py`): si el reloj de pared salta respecto del
    monotónico (en macOS `time.monotonic()` no avanza dormido) o el bucle de 1 s se congela, el runner:
    - aplica el kill switch,
    - detiene k6,
    - escribe `results/<RUN>/ABORTADA.md`,
    - y sale con código 3.

    Se probó congelando el runner 8 s con SIGSTOP. Si aborta, se repite una vez; si vuelve a abortar,
    hay que avisar al usuario.
- **OOM de Jaeger (costo de la observabilidad; usar en el informe).** Jaeger `all-in-one` guarda las
  trazas en memoria y venía **sin límite**. Tras 6,5 h encendido (fase 3 completa, smoke tests y A1-corr)
  ocupaba ~6,4 GB al empezar A1-corr y ~6,8 GB de los 7,75 GiB de la VM de Docker. La VM lo mató por OOM
  (`OOMKilled=true`, código 137) el 2026-10-17 a las 00:41:14 UTC, en plena falla de A2-corr: la corrida
  quedó inválida (`A2-corr-INVALIDA_20261017T003353Z`). Lecciones:
  - el backend de trazas crece con el tráfico y el tiempo, no con las fallas: sin retención, es en sí mismo
    un riesgo de disponibilidad que compite por memoria con el sistema observado;
  - la caída de Jaeger no detuvo el sistema (la API siguió atendiendo y k6 terminó la carga con código 0),
    pero sí se perdió la evidencia; no se midió si la presión de memoria previa afectó las latencias;
  - estimación: ~40 KB por traza en memoria; una corrida son ~15.000 trazas (~600 MB).
  - **Límite nuevo** (`compose.yaml`): `MEMORY_MAX_TRACES=20000` (cubre la corrida en curso; descarta las
    más viejas) y `mem_limit: 1536m`. La memoria de Jaeger por corrida queda en
    `metrics/<RUN>/prometheus/memoria_por_contenedor_bytes.csv` (`servicio=jaeger`).
- **Kill switch por archivo.** El runner no depende de la API, que en B1 está saturada: escribe
  `kill_switch: true` en `faults.yaml` **desde dentro de `fallas-ext`** con `docker compose exec`,
  bajo lock y con reemplazo atómico, y en paralelo manda el `DELETE /admin/faults`.
  - No se escribe desde el host: con Docker Desktop el `os.replace` del host no llega atómico al
    montaje, y una API leyó el archivo a medias (500).
  - La demora del `DELETE` queda en `logs/<RUN>/runner.jsonl`.
- **VUS_MAX.** k6 prealoca 1000 VUs (`carga.vus_max` en `slo.yaml`). Con 200 se agotaban, y con VUs
  creados durante la prueba k6 descartaba iteraciones mientras los inicializaba.
  - Las iteraciones no enviadas (`dropped_iterations`) quedan en `metrics/<RUN>/no_enviadas.csv.gz`.
  - El resumen da el % de errores sobre lo enviado y sobre lo planificado; el SLO de errores y la
    recuperación usan la carga planificada.
  - Aun con 1000 VUs, B1 deja 185 sin enviar: 20 req/s × 60 s de timeout son más de 1000
    concurrentes. Es comportamiento del sistema, no un error del runner.
- **Salida de k6.** k6 escribe directo a `logs/<RUN>/k6.log`, no a un pipe. Con un pipe sin leer, los
  más de 150 KB de avisos de B1 lo llenaron y k6 se bloqueó (corrida `B1_20261016T221301Z`).
- **Otros:**
  - cAdvisor corre en modo cgroup crudo, porque el snapshotter containerd de Docker Desktop no está
    soportado; el nombre del servicio sale del join con `contenedor_info`.
  - `fallas-ext` usa el socket de Docker para D1. Eso solo es aceptable en un lab local.
  - `make fase4` del E2 baja de throughput también sin el lab: no lo causa el lab.

## Corridas en `evidencia/`

| Corrida | Estado | Motivo |
| --- | --- | --- |
| `A1_20261016T205354Z` | ✅ válida | |
| `A2_20261016T211219Z` | ✅ válida | |
| `B1-intento1-INVALIDA_20261016T212444Z` | ❌ inválida | Reposo del host de 74 s en plena falla; el kill switch llegó 82 s tarde (~74 s de reposo y ~8 s del `DELETE` en la API saturada); 1733 peticiones no enviadas con 200 VUs |
| `B1-intento2-INVALIDA_20261016T214754Z` | ❌ inválida | Reposo del host de 56 s en plena falla; el kill switch llegó 54 s tarde; latencias de más de 60 s y 502 al despertar |
| `B1_20261016T221301Z` | ❌ abortada | Error del runner: el pipe de k6 se llenó y k6 se bloqueó (ver `ABORTADA.md`) |
| `B1_20261016T222927Z` | ✅ válida | |
| `B2_20261016T224212Z` | ✅ válida | |
| `C1_20261016T225444Z` | ✅ válida | |
| `C2_20261016T230717Z` | ✅ válida | |
| `D1_20261016T232015Z` | ✅ válida | Un intento anterior no llegó a arrancar por YAML inválido en la definición; no dejó evidencia |
| `D2_20261016T233309Z` | ✅ válida | Hay que leerla con el hallazgo de abajo |

Fase 4 (correcciones, `CORRECCION=on`):

| Corrida | Estado | Motivo |
| --- | --- | --- |
| `A1-corr_20261017T002059Z` | ✅ válida | |
| `A2-corr-INVALIDA_20261017T003353Z` | ❌ inválida | OOM de Jaeger (sin límite de memoria) a las 00:41:14, en plena falla; el runner no pudo leer las trazas y no escribió el resumen |
| `A2-corr_20261017T005544Z` | ✅ válida | Repetición con Jaeger limitado (20 000 trazas, 1536 MiB) |
| `B1-corr_20261017T010803Z` | ✅ válida | |
| `B2-corr_20261017T012023Z` | ✅ válida | |
| `D2-corr_20261017T013242Z` | ✅ válida | El breaker hacia ext-sap seguía abierto en el kill: el drenaje arranca unos 20 s tarde |
| `O1-trazas-on_20261017T014501Z` | ✅ válida | El primer punto del baseline arrastra el lag del backlog de D2-corr (104 s); a los 5 s ya está en 0.6 s |
| `O1-trazas-off_20261017T015738Z` | ✅ válida | `trazas_activas=0` en los 5 procesos durante toda la corrida |

Repeticiones (reproducibilidad, ventana reducida 2 + 3 + 1 min, `--etiqueta rep`; base como en las
corridas originales: sin índices de Q4/Q5 ni órdenes de la Fase 4):

| Corrida | Estado | Comparada con |
| --- | --- | --- |
| `A1-rep_20261017T040244Z` | ✅ válida | `A1_20261016T205354Z` |
| `B2-corr-rep_20261017T040853Z` | ✅ válida | `B2-corr_20261017T012023Z` |
| `D2-rep_20261017T041511Z` | ✅ válida | `D2_20261016T233309Z` |

Momento 1 y optimizaciones: `evidencia/momento1/`, `evidencia/linea_base/` y `evidencia/optimizaciones/README.md`.
Limitación: los experimentos de fallas corrieron sin los índices de Q4/Q5 (`make lab-reset` no los crea),
a diferencia del estado final del E2; no se repitieron por eso.

Las notas de invalidez están al inicio del `resumen.md` de cada corrida inválida. Una carpeta renombrada
conserva dentro el id original.

## Resultados principales y hallazgos

- **A1**: la predicción se cumplió entera. `GET /catalogo/precio` también se afecta, porque pasa por `validar_sku`.
- **A2**: también sube el p99 de las lecturas, porque esperan conexión del pool.
- **B1** (70 % de errores): las peticiones hacen dos filas, los 40 hilos de uvicorn y luego el pool
  (timeout de 5 s), hasta llegar al timeout de 60 s de k6. Con `max_fails=1`, nginx marca las dos
  réplicas como caídas y responde 502 sin llamar a la API: en los minutos 2 y 3 los errores llegan al
  89–100 %. El kill switch por HTTP depende del recurso que la falla satura (hallazgo menor).
- **B2**: cascada a todos los CEDI (27 % de errores en el CEDI 5 y 25 % en los demás), en diente de
  sierra de 60 s. Durante los últimos ~10 s de cada lock las peticiones ya no fallan: esperan un hilo
  de uvicorn, una espera sin timeout, y responden 201 al liberarse el lock.
- **C1**: el GIL topa api-1 en ~1 núcleo. api-1 sube a p50 270 ms y p95 493 ms; api-2 sigue igual.
- **C2**: falla silenciosa (lag de 178 s con la API intacta). Drena en ~95 s: el worker publica
  ~40 eventos/s mientras siguen entrando ~14/s.
- **D1**: 0 errores. nginx con `resolve` saca a api-2 cuando deja de resolver; el único POST que la
  alcanzó se reintentó en api-1 sin que el cliente lo notara. Reincorporación en 5,5 s.
- **D2, evento envenenado (*head-of-line blocking*)**:
  - Mecanismo:
    - el worker toma el outbox en orden (`ORDER BY outbox_id`);
    - si un evento falla, corta el lote y lo reintenta primero en el siguiente ciclo;
    - no hay estado de fallo permanente;
    - el inyector decide por clave, así que ese evento falla en cada reintento.
  - Efecto: un solo evento (`outbox_id` 113546) falló 119 veces seguidas y bloqueó todo el outbox
    durante ~4,5 min. Hubo 0 publicaciones desde t≈30 s, 4201 pendientes y un lag de 300 s.
  - Tras el kill switch drena a ~40/s y no termina en los 120 s de recuperación.
  - Es un hallazgo real del worker. Representa un SAP que rechaza siempre un mismo mensaje, no un
    503 transitorio en el que un reintento podría pasar.
  - La predicción ("40 % en fallo permanente, ~1,25 eventos/s") suponía otro modelo.
  - Relevante para la fase 4: retry con backoff, y sacar de la cabeza del outbox los eventos que
    fallan repetidamente (tope de intentos o cola de eventos fallidos).
