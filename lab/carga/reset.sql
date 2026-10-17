-- Restaura el estado de partida del laboratorio antes de cada corrida (make lab-reset):
--   - borra las órdenes creadas por la API (rango 1.000.001+) y sus eventos de outbox,
--   - reinicia la secuencia de la API (mismos orden_id en cada corrida → la clave del
--     inyector para % de tráfico se repite),
--   - devuelve las franjas a su estado de datos/csv/franja_descargue.csv (la carga del
--     lab cuenta con ese cupo; make fase4 también las modifica),
--   - fase 4: borra los mensajes muertos de la API y los reintentos pendientes del outbox.
-- El runner copia el CSV a /tmp/franja_descargue.csv dentro del contenedor.
\set ON_ERROR_STOP on

BEGIN;
CREATE SEQUENCE IF NOT EXISTS ordenes.api_orden_seq START 1000001;
-- Esquema de las correcciones del worker (mismo DDL que app/db.py: DDL_CORRECCIONES).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'ordenes'
                 AND table_name = 'outbox_evento' AND column_name = 'intentos') THEN
    ALTER TABLE ordenes.outbox_evento ADD COLUMN intentos integer NOT NULL DEFAULT 0,
                                      ADD COLUMN proximo_intento timestamptz;
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS ordenes.outbox_muerto (
    outbox_id      bigint PRIMARY KEY,
    aggregate_id   bigint NOT NULL,
    tipo_evento    varchar(50) NOT NULL,
    payload        jsonb NOT NULL,
    intentos       integer NOT NULL,
    ultimo_error   text,
    fecha_creacion timestamptz NOT NULL,
    fecha_muerte   timestamptz NOT NULL DEFAULT now()
);
DELETE FROM ordenes.outbox_muerto WHERE aggregate_id >= 1000001;
DELETE FROM ordenes.outbox_evento WHERE aggregate_id >= 1000001;
UPDATE ordenes.outbox_evento SET intentos = 0, proximo_intento = NULL
 WHERE intentos <> 0 OR proximo_intento IS NOT NULL;
DELETE FROM ordenes.linea_orden   WHERE orden_id     >= 1000001;
-- Sin el índice idx_linea_orden_id (lo crea `make medir`, no `make datos`) la FK revisaría
-- 2M filas de linea_orden por cada orden borrada (~60 s). Las líneas ya se borraron arriba,
-- así que se omiten los triggers de FK solo en esta transacción.
SET LOCAL session_replication_role = replica;
DELETE FROM ordenes.orden_compra  WHERE orden_id     >= 1000001;
SET LOCAL session_replication_role = origin;
ALTER SEQUENCE ordenes.api_orden_seq RESTART WITH 1000001;

CREATE TEMP TABLE franja_csv (LIKE logistica.franja_descargue) ON COMMIT DROP;
COPY franja_csv FROM '/tmp/franja_descargue.csv' WITH (FORMAT csv, HEADER true);
UPDATE logistica.franja_descargue f
   SET reservas_actuales = c.reservas_actuales, estado = c.estado
  FROM franja_csv c
 WHERE f.franja_id = c.franja_id
   AND (f.reservas_actuales <> c.reservas_actuales OR f.estado <> c.estado);
COMMIT;

-- Sin bloat ni estadísticas viejas entre corridas.
VACUUM (ANALYZE) ordenes.outbox_evento, ordenes.outbox_muerto, ordenes.orden_compra, ordenes.linea_orden, logistica.franja_descargue;

SELECT (SELECT count(*) FROM ordenes.orden_compra WHERE orden_id >= 1000001) AS ordenes_api,
       (SELECT count(*) FROM ordenes.outbox_evento)                          AS outbox,
       (SELECT sum(reservas_actuales) FROM logistica.franja_descargue)        AS reservas_franjas;
