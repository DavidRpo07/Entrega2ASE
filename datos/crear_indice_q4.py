#!/usr/bin/env python3
import psycopg2

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

INDICES_SQL = [
    # 1. Índice Parcial Compuesto en orden_compra
    """
    CREATE INDEX IF NOT EXISTS idx_orden_proveedor_confirmada 
    ON ordenes.orden_compra (proveedor_id, fecha_creacion) 
    WHERE estado = 'CONFIRMADA';
    """,
    # 2. Índice Simple en linea_orden para el JOIN
    """
    CREATE INDEX IF NOT EXISTS idx_linea_orden_id 
    ON ordenes.linea_orden (orden_id);
    """,
    # 3. Actualizar estadísticas para el optimizador
    """
    ANALYZE ordenes.orden_compra, ordenes.linea_orden;
    """
]


def main():
    print("==============================================")
    print("APLICANDO ÍNDICES DE OPTIMIZACIÓN PARA Q4")
    print("==============================================")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()

        for sql in INDICES_SQL:
            # Extraer el nombre del índice para los logs
            if "INDEX" in sql:
                idx_name = sql.split("IF NOT EXISTS")[1].split()[0]
                print(f"Creando índice '{idx_name}'...")
            else:
                print("Actualizando estadísticas con ANALYZE...")
            cursor.execute(sql)

        print("✔ Índices creados y estadísticas actualizadas con éxito.")
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error al crear índices: {e}")


if __name__ == "__main__":
    main()