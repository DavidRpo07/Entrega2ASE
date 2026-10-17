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
    # E3, optimización d: los mismos dos índices del E2, ahora "cubrientes" (INCLUDE con las
    # columnas que Q4 lee), para que el plan sea Index Only Scan sin visitar el heap. Se
    # recrean si ya existían con la definición del E2.
    "DROP INDEX IF EXISTS ordenes.idx_orden_proveedor_confirmada;",
    "DROP INDEX IF EXISTS ordenes.idx_linea_orden_id;",
    # 1. Índice Parcial Compuesto en orden_compra
    """
    CREATE INDEX IF NOT EXISTS idx_orden_proveedor_confirmada 
    ON ordenes.orden_compra (proveedor_id, fecha_creacion) 
    INCLUDE (fecha_recepcion, fecha_entrega_solicitada)
    WHERE estado = 'CONFIRMADA';
    """,
    # 2. Índice en linea_orden para el JOIN
    """
    CREATE INDEX IF NOT EXISTS idx_linea_orden_id 
    ON ordenes.linea_orden (orden_id)
    INCLUDE (categoria, cantidad_solicitada, cantidad_recibida);
    """,
    # 3. VACUUM (mapa de visibilidad para el Index Only Scan) y estadísticas para el optimizador
    """
    VACUUM (ANALYZE) ordenes.orden_compra, ordenes.linea_orden;
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
            if "CREATE INDEX" in sql:
                idx_name = sql.split("IF NOT EXISTS")[1].split()[0]
                print(f"Creando índice '{idx_name}'...")
            elif "DROP INDEX" in sql:
                print(f"{sql.strip()}")
            else:
                print("VACUUM ANALYZE (mapa de visibilidad y estadísticas)...")
            cursor.execute(sql)

        print("✔ Índices creados y estadísticas actualizadas con éxito.")
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error al crear índices: {e}")


if __name__ == "__main__":
    main()