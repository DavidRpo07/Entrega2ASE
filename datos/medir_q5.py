#!/usr/bin/env python3
import math
import random
import time
import psycopg2
from registrar_evidencia import escribir_mediciones

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

QUERY_Q5 = """
SELECT 
    o.orden_id,
    o.proveedor_id,
    o.cedi_id,
    o.fecha_creacion,
    o.estado,
    o.total
FROM ordenes.orden_compra o
WHERE o.proveedor_id = %s
ORDER BY o.fecha_creacion DESC
LIMIT 50 OFFSET %s;
"""


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


def obtener_proveedores(cursor):
    # Hot: Proveedor Top Zipf con más órdenes
    cursor.execute("""
        SELECT proveedor_id 
        FROM ordenes.orden_compra 
        GROUP BY proveedor_id 
        ORDER BY COUNT(*) DESC 
        LIMIT 50;
    """)
    hot_provs = [r[0] for r in cursor.fetchall()]

    # Cold: Proveedores con pocas órdenes (Cola larga)
    cursor.execute("""
        SELECT proveedor_id 
        FROM ordenes.orden_compra 
        GROUP BY proveedor_id 
        HAVING COUNT(*) BETWEEN 1 AND 20
        LIMIT 50;
    """)
    cold_provs = [r[0] for r in cursor.fetchall()]

    return hot_provs, cold_provs


def medir_escenario(cursor, prov_ids, num_runs=100):
    rng = random.Random(42)
    tiempos = []
    mediciones = []

    for ejecucion in range(1, num_runs + 1):
        p_id = rng.choice(prov_ids)
        offset = rng.choice([0, 50, 100])
        inicio = time.perf_counter()
        cursor.execute(QUERY_Q5, (p_id, offset))
        cursor.fetchall()
        fin = time.perf_counter()
        latencia = (fin - inicio) * 1000
        tiempos.append(latencia)
        mediciones.append((ejecucion, f"proveedor_id={p_id};offset={offset}", latencia))

    p50 = calcular_percentil(tiempos, 50)
    p95 = calcular_percentil(tiempos, 95)
    p99 = calcular_percentil(tiempos, 99)

    return p50, p95, p99, prov_ids[0], mediciones


def obtener_explain(cursor, p_id, offset=0):
    query_explain = f"EXPLAIN (ANALYZE, BUFFERS) {QUERY_Q5}"
    cursor.execute(query_explain, (p_id, offset))
    plan = cursor.fetchall()
    return "\n".join([linea[0] for linea in plan])


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("==============================================")
    print("SELECCIONANDO PROVEEDORES Y MIDIENDO Q5 BASE")
    print("==============================================")
    
    hot_provs, cold_provs = obtener_proveedores(cursor)

    p50_h, p95_h, p99_h, sample_hot_id, raw_hot = medir_escenario(cursor, hot_provs, 100)
    p50_c, p95_c, p99_c, sample_cold_id, raw_cold = medir_escenario(cursor, cold_provs, 100)
    escribir_mediciones("Q5", [
        {"escenario": escenario, "ejecucion": n, "parametro": parametro, "latencia_ms": f"{latencia:.6f}"}
        for escenario, grupo in (("caliente", raw_hot), ("frio", raw_cold))
        for n, parametro, latencia in grupo
    ])

    explain_hot = obtener_explain(cursor, sample_hot_id, 0)
    explain_cold = obtener_explain(cursor, sample_cold_id, 0)

    print("\n--- RESULTADOS MEDICIÓN ---")
    print("Escenario Caliente (Proveedor Hot - 100 runs):")
    print(f"  p50: {p50_h:.3f} ms | p95: {p95_h:.3f} ms | p99: {p99_h:.3f} ms")

    print("\nEscenario Frío (Cola Larga - 100 runs):")
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
