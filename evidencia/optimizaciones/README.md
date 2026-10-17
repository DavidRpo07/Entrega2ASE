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
