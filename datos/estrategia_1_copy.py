#!/usr/bin/env python3
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

def medir_copy():
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"No existe el archivo {CSV_FILE}. Ejecuta generar_ordenes_prueba_50k.py primero.")

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("==============================================")
    print("ESTRATEGIA 1: COPY MASIVO (50,000 ÓRDENES SOBRE TABLA GRANDE)")
    print("==============================================")

    # Limpiamos únicamente las órdenes de prueba para mantener la medición aislada
    cursor.execute("DELETE FROM ordenes.orden_compra WHERE orden_id >= 500001;")
    conn.commit()

    # Verificar volumen base
    cursor.execute("SELECT COUNT(*) FROM ordenes.orden_compra;")
    base_count = cursor.fetchone()[0]
    print(f"Volumen base en tabla grande: {base_count:,} registros.")

    sql_copy = """
    COPY ordenes.orden_compra(
        orden_id, proveedor_id, cedi_id, fecha_creacion, 
        fecha_entrega_solicitada, fecha_recepcion, estado, total
    ) 
    FROM STDIN WITH (FORMAT csv, HEADER true);
    """

    print("Ejecutando COPY masivo de 50,000 registros...")
    inicio = time.perf_counter()
    
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        cursor.copy_expert(sql_copy, f)
    
    conn.commit()
    fin = time.perf_counter()

    tiempo_total = fin - inicio
    filas_insertadas = 50_000
    filas_por_segundo = filas_insertadas / tiempo_total

    print("\n--- RESULTADO ESTRATEGIA 1 ---")
    print(f"Filas insertadas: {filas_insertadas:,}")
    print(f"Tiempo total:     {tiempo_total:.4f} segundos")
    print(f"Rendimiento:      {filas_por_segundo:,.2f} filas/segundo")
    escribir_estrategia("COPY masivo", filas_insertadas, tiempo_total)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    medir_copy()
