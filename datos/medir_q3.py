#!/usr/bin/env python3
import calendar
import math
import random
import time
from datetime import datetime, timedelta
import psycopg2
from registrar_evidencia import escribir_mediciones

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

QUERY_Q3 = """
SELECT 
    f.franja_id,
    f.hora_inicio, 
    f.hora_fin, 
    (f.capacidad - f.reservas_actuales) AS cupo_disponible
FROM logistica.franja_descargue f
WHERE f.cedi_id = %s 
  AND f.fecha = %s::date
  AND f.estado = 'DISPONIBLE';
"""

FECHA_CASO_BORDE = "2026-09-16"  # Fecha del Caso Borde #4


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


def obtener_ultimos_tres_dias_habiles():
    """Genera las fechas de los últimos 3 días hábiles de cada mes para 2025 y 2026."""
    fechas_pico = []
    for year in [2025, 2026]:
        for month in range(1, 13):
            _, num_days = calendar.monthrange(year, month)
            ultimo_dia = datetime(year, month, num_days)
            
            dias_habiles = []
            curr = ultimo_dia
            while len(dias_habiles) < 3 and curr.month == month:
                if curr.weekday() < 5:  # Lunes a Viernes
                    dias_habiles.append(curr.date())
                curr -= timedelta(days=1)
            fechas_pico.extend([d.isoformat() for d in dias_habiles])
    return fechas_pico


def obtener_dias_valle_mitad_mes():
    """Genera las fechas de mitad de mes (días 12 a 15) para 2025 y 2026."""
    fechas_valle = []
    for year in [2025, 2026]:
        for month in range(1, 13):
            for day in [12, 13, 14, 15]:
                fechas_valle.append(datetime(year, month, day).date().isoformat())
    return fechas_valle


def construir_pools_parametros(num_muestras_por_pool=100):
    rng = random.Random(42)

    fechas_pico = obtener_ultimos_tres_dias_habiles()
    fechas_valle = obtener_dias_valle_mitad_mes()

    # 1. Pool Caliente: Días pico de fin de mes (incluye Caso Borde #4)
    pool_hot = [(1, FECHA_CASO_BORDE)]
    for _ in range(num_muestras_por_pool - 1):
        cedi_id = rng.randint(1, 5)
        fecha_eval = rng.choice(fechas_pico)
        pool_hot.append((cedi_id, fecha_eval))

    # 2. Pool Frío: Días de mitad de mes (baja carga / valle)
    pool_cold = []
    for _ in range(num_muestras_por_pool):
        cedi_id = rng.randint(1, 5)
        fecha_eval = rng.choice(fechas_valle)
        pool_cold.append((cedi_id, fecha_eval))

    return pool_hot, pool_cold


def medir_escenario(cursor, pool_parametros):
    tiempos = []
    mediciones = []

    for ejecucion, (cedi_id, fecha) in enumerate(pool_parametros, start=1):
        inicio = time.perf_counter()
        cursor.execute(QUERY_Q3, (cedi_id, fecha))
        cursor.fetchall()
        fin = time.perf_counter()
        latencia = (fin - inicio) * 1000
        tiempos.append(latencia)
        mediciones.append((ejecucion, f"cedi_id={cedi_id};fecha={fecha}", latencia))

    p50 = calcular_percentil(tiempos, 50)
    p95 = calcular_percentil(tiempos, 95)
    p99 = calcular_percentil(tiempos, 99)

    return p50, p95, p99, mediciones


def obtener_explain(cursor, cedi_id, fecha):
    query_explain = f"EXPLAIN (ANALYZE, BUFFERS) {QUERY_Q3}"
    cursor.execute(query_explain, (cedi_id, fecha))
    plan = cursor.fetchall()
    return "\n".join([linea[0] for linea in plan])


def main():
    print("==============================================")
    print("PREPARANDO PARÁMETROS DE EVALUACIÓN PARA Q3")
    print("==============================================")
    
    pool_hot, pool_cold = construir_pools_parametros(num_muestras_por_pool=100)
    
    print(f"Pool Caliente: {len(pool_hot)} variaciones (Picos de Fin de Mes).")
    print(f"Pool Frío: {len(pool_cold)} variaciones (Días Valle - Mitad de Mes).")
    print(f"Total de corridas a ejecutar: {len(pool_hot) + len(pool_cold)}")

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("\n==============================================")
    print("MEDICIÓN Q3 CON PARÁMETROS VARIADOS (200 RUNS)")
    print("==============================================")

    # Medir escenarios
    p50_h, p95_h, p99_h, raw_hot = medir_escenario(cursor, pool_hot)
    p50_c, p95_c, p99_c, raw_cold = medir_escenario(cursor, pool_cold)
    escribir_mediciones("Q3", [
        {"escenario": escenario, "ejecucion": n, "parametro": parametro, "latencia_ms": f"{latencia:.6f}"}
        for escenario, grupo in (("caliente", raw_hot), ("frio", raw_cold))
        for n, parametro, latencia in grupo
    ])

    # Muestras de EXPLAIN
    explain_hot = obtener_explain(cursor, pool_hot[0][0], pool_hot[0][1])
    explain_cold = obtener_explain(cursor, pool_cold[0][0], pool_cold[0][1])

    print("\n--- RESULTADOS MEDICIÓN ---")
    print("Escenario Caliente (Últimos 3 Días Hábiles del Mes - 100 runs):")
    print(f"  p50: {p50_h:.3f} ms | p95: {p95_h:.3f} ms | p99: {p99_h:.3f} ms")

    print("\nEscenario Frío (Días Valle / Mitad de Mes - 100 runs):")
    print(f"  p50: {p50_c:.3f} ms | p95: {p95_c:.3f} ms | p99: {p99_c:.3f} ms")

    print("\n==============================================")
    print("EXPLAIN ANALYZE (Muestra Escenario Caliente - Fin de Mes)")
    print("==============================================")
    print(explain_hot)

    print("\n==============================================")
    print("EXPLAIN ANALYZE (Muestra Escenario Frío - Mitad de Mes)")
    print("==============================================")
    print(explain_cold)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
