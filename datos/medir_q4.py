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

QUERY_Q4 = """
WITH detalle_orden_categoria AS (
    SELECT 
        o.proveedor_id,
        l.categoria,
        DATE_TRUNC('month', o.fecha_creacion)::date AS mes,
        o.orden_id,
        CASE 
            WHEN o.fecha_recepcion IS NOT NULL 
                 AND o.fecha_recepcion::date <= o.fecha_entrega_solicitada::date THEN 1 
            ELSE 0 
        END AS es_on_time,
        CASE 
            WHEN BOOL_AND(l.cantidad_recibida = l.cantidad_solicitada) THEN 1 
            ELSE 0 
        END AS es_in_full,
        SUM(l.cantidad_solicitada) AS cant_solicitada,
        SUM(l.cantidad_recibida) AS cant_recibida
    FROM ordenes.orden_compra o
    JOIN ordenes.linea_orden l ON o.orden_id = l.orden_id
    WHERE o.estado = 'CONFIRMADA'
      AND o.proveedor_id = %s
    GROUP BY o.proveedor_id, l.categoria, DATE_TRUNC('month', o.fecha_creacion), o.orden_id, o.fecha_recepcion, o.fecha_entrega_solicitada
)
SELECT 
    proveedor_id,
    categoria,
    TO_CHAR(mes, 'YYYY-MM') AS periodo,
    COUNT(orden_id) AS total_ordenes,
    ROUND(
        (SUM(cant_recibida)::numeric / NULLIF(SUM(cant_solicitada), 0)) * 100, 2
    ) AS fill_rate_pct,
    ROUND(
        (COUNT(CASE WHEN es_on_time = 1 AND es_in_full = 1 THEN 1 END)::numeric / COUNT(orden_id)) * 100, 2
    ) AS otif_pct
FROM detalle_orden_categoria
GROUP BY proveedor_id, categoria, mes
ORDER BY mes DESC, categoria;
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


def medir_escenario(cursor, ids_list):
    tiempos = []
    mediciones = []
    rng = random.Random(42)
    for ejecucion in range(1, 101):
        prov_id = rng.choice(ids_list)
        inicio = time.perf_counter()
        cursor.execute(QUERY_Q4, (prov_id,))
        cursor.fetchall()
        fin = time.perf_counter()
        latencia = (fin - inicio) * 1000
        tiempos.append(latencia)
        mediciones.append((ejecucion, f"proveedor_id={prov_id}", latencia))

    p50 = calcular_percentil(tiempos, 50)
    p95 = calcular_percentil(tiempos, 95)
    p99 = calcular_percentil(tiempos, 99)
    return p50, p95, p99, mediciones


def obtener_explain(cursor, prov_id):
    query_explain = f"EXPLAIN (ANALYZE, BUFFERS) {QUERY_Q4}"
    cursor.execute(query_explain, (prov_id,))
    plan = cursor.fetchall()
    return "\n".join([linea[0] for linea in plan])


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("==============================================")
    print("SELECCIONANDO PARÁMETROS (HOT Y COLD) PARA Q4")
    print("==============================================")
    
    # Proveedores Hot: Top proveedores con más órdenes confirmadas
    cursor.execute("""
        SELECT proveedor_id FROM ordenes.orden_compra 
        WHERE estado = 'CONFIRMADA'
        GROUP BY proveedor_id ORDER BY COUNT(*) DESC LIMIT 50;
    """)
    hot_ids = [r[0] for r in cursor.fetchall()]
    if not hot_ids:
        hot_ids = [1, 2, 3, 4, 5]

    # Proveedores fríos: cola larga dentro del módulo de órdenes.
    cursor.execute("""
        SELECT proveedor_id FROM ordenes.orden_compra
        WHERE estado = 'CONFIRMADA'
        GROUP BY proveedor_id HAVING COUNT(*) BETWEEN 1 AND 20
        LIMIT 50;
    """)
    cold_ids = [r[0] for r in cursor.fetchall()]
    if len(cold_ids) < 10:
        cursor.execute("SELECT proveedor_id FROM ordenes.orden_compra ORDER BY proveedor_id DESC LIMIT 50;")
        cold_ids = [r[0] for r in cursor.fetchall()]

    print(f"Pool Caliente: {len(hot_ids)} proveedores (Top).")
    print(f"Pool Frío: {len(cold_ids)} proveedores (Cola Larga).")

    print("\n==============================================")
    print("MEDICIÓN Q4 CON PARÁMETROS VARIADOS (200 RUNS)")
    print("==============================================")

    p50_h, p95_h, p99_h, raw_hot = medir_escenario(cursor, hot_ids)
    p50_c, p95_c, p99_c, raw_cold = medir_escenario(cursor, cold_ids)
    escribir_mediciones("Q4", [
        {"escenario": escenario, "ejecucion": n, "parametro": parametro, "latencia_ms": f"{latencia:.6f}"}
        for escenario, grupo in (("caliente", raw_hot), ("frio", raw_cold))
        for n, parametro, latencia in grupo
    ])

    explain_hot = obtener_explain(cursor, hot_ids[0])

    print("\n--- RESULTADOS MEDICIÓN ---")
    print("Escenario Caliente (Top Proveedores - 100 runs):")
    print(f"  p50: {p50_h:.3f} ms | p95: {p95_h:.3f} ms | p99: {p99_h:.3f} ms")

    print("\nEscenario Frío (Cola Larga - 100 runs):")
    print(f"  p50: {p50_c:.3f} ms | p95: {p95_c:.3f} ms | p99: {p99_c:.3f} ms")

    print("\n==============================================")
    print("EXPLAIN ANALYZE (Muestra Escenario Caliente)")
    print("==============================================")
    print(explain_hot)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
