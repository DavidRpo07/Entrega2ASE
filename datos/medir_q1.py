import time
import random
import statistics
import psycopg2
from registrar_evidencia import escribir_mediciones

# Conexión a la base de datos
conn = psycopg2.connect(
    dbname="escalables", user="postgres", password="postgres", host="localhost", port=5432
)
cursor = conn.cursor()

sql_q1 = """
    SELECT p.estado AS estado_proveedor, c.estado AS estado_contrato, 
        CASE 
            WHEN c.contrato_id IS NULL THEN 'Proveedor sin Contrato'
            WHEN %s::timestamptz BETWEEN c.fecha_inicio AND c.fecha_fin THEN 'Contrato Vigente'
            ELSE 'Contrato No Vigente'
        END AS revision_estado_contrato  
    FROM proveedores.proveedor p
    LEFT JOIN proveedores.contrato_suministro c 
        ON p.proveedor_id = c.proveedor_id AND c.estado = 'VIGENTE'
    WHERE p.proveedor_id = %s;
"""

def medir_escenario(ids_list, fecha_evaluacion="2026-09-16 10:00:00-05"):
    tiempos = []
    mediciones = []
    rng = random.Random(42)
    for ejecucion in range(1, 101):
        prov_id = rng.choice(ids_list)
        t_inicio = time.perf_counter_ns()
        
        cursor.execute(sql_q1, (fecha_evaluacion, prov_id))
        cursor.fetchall()
        
        t_fin = time.perf_counter_ns()
        latencia_ms = (t_fin - t_inicio) / 1_000_000.0
        tiempos.append(latencia_ms)
        mediciones.append((ejecucion, f"proveedor_id={prov_id}", latencia_ms))
    
    tiempos_ordenados = sorted(tiempos)
    p50 = statistics.quantiles(tiempos_ordenados, n=100)[49]
    p95 = statistics.quantiles(tiempos_ordenados, n=100)[94]
    p99 = statistics.quantiles(tiempos_ordenados, n=100)[98]
    return round(p50, 3), round(p95, 3), round(p99, 3), mediciones

def obtener_explain_analyze(prov_id, fecha_evaluacion="2026-09-16 10:00:00-05"):
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS) {sql_q1}"
    cursor.execute(explain_sql, (fecha_evaluacion, prov_id))
    rows = cursor.fetchall()
    return "\n".join(r[0] for r in rows)

def main():
    cursor.execute("SELECT proveedor_id FROM ordenes.orden_compra GROUP BY proveedor_id ORDER BY COUNT(*) DESC LIMIT 50")
    hot_ids = [r[0] for r in cursor.fetchall()]
    # La selección de la cola no cruza fronteras de esquemas.
    cursor.execute("SELECT proveedor_id FROM proveedores.proveedor WHERE proveedor_id > 90000 LIMIT 50")
    cold_ids = [r[0] for r in cursor.fetchall()]
    cold_p50, cold_p95, cold_p99, raw_cold = medir_escenario(cold_ids)
    hot_p50, hot_p95, hot_p99, raw_hot = medir_escenario(hot_ids)
    escribir_mediciones("Q1", [
        {"escenario": escenario, "ejecucion": n, "parametro": parametro, "latencia_ms": f"{latencia:.6f}"}
        for escenario, grupo in (("caliente", raw_hot), ("frio", raw_cold))
        for n, parametro, latencia in grupo
    ])
    sample_hot_id, sample_cold_id = hot_ids[0], cold_ids[0]
    print("RESULTADOS DE MEDICIÓN PARA Q1 (200 EJECUCIONES)")
    print(f"Frío -> p50: {cold_p50} ms | p95: {cold_p95} ms | p99: {cold_p99} ms")
    print(f"Caliente -> p50: {hot_p50} ms | p95: {hot_p95} ms | p99: {hot_p99} ms")
    print(obtener_explain_analyze(sample_hot_id))
    print(obtener_explain_analyze(sample_cold_id))
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
