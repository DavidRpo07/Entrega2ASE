"""Utilidades para dejar evidencia reproducible de los benchmarks."""
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

RESULTADOS_DIR = Path(__file__).resolve().parent / "resultados"


def escribir_mediciones(consulta, filas):
    """Escribe una fila por ejecución; no solo percentiles agregados."""
    RESULTADOS_DIR.mkdir(exist_ok=True)
    etiqueta = os.environ.get("BENCHMARK_ETIQUETA", "base")
    destino = RESULTADOS_DIR / f"{consulta.lower()}_{etiqueta}.csv"
    campos = ["consulta", "etiqueta", "escenario", "ejecucion", "parametro", "latencia_ms", "medido_en_utc"]
    ahora = datetime.now(timezone.utc).isoformat()
    with destino.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({"consulta": consulta, "etiqueta": etiqueta,
                              "medido_en_utc": ahora, **fila})
    print(f"Evidencia cruda: {destino} ({len(filas)} ejecuciones)")
    return destino


def escribir_estrategia(nombre, filas, segundos):
    """Registra el resultado bruto agregado de una estrategia de inyección."""
    RESULTADOS_DIR.mkdir(exist_ok=True)
    destino = RESULTADOS_DIR / "estrategias_inyeccion.csv"
    existe = destino.exists()
    with destino.open("a", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=["estrategia", "filas", "duracion_s", "filas_por_s", "medido_en_utc"])
        if not existe:
            escritor.writeheader()
        escritor.writerow({"estrategia": nombre, "filas": filas, "duracion_s": f"{segundos:.6f}",
                          "filas_por_s": f"{filas / segundos:.6f}",
                          "medido_en_utc": datetime.now(timezone.utc).isoformat()})
    print(f"Evidencia cruda: {destino}")
