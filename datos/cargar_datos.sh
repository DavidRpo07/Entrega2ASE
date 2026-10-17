#!/usr/bin/env bash
set -e

DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-escalables}"
CONTAINER_NAME="postgres-escalables"
CSV_DIR="datos/csv"
RESULTADOS_DIR="${RESULTADOS_DIR:-datos/resultados}"   # make linea-base lo redirige a evidencia/linea_base/
REPORTE_CARGA="$RESULTADOS_DIR/carga.csv"

PSQL_CMD="docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME"

mkdir -p "$RESULTADOS_DIR"
printf 'tipo,tabla,archivo,filas,tamano_bytes,duracion_ms\n' > "$REPORTE_CARGA"

echo "================================================================="
echo "EJECUTANDO FASE 0 Y FASE 2: CARGA MASIVA Y ANALYZE"
echo "================================================================="
TIEMPO_INICIO_TOTAL=$(date +%s%N)

# -----------------------------------------------------------------
# FASE 0: ESQUEMA LIMPIO
# -----------------------------------------------------------------
echo ""
echo "--- FASE 0: RECREANDO MODELO FÍSICO (ESQUEMA LIMPIO) ---"
# El SQL se redirige desde el host hacia psql dentro del contenedor.
$PSQL_CMD < modelo-fisico.sql > /dev/null
echo "✓ Esquemas limpios creados desde modelo-fisico.sql."

# -----------------------------------------------------------------
# FASE 2: CARGA MASIVA CON COPY
# -----------------------------------------------------------------
echo ""
echo "--- FASE 2: CARGA MASIVA CON COPY Y REPORTE DE TIEMPOS ---"

ejecutar_copy() {
    local tabla=$1
    local archivo=$2
    local inicio=$(date +%s%N)

    if [ ! -f "$archivo" ]; then
        echo "❌ Error: $archivo no existe."
        exit 1
    fi

    local tamano=$(du -h "$archivo" | cut -f1)
    local tamano_bytes=$(stat -f %z "$archivo")
    local filas=$(( $(wc -l < "$archivo") - 1 ))
    echo -n "Cargando $tabla ($tamano)... "

    cat "$archivo" | $PSQL_CMD -c "\copy $tabla FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" > /dev/null

    local fin=$(date +%s%N)
    local duracion_ms=$(( (fin - inicio) / 1000000 ))
    echo "Done (${duracion_ms} ms)"
    printf 'COPY,%s,%s,%s,%s,%s\n' "$tabla" "$archivo" "$filas" "$tamano_bytes" "$duracion_ms" >> "$REPORTE_CARGA"
}

ejecutar_copy "proveedores.proveedor" "$CSV_DIR/proveedor.csv"
ejecutar_copy "proveedores.contrato_suministro" "$CSV_DIR/contrato_suministro.csv"
ejecutar_copy "catalogo.sku" "$CSV_DIR/sku.csv"
ejecutar_copy "catalogo.catalogo_negociado" "$CSV_DIR/catalogo_negociado.csv"
ejecutar_copy "logistica.cedi" "$CSV_DIR/cedi.csv"
ejecutar_copy "logistica.franja_descargue" "$CSV_DIR/franja_descargue.csv"
ejecutar_copy "ordenes.orden_compra" "$CSV_DIR/orden_compra.csv"
ejecutar_copy "ordenes.linea_orden" "$CSV_DIR/linea_orden.csv"
ejecutar_copy "auditoria.evento_auditoria" "$CSV_DIR/evento_auditoria.csv"

# -----------------------------------------------------------------
# SINCRONIZACIÓN DE SECUENCIAS IDENTITY (setval)
# -----------------------------------------------------------------
echo ""
echo "--- REAJUSTANDO SECUENCIAS IDENTITY (setval) ---"
$PSQL_CMD -c "
SELECT setval(pg_get_serial_sequence('proveedores.proveedor', 'proveedor_id'), COALESCE(MAX(proveedor_id), 1)) FROM proveedores.proveedor;
SELECT setval(pg_get_serial_sequence('proveedores.contrato_suministro', 'contrato_id'), COALESCE(MAX(contrato_id), 1)) FROM proveedores.contrato_suministro;
SELECT setval(pg_get_serial_sequence('catalogo.sku', 'sku_id'), COALESCE(MAX(sku_id), 1)) FROM catalogo.sku;
SELECT setval(pg_get_serial_sequence('catalogo.catalogo_negociado', 'catalogo_id'), COALESCE(MAX(catalogo_id), 1)) FROM catalogo.catalogo_negociado;
SELECT setval(pg_get_serial_sequence('logistica.cedi', 'cedi_id'), COALESCE(MAX(cedi_id), 1)) FROM logistica.cedi;
SELECT setval(pg_get_serial_sequence('logistica.franja_descargue', 'franja_id'), COALESCE(MAX(franja_id), 1)) FROM logistica.franja_descargue;
SELECT setval(pg_get_serial_sequence('ordenes.orden_compra', 'orden_id'), COALESCE(MAX(orden_id), 1)) FROM ordenes.orden_compra;
SELECT setval(pg_get_serial_sequence('ordenes.linea_orden', 'linea_orden_id'), COALESCE(MAX(linea_orden_id), 1)) FROM ordenes.linea_orden;
SELECT setval(pg_get_serial_sequence('auditoria.evento_auditoria', 'evento_id'), COALESCE(MAX(evento_id), 1)) FROM auditoria.evento_auditoria;
" > /dev/null
echo "✓ Secuencias ajustadas correctamente."

# -----------------------------------------------------------------
# CREACIÓN POSTERIOR DE ÍNDICES SECUNDARIOS
# (Q4 y Q5 se mantienen comentados para medir el baseline)
# -----------------------------------------------------------------
echo ""
echo "--- CREANDO ÍNDICES SECUNDARIOS BASE (SIN Q4 Y Q5) ---"
INICIO_INDICES=$(date +%s%N)

$PSQL_CMD -c "
CREATE INDEX idx_contrato_proveedor_vigencia ON proveedores.contrato_suministro (proveedor_id, fecha_inicio, fecha_fin) WHERE estado = 'VIGENTE';
CREATE INDEX idx_catalogo_proveedor_sku_vigencia ON catalogo.catalogo_negociado (proveedor_id, sku_id, fecha_inicio, fecha_fin) WHERE estado = 'ACTIVO';
CREATE INDEX idx_franja_cedi_fecha_estado ON logistica.franja_descargue (cedi_id, fecha, estado) WHERE estado = 'DISPONIBLE';
CREATE INDEX idx_outbox_pendientes ON ordenes.outbox_evento (fecha_creacion) WHERE publicado = FALSE;
CREATE UNIQUE INDEX uq_reserva_franja_activa ON logistica.reserva_franja (franja_id, orden_id) WHERE estado IN ('CONFIRMADA', 'PENDIENTE');

-- ÍNDICES RESERVADOS PARA FASE DE MEDICIÓN (BENCHMARK Q4 Y Q5):
-- CREATE INDEX idx_orden_proveedor_fecha ON ordenes.orden_compra (proveedor_id, fecha_creacion DESC, orden_id DESC);
-- CREATE INDEX idx_linea_orden_id ON ordenes.linea_orden (orden_id);
" > /dev/null

FIN_INDICES=$(date +%s%N)
DURACION_INDICES=$(( (FIN_INDICES - INICIO_INDICES) / 1000000 ))
echo "✓ Índices base creados (${DURACION_INDICES} ms)."

# -----------------------------------------------------------------
# ACTUALIZACIÓN DEL PLANEADOR DE CONSULTAS (ANALYZE)
# -----------------------------------------------------------------
echo ""
echo "--- EJECUTANDO ANALYZE EN TODOS LOS ESQUEMAS ---"
INICIO_ANALYZE=$(date +%s%N)
$PSQL_CMD -c "ANALYZE VERBOSE proveedores.proveedor, proveedores.contrato_suministro, catalogo.sku, catalogo.catalogo_negociado, logistica.cedi, logistica.franja_descargue, ordenes.orden_compra, ordenes.linea_orden, auditoria.evento_auditoria;" > /dev/null
FIN_ANALYZE=$(date +%s%N)
DURACION_ANALYZE=$(( (FIN_ANALYZE - INICIO_ANALYZE) / 1000000 ))
echo "✓ ANALYZE ejecutado exitosamente (${DURACION_ANALYZE} ms)."

TIEMPO_FIN_TOTAL=$(date +%s%N)
TOTAL_MS=$(( (TIEMPO_FIN_TOTAL - TIEMPO_INICIO_TOTAL) / 1000000 ))

echo ""
echo "================================================================="
echo "FASE 0 Y FASE 2 COMPLETADAS EXITOSAMENTE EN ${TOTAL_MS} ms"
echo "================================================================="
printf 'TOTAL,carga_completa,,,,%s\n' "$TOTAL_MS" >> "$REPORTE_CARGA"
echo "Reporte de carga: $REPORTE_CARGA"
