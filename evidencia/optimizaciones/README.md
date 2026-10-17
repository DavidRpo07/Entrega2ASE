# Optimizaciones del E3 sobre las cargas del E2

Objetivo (rúbrica): cada métrica de tiempo del E2 ≤ 0,90 × valor del informe del E2, con la misma
consulta, escenario, métrica y carga. Un commit por optimización; tras cada una se mide solo lo
afectado (Fase 4 para a, b, c; Q4/Q5 para d). La tabla final sale de `make linea-base`.

## Protocolo de medición por paso

`lab/momento1/linea_base.py fase4 --repeticiones 3`: 3 corridas de las mismas 5.000 órdenes
(`datos/csv/ordenes_fase4_5k.csv`), cada una desde el mismo estado (sin órdenes de la Fase 4, franjas
como en el CSV, `VACUUM ANALYZE`), lab apagado. Se reporta la mediana. Métrica del E2: órdenes exitosas
/ duración (req/s); las exitosas deben seguir siendo 1.523 (misma carga, mismo resultado de negocio).

| Paso | Carpeta | Mediana req/s | Corridas | Exitosas |
| --- | --- | --- | --- | --- |
| 0. Código del E2 | `0_original/` | 400,25 | 362,88 · 404,58 · 400,25 | 1.523 |
| a. Validar el estado antes de los módulos | `a_validar_estado/` | 960,48 | 941,20 · 960,48 · 964,38 | 1.523 |
| b. (+a) UPDATE de Q3 a una sola franja, SKIP LOCKED | `b_una_franja/` | 958,47 | 996,97 · 958,47 · 887,43 | 1.523 |
| c. (+a+b) Sentencias preparadas | `c_preparadas/` | 1.036,97 | 1.063,41 · 931,44 · 1.036,97 | 1.523 |

Nota: con este protocolo el código del E2 da ~400 req/s, frente a 296,42 req/s de la línea base
(`make linea-base`), que mide justo después de recargar la base: allí los datos recién copiados
todavía no tienen hint bits ni mapa de visibilidad y autovacuum está trabajando. Por eso la tabla
final se mide con el mismo `make linea-base` que la línea base (comparación justa), y el aporte de
cada optimización se lee en esta tabla (mismo protocolo entre pasos).

## a. Validar el estado de la orden antes de llamar a los módulos (corrección de comportamiento)

- **Antes (E2):** `OrdenesService.crear_orden_transaccional` ejecutaba Q1 (contrato), Q2 (precio) y
  el UPDATE de franjas de Q3, y recién en el `INSERT` de la cabecera PostgreSQL rechazaba la orden por
  el `CHECK chk_orden_estadoor` (estado `RECIBIDA` o `ENTREGADA`, que la tabla no admite). La
  transacción hacía `ROLLBACK`. Fueron 2.988 de las 5.000 órdenes (60 %): tres consultas, un UPDATE
  de varias franjas y un rollback por orden que de antemano no podía guardarse. El informe del E2
  atribuía los rechazos a contratos no vigentes y franjas completas; solo 489 eran de contrato.
- **Ahora:** el módulo Órdenes valida el estado contra el mismo conjunto del `CHECK` antes de llamar a
  Proveedores, Catálogo y Logística, y rechaza con `ValueError` (fail-fast, sin tocar la base). El
  `CHECK` sigue en la tabla como defensa en profundidad.
- **Por qué es una corrección:** es la validación fail-fast que el diseño del E2 declara («el sistema
  abortó la operación inmediatamente… sin incurrir en I/O innecesario»), y que no ocurría: una orden
  inválida no debe bloquear franjas ni consumir trabajo de otros módulos. El resultado de negocio no
  cambia: las mismas 1.523 órdenes exitosas y 3.477 rechazadas (ahora 3.323 por estado inválido y 154
  por contrato, porque el estado se revisa primero).
- **Alcance:** `OrdenesService(..., validar_estado_primero=True)`. La API del lab (`app/servicios.py`)
  lo deja en `False` para que las repeticiones de los experimentos de fallas sean comparables con las
  corridas originales.

## b. UPDATE de Q3 a una sola franja con SKIP LOCKED (corrección de comportamiento)

- **Antes (E2):** `LogisticaService.reservar_franja` ejecutaba
  `UPDATE … SET reservas_actuales = reservas_actuales + 1 … WHERE cedi_id = … AND fecha = … AND
  estado = 'DISPONIBLE' AND reservas_actuales < capacidad`: sumaba una reserva en **todas** las franjas
  disponibles de ese CEDI y día (5,4 filas por orden en promedio con la base recién cargada) y las
  bloqueaba todas hasta el commit. Medido en la corrida `0_original/fase4_r1`: las 1.523 órdenes
  exitosas consumieron **8.272** cupos y dejaron **1.534** franjas COMPLETAS.
- **Ahora:** la subconsulta elige la primera franja del día con cupo (`ORDER BY hora_inicio LIMIT 1`)
  con `FOR UPDATE SKIP LOCKED` y el UPDATE toca solo esa fila. En `b_una_franja/fase4_r1`: 1.523
  órdenes → **1.523** cupos, 278 franjas COMPLETAS; `desglose/` muestra 1 fila por UPDATE.
- **Por qué es una corrección:** una orden reserva un cupo de descargue, no uno en cada franja del
  día; el E2 agotaba la capacidad logística ~5 veces más rápido de lo real y retenía locks sobre
  todas las franjas del día, lo que serializa órdenes concurrentes del mismo CEDI. Con SKIP LOCKED
  una orden concurrente toma la siguiente franja libre en vez de esperar.
- **Sin cambio en el resultado de negocio:** igual que en el E2, Q3 no rechaza la orden si no hay
  franja con cupo (el UPDATE afecta 0 filas). Se mantuvo para no cambiar la carga ni las 1.523
  exitosas; queda anotado como pendiente de diseño.
- **Aporte medido:** dentro del ruido (960 → 958 req/s): tras la optimización a, Q3 solo corre para
  1.677 órdenes y, en una sola conexión, el costo de tocar ~5 filas en vez de 1 es pequeño. El
  beneficio está en la corrección y en la concurrencia (menos locks), que esta carga secuencial
  del E2 no ejercita.
- **Alcance:** `LogisticaService(cursor, una_franja=True)`; la API del lab usa `una_franja=False`
  (B2 bloquea franjas con `FOR UPDATE`: con SKIP LOCKED el experimento sería otro).

## c. Sentencias preparadas

- **Antes:** cada orden enviaba el texto completo de Q1, Q2, Q3 y los dos INSERT; PostgreSQL los
  analizaba y planificaba en cada ejecución.
- **Ahora:** `preparar_sentencia` hace `PREPARE` una vez por conexión y la ruta usa `EXECUTE`
  (`datos/ejecutar_fase4_modulith.py`, `preparar=True` en los cuatro servicios). Mismo SQL, mismos
  resultados; la API del lab usa `preparar=False` (psycopg 3 con pool: el PREPARE por conexión es otro
  diseño).
- **Aporte medido:** 958,47 → 1.036,97 req/s (+8 %), con la dispersión habitual entre corridas
  (931–1.063).

## d. Índices cubrientes (INCLUDE) + VACUUM para Q4 y Q5

- **Antes (E2):** `idx_orden_proveedor_confirmada (proveedor_id, fecha_creacion) WHERE estado =
  'CONFIRMADA'`, `idx_linea_orden_id (orden_id)` e `idx_orden_proveedor_fecha (proveedor_id,
  fecha_creacion DESC)`, seguidos de `ANALYZE`: los planes visitan el heap por cada fila.
- **Ahora** (`datos/crear_indice_q4.py`, `datos/crear_indice_q5.py`; mismos nombres, se recrean):
  `INCLUDE (fecha_recepcion, fecha_entrega_solicitada)` en el de órdenes confirmadas, `INCLUDE
  (categoria, cantidad_solicitada, cantidad_recibida)` en el de líneas e `INCLUDE (orden_id, cedi_id,
  estado, total)` en el de paginación, seguidos de `VACUUM (ANALYZE)` para el mapa de visibilidad.
- **Planes** (`medir_despues_d.log`): Q5 pasa a `Index Only Scan … Heap Fetches: 0` (0,006–0,04 ms en
  el servidor); en Q4 el join con `linea_orden` es `Index Only Scan` (Heap Fetches: 3) y el acceso a
  `orden_compra` sigue siendo Bitmap Heap Scan (elección del planificador).
- **Medición:** `linea_base.py medir --consultas q4 q5 --repeticiones 3`, mediana por percentil
  (método inclusive, como el informe), sobre la misma base antes y después del cambio.

| Consulta | Escenario | Métrica | E2 | Objetivo | Antes de d | Después de d | Cumple |
|---|---|---|---|---|---|---|---|
| Q4 | frio | p50 | 0.358 | 0.322 | 0.354 | 0.341 | no |
| Q4 | frio | p95 | 0.419 | 0.377 | 0.398 | 0.384 | no |
| Q4 | frio | p99 | 0.435 | 0.392 | 0.41 | 0.397 | no |
| Q4 | caliente | p50 | 2.839 | 2.555 | 2.929 | 2.249 | sí |
| Q4 | caliente | p95 | 9.334 | 8.401 | 9.356 | 7.977 | sí |
| Q4 | caliente | p99 | 14.481 | 13.033 | 12.699 | 9.534 | sí |
| Q5 | frio | p50 | 0.156 | 0.14 | 0.155 | 0.14 | sí |
| Q5 | frio | p95 | 0.181 | 0.163 | 0.186 | 0.181 | no |
| Q5 | frio | p99 | 0.191 | 0.172 | 0.204 | 0.184 | no |
| Q5 | caliente | p50 | 0.25 | 0.225 | 0.274 | 0.223 | sí |
| Q5 | caliente | p95 | 0.327 | 0.294 | 0.329 | 0.321 | no |
| Q5 | caliente | p99 | 0.374 | 0.337 | 0.36 | 0.456 | no |

- **Lectura:** Q4 caliente (la consulta pesada) cumple los tres objetivos; Q4 frío y Q5 mejoran pero
  quedan cerca del objetivo sin alcanzarlo en varias métricas. En Q5 el servidor resuelve en
  < 0,04 ms y el cliente mide 0,14–0,22 ms: el resto es el viaje de ida y vuelta de psycopg2 por la
  red de Docker Desktop, que ningún índice reduce.

## e. Q1–Q3: mediana de 3 corridas

Q1–Q3 no cambian de SQL ni de índices. `make linea-base MEDIANA_Q1_Q3=on` las mide 3 veces más (100
ejecuciones por escenario cada vez) y la tabla usa la mediana de cada percentil
(`linea_base/<UTC>/medir_mediana.json`); la línea base E3 es de 1 corrida.

## Tabla final

`evidencia/linea_base/20261017T035415Z/tabla_final.md` (E2 / línea base E3 / final E3 / objetivo /
¿cumple? / mejora vs. línea base E3). Resumen:

- **Fase 4:** 413,69 (E2) → 296,42 (línea base E3) → **1.036,37 req/s** (final); objetivo ≥ 459,66: cumple.
- **Q1–Q3:** los 18 valores cumplen 0,90 × E2.
- **Q4 con índice:** caliente p95 y p99 cumplen; caliente p50 (2,721 vs. 2,555) y frío p50/p95/p99 no.
- **Q5 con índice:** ninguno cumple en la corrida final (p. ej. frío p50 0,154 vs. 0,140).

**Lectura de la mejora vs. la línea base E3.** Q1–Q3 y Q4/Q5 «antes_indice» no cambiaron entre las
dos corridas (mismo SQL, mismos índices) y aun así mejoraron entre 9 y 67 %: es variación del entorno
entre corridas (Docker Desktop en el mismo Mac), no efecto de las optimizaciones. Esas filas sirven de
control: el aporte atribuible a cada optimización es el de la tabla por pasos de arriba (mismo protocolo,
mediana de 3). Q1–Q3 cumplen el objetivo, pero ese cumplimiento depende del entorno, no de un cambio.

## Decisiones tomadas

1. La API del lab (`app/servicios.py`) conserva el comportamiento del E2 (sin a, b ni c) para que las
   repeticiones de los experimentos de fallas sean comparables con las corridas originales.
2. b no rechaza la orden si no hay franja con cupo (como el E2), para no cambiar la carga ni las 1.523
   exitosas.
3. La tabla final se mide con el mismo `make linea-base` que la línea base (base recién cargada); el
   aporte por paso, con el protocolo de estado preparado y mediana de 3 (ver «Protocolo»).
4. Q4/Q5 «antes_indice»: solo referencia, sin objetivo.
5. Antes de las repeticiones del lab, la base se dejó como en las corridas originales (sin órdenes de la
   Fase 4 ni índices de Q4/Q5); después se recrearon los índices finales (`crear_indice_q4/q5.py`).
