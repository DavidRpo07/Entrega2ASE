#!/usr/bin/env python3
import csv
import time
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
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

def medir_lotes():
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"No existe el archivo {CSV_FILE}.")

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("==============================================")
    print("ESTRATEGIA 2: INSERT POR LOTES DE 1,000 (1 TRANSACCIÓN)")
    print("==============================================")

    # Limpiamos las 50,000 órdenes de prueba previas
    cursor.execute("DELETE FROM ordenes.orden_compra WHERE orden_id >= 500001;")
    conn.commit()

    # Cargar datos desde el CSV
    filas = []
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            filas.append((
                int(r["orden_id"]),
                int(r["proveedor_id"]),
                int(r["cedi_id"]),
                r["fecha_creacion"],
                r["fecha_entrega_solicitada"],
                r["fecha_recepcion"] if r["fecha_recepcion"] else None,
                r["estado"],
                float(r["total"])
            ))

    query_insert = """
    INSERT INTO ordenes.orden_compra (
        orden_id, proveedor_id, cedi_id, fecha_creacion, 
        fecha_entrega_solicitada, fecha_recepcion, estado, total
    ) VALUES %s;
    """

    print("Ejecutando INSERT por lotes de 1,000 en una única transacción...")
    inicio = time.perf_counter()
    
    # Insertar en lotes de 1,000 dentro de la misma transacción
    tamanio_lote = 1000
    for i in range(0, len(filas), tamanio_lote):
        lote = filas[i:i + tamanio_lote]
        execute_values(cursor, query_insert, lote, page_size=tamanio_lote)
    
    conn.commit()  # Único commit al final
    fin = time.perf_counter()

    tiempo_total = fin - inicio
    filas_insertadas = len(filas)
    filas_por_segundo = filas_insertadas / tiempo_total

    print("\n--- RESULTADO ESTRATEGIA 2 ---")
    print(f"Filas insertadas: {filas_insertadas:,}")
    print(f"Tiempo total:     {tiempo_total:.4f} segundos")
    print(f"Rendimiento:      {filas_por_segundo:,.2f} filas/segundo")
    escribir_estrategia("INSERT por lotes de 1000", filas_insertadas, tiempo_total)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    medir_lotes()
