#!/usr/bin/env python3
import csv
import time
from pathlib import Path
import psycopg2
from registrar_evidencia import escribir_estrategia

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "csv" / "ordenes_50k.csv"

# -----------------------------------------------------------------
# SENTENCIAS SQL DE VALIDACIÓN Y ESCRITURA
# -----------------------------------------------------------------

# 1. Validar Proveedor Activo y Contrato Vigente (RF01 / Q1)
QUERY_VAL_CONTRATO = """
SELECT c.contrato_id 
FROM proveedores.proveedor p
JOIN proveedores.contrato_suministro c ON p.proveedor_id = c.proveedor_id
WHERE p.proveedor_id = %s 
  AND p.estado = 'ACTIVO' 
  AND c.estado = 'VIGENTE'
  AND %s::timestamptz BETWEEN c.fecha_inicio AND c.fecha_fin
LIMIT 1;
"""

# 2. Validar SKU en Catálogo Negociado (RF02 / Q2)
QUERY_VAL_SKU = """
SELECT c.precio 
FROM catalogo.catalogo_negociado c
WHERE c.proveedor_id = %s 
  AND c.sku_id = %s 
  AND c.estado = 'ACTIVO'
  AND %s::timestamptz BETWEEN c.fecha_inicio AND c.fecha_fin
LIMIT 1;
"""

# 3. Validar y Reservar Franja de Descargue en CEDI (RF06 / Q3)
QUERY_RESERVAR_FRANJA = """
UPDATE logistica.franja_descargue
SET reservas_actuales = reservas_actuales + 1,
    estado = CASE WHEN reservas_actuales + 1 >= capacidad THEN 'COMPLETA' ELSE estado END
WHERE cedi_id = %s 
  AND fecha = %s::date
  AND estado = 'DISPONIBLE'
  AND reservas_actuales < capacidad;
"""

# 4. Inserción de Cabecera de Orden
QUERY_INSERT_ORDEN = """
INSERT INTO ordenes.orden_compra (
    orden_id, proveedor_id, cedi_id, fecha_creacion, 
    fecha_entrega_solicitada, fecha_recepcion, estado, total
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
"""

# 5. Inserción de Línea de Detalle
QUERY_INSERT_LINEA = """
INSERT INTO ordenes.linea_orden (
    orden_id, sku_id, categoria, cantidad_solicitada, cantidad_recibida, precio_unitario
) VALUES (%s, %s, %s, %s, %s, %s);
"""


def medir_ruta_transaccional_completa():
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"No existe el archivo {CSV_FILE}.")

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("==============================================")
    print("ESTRATEGIA 4: RUTA TRANSACCIONAL COMPLETA CON VALIDACIONES")
    print("Validaciones: Proveedor/Contrato, SKU/Catálogo y Reserva de Franja")
    print("==============================================")

    # Limpiamos únicamente las órdenes de prueba previas
    cursor.execute("DELETE FROM ordenes.linea_orden WHERE orden_id >= 500001;")
    cursor.execute("DELETE FROM ordenes.orden_compra WHERE orden_id >= 500001;")
    conn.commit()

    # Cargar datos desde el CSV de 50k
    ordenes = []
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ordenes.append((
                int(r["orden_id"]),
                int(r["proveedor_id"]),
                int(r["cedi_id"]),
                r["fecha_creacion"],
                r["fecha_entrega_solicitada"],
                r["fecha_recepcion"] if r["fecha_recepcion"] else None,
                r["estado"],
                float(r["total"])
            ))

    print(f"Iniciando procesamiento de {len(ordenes):,} órdenes...")
    inicio = time.perf_counter()

    procesadas_exitosas = 0

    for idx, ord_data in enumerate(ordenes):
        orden_id, prov_id, cedi_id, f_creacion, f_entrega, f_recepcion, estado, total = ord_data
        fecha_solo_dia = f_entrega.split("T")[0] if "T" in f_entrega else f_entrega.split(" ")[0]

        # 1. Validar Contrato
        cursor.execute(QUERY_VAL_CONTRATO, (prov_id, f_creacion))
        contrato_ok = cursor.fetchone()

        # 2. Validar SKU de muestra en catálogo (SKU_ID = 1 por defecto)
        cursor.execute(QUERY_VAL_SKU, (prov_id, 1, f_creacion))
        sku_ok = cursor.fetchone()

        # 3. Intentar Reserva de Franja en CEDI
        cursor.execute(QUERY_RESERVAR_FRANJA, (cedi_id, fecha_solo_dia))
        franja_reservada = cursor.rowcount > 0

        # 4. Insertar Cabecera de Orden
        cursor.execute(QUERY_INSERT_ORDEN, (orden_id, prov_id, cedi_id, f_creacion, f_entrega, f_recepcion, estado, total))

        # 5. Insertar Detalle de Línea de Orden
        precio_unit = sku_ok[0] if sku_ok else total
        cursor.execute(QUERY_INSERT_LINEA, (orden_id, 1, "alimentos", 10, 10, precio_unit))

        procesadas_exitosas += 1

        # Realizar COMMIT por lotes de 1,000 para optimizar llamadas al canal I/O
        if (idx + 1) % 1000 == 0:
            conn.commit()

    conn.commit()
    fin = time.perf_counter()

    tiempo_total = fin - inicio
    filas_por_segundo = procesadas_exitosas / tiempo_total

    print("\n--- RESULTADO ESTRATEGIA 4 ---")
    print(f"Órdenes procesadas con validación: {procesadas_exitosas:,}")
    print(f"Tiempo total de procesamiento:     {tiempo_total:.4f} segundos")
    print(f"Rendimiento de Ingesta:            {filas_por_segundo:,.2f} filas/segundo")
    escribir_estrategia("Ruta transaccional completa", procesadas_exitosas, tiempo_total)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    medir_ruta_transaccional_completa()
