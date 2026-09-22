#!/usr/bin/env python3
import psycopg2

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

SQL_INDICE = """
CREATE INDEX IF NOT EXISTS idx_orden_proveedor_fecha 
ON ordenes.orden_compra (proveedor_id, fecha_creacion DESC);

ANALYZE ordenes.orden_compra;
"""

def main():
    print("==============================================")
    print("CREANDO ÍNDICE DISEÑADO: idx_orden_proveedor_fecha")
    print("==============================================")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(SQL_INDICE)
    print("✔ Índice creado y ANALYZE ejecutado correctamente.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()