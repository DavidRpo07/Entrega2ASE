#!/usr/bin/env python3
import psycopg2

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

# E3, optimización d: el mismo índice del E2, ahora cubriente (INCLUDE con las columnas que
# devuelve Q5) para que la paginación sea Index Only Scan; VACUUM para el mapa de visibilidad.
SQL_INDICE = """
DROP INDEX IF EXISTS ordenes.idx_orden_proveedor_fecha;

CREATE INDEX IF NOT EXISTS idx_orden_proveedor_fecha 
ON ordenes.orden_compra (proveedor_id, fecha_creacion DESC)
INCLUDE (orden_id, cedi_id, estado, total);
"""
SQL_VACUUM = "VACUUM (ANALYZE) ordenes.orden_compra;"

def main():
    print("==============================================")
    print("CREANDO ÍNDICE DISEÑADO: idx_orden_proveedor_fecha")
    print("==============================================")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(SQL_INDICE)
    cursor.execute(SQL_VACUUM)   # VACUUM no puede ir en el mismo comando que otras sentencias
    print("✔ Índice creado y VACUUM ANALYZE ejecutado correctamente.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()