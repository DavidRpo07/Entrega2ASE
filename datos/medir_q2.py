#!/usr/bin/env python3
import csv
import math
import random
import time
from pathlib import Path
import psycopg2
from registrar_evidencia import escribir_mediciones

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

QUERY_Q2 = """
SELECT 
    c.sku_id, 
    c.precio
FROM catalogo.catalogo_negociado c
WHERE c.proveedor_id = %s
  AND c.sku_id = ANY(%s)
  AND c.estado = 'ACTIVO'
  AND %s::timestamptz BETWEEN c.fecha_inicio AND c.fecha_fin;
"""

FECHA_EVALUACION = "2026-09-16 10:00:00-05"
BASE_DIR = Path(__file__).resolve().parent
CSV_CATALOGO = BASE_DIR / "csv" / "catalogo_negociado.csv"


def calcular_percentil(datos, p):
    if not datos:
        return 0.0
    datos_ordenados = sorted(datos)
    k = (len(datos_ordenados) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return datos_ordenados[int(k)]
    d0 = datos_ordenados[int(f)] * (c - k)
    d1 = datos_ordenados[int(c)] * (k - f)
    return d0 + d1


def cargar_catalogos_desde_csv():
    """
    Lee catalogo_negociado.csv directamente desde el disco con Python
    para no tocar ni precalentar la RAM de PostgreSQL.
    """
    if not CSV_CATALOGO.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {CSV_CATALOGO}")

    catalogos_por_proveedor = {}
    with open(CSV_CATALOGO, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Limpieza básica de claves/valores por espacios accidentales
            row = {k.strip(): v.strip() for k, v in r.items() if k}
            
            if row.get("estado") == "ACTIVO":
                p_id = int(row["proveedor_id"])
                s_id = int(row["sku_id"])
                if p_id not in catalogos_por_proveedor:
                    catalogos_por_proveedor[p_id] = []
                catalogos_por_proveedor[p_id].append(s_id)

    return catalogos_por_proveedor


def construir_pools_parametros(catalogos_por_proveedor, num_muestras_por_pool=100):
    rng = random.Random(42)

    # 1. Pool Caliente: Muestreo sobre proveedores base (Top Zipf, ID <= 51)
    provs_hot = [p_id for p_id in catalogos_por_proveedor.keys() if p_id <= 51]
    pool_hot = []
    for _ in range(num_muestras_por_pool):
        p_id = rng.choice(provs_hot)
        skus = catalogos_por_proveedor[p_id]
        skus_muestra = rng.sample(skus, min(20, len(skus)))
        pool_hot.append((p_id, skus_muestra))

    # 2. Pool Frío: Proveedores DISTINTOS de la cola larga (ID > 100) con >= 20 SKUs
    provs_cold = [
        p_id for p_id, skus in catalogos_por_proveedor.items()
        if p_id > 100 and len(skus) >= 20
    ]
    
    # Tomamos exactamente 'num_muestras_por_pool' proveedores únicos
    provs_cold_seleccionados = rng.sample(provs_cold, min(num_muestras_por_pool, len(provs_cold)))
    
    pool_cold = []
    for p_id in provs_cold_seleccionados:
        skus = catalogos_por_proveedor[p_id]
        skus_muestra = rng.sample(skus, 20)
        pool_cold.append((p_id, skus_muestra))

    return pool_hot, pool_cold


def medir_escenario(cursor, pool_parametros):
    tiempos = []
    mediciones = []

    for ejecucion, (p_id, skus) in enumerate(pool_parametros, start=1):
        inicio = time.perf_counter()
        cursor.execute(QUERY_Q2, (p_id, skus, FECHA_EVALUACION))
        cursor.fetchall()
        fin = time.perf_counter()
        latencia = (fin - inicio) * 1000
        tiempos.append(latencia)
        mediciones.append((ejecucion, f"proveedor_id={p_id};skus={','.join(map(str, skus))}", latencia))

    p50 = calcular_percentil(tiempos, 50)
    p95 = calcular_percentil(tiempos, 95)
    p99 = calcular_percentil(tiempos, 99)

    return p50, p95, p99, mediciones


def obtener_explain(cursor, p_id, skus):
    query_explain = f"EXPLAIN (ANALYZE, BUFFERS) {QUERY_Q2}"
    cursor.execute(query_explain, (p_id, skus, FECHA_EVALUACION))
    plan = cursor.fetchall()
    return "\n".join([linea[0] for linea in plan])


def main():
    print("==============================================")
    print("PREPARANDO PARÁMETROS DESDE CSV (CERO CONSULTAS PREVIAS)")
    print("==============================================")
    catalogos = cargar_catalogos_desde_csv()
    
    # Exactamente 100 y 100 para completar las 200 ejecuciones totales
    pool_hot, pool_cold = construir_pools_parametros(catalogos, num_muestras_por_pool=100)
    
    print(f"Pool Caliente: {len(pool_hot)} variaciones (Top Zipf).")
    print(f"Pool Frío: {len(pool_cold)} proveedores distintos (Cola Larga).")
    print(f"Total de corridas a ejecutar: {len(pool_hot) + len(pool_cold)}")

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("\n==============================================")
    print("MEDICIÓN Q2 CON PARÁMETROS VARIADOS (200 RUNS)")
    print("==============================================")

    # Medir escenarios
    p50_h, p95_h, p99_h, raw_hot = medir_escenario(cursor, pool_hot)
    p50_c, p95_c, p99_c, raw_cold = medir_escenario(cursor, pool_cold)
    escribir_mediciones("Q2", [
        {"escenario": escenario, "ejecucion": n, "parametro": parametro, "latencia_ms": f"{latencia:.6f}"}
        for escenario, grupo in (("caliente", raw_hot), ("frio", raw_cold))
        for n, parametro, latencia in grupo
    ])

    # Muestras de EXPLAIN
    explain_hot = obtener_explain(cursor, pool_hot[0][0], pool_hot[0][1])
    explain_cold = obtener_explain(cursor, pool_cold[0][0], pool_cold[0][1])

    print("\n--- RESULTADOS MEDICIÓN ---")
    print("Escenario Caliente (Top Zipf - 100 runs):")
    print(f"  p50: {p50_h:.3f} ms | p95: {p95_h:.3f} ms | p99: {p99_h:.3f} ms")

    print("\nEscenario Frío (100 Proveedores Distintos Cola Larga - 100 runs):")
    print(f"  p50: {p50_c:.3f} ms | p95: {p95_c:.3f} ms | p99: {p99_c:.3f} ms")

    print("\n==============================================")
    print("EXPLAIN ANALYZE (Muestra Escenario Caliente)")
    print("==============================================")
    print(explain_hot)

    print("\n==============================================")
    print("EXPLAIN ANALYZE (Muestra Escenario Frío)")
    print("==============================================")
    print(explain_cold)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
