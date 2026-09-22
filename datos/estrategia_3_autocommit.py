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

def medir_autocommit():
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"No existe el archivo {CSV_FILE}.")

    conn = psycopg2.connect(**DB_CONFIG)
    # Habilitar autocommit explícito (1 transacción e I/O de disco por cada fila)
    conn.autocommit = True
    cursor = conn.cursor()

    print("==============================================")
    print("ESTRATEGIA 3: INSERT FILA POR FILA (AUTOCOMMIT)")
    print("==============================================")

    # Limpiamos las 50,000 órdenes de prueba previas
    cursor.execute("DELETE FROM ordenes.orden_compra WHERE orden_id >= 500001;")

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
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """

    print("Ejecutando 50,000 INSERTs individuales con AUTOCOMMIT...")
    inicio = time.perf_counter()
    
    for fila in filas:
        cursor.execute(query_insert, fila)
    
    fin = time.perf_counter()

    tiempo_total = fin - inicio
    filas_insertadas = len(filas)
    filas_por_segundo = filas_insertadas / tiempo_total

    print("\n--- RESULTADO ESTRATEGIA 3 ---")
    print(f"Filas insertadas: {filas_insertadas:,}")
    print(f"Tiempo total:     {tiempo_total:.4f} segundos")
    print(f"Rendimiento:      {filas_por_segundo:,.2f} filas/segundo")
    escribir_estrategia("INSERT fila a fila con autocommit", filas_insertadas, tiempo_total)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    medir_autocommit()
