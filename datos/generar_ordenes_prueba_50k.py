#!/usr/bin/env python3
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
NUM_ORDENES_NUEVAS = 50_000
ID_INICIAL = 500_001  # Para insertar sobre las 500,000 que ya existen

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "csv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUTPUT_DIR / "ordenes_50k.csv"

FECHA_INICIO = datetime(2026, 1, 1, tzinfo=timezone.utc)

def generar_ordenes():
    rng = random.Random(SEED)
    estados = ["PENDIENTE", "EN_VALIDACION", "CONFIRMADA", "RECHAZADA", "CANCELADA"]
    pesos_estados = [0.05, 0.10, 0.70, 0.10, 0.05]

    print(f"Generando {NUM_ORDENES_NUEVAS:,} órdenes de prueba (IDs {ID_INICIAL:,} a {ID_INICIAL + NUM_ORDENES_NUEVAS - 1:,})...")

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "orden_id", "proveedor_id", "cedi_id", "fecha_creacion", 
            "fecha_entrega_solicitada", "fecha_recepcion", "estado", "total"
        ])

        for i in range(NUM_ORDENES_NUEVAS):
            orden_id = ID_INICIAL + i
            proveedor_id = rng.randint(1, 100_000)
            cedi_id = rng.randint(1, 5)
            
            offset_dias = rng.randint(0, 300)
            fecha_creacion = FECHA_INICIO + timedelta(
                days=offset_dias, 
                hours=rng.randint(6, 20), 
                minutes=rng.randint(0, 59)
            )
            
            fecha_entrega_solicitada = fecha_creacion + timedelta(days=rng.randint(2, 5))
            estado = rng.choices(estados, weights=pesos_estados, k=1)[0]
            
            if estado == "CONFIRMADA":
                fecha_recepcion = (fecha_entrega_solicitada + timedelta(hours=rng.randint(-12, 12))).isoformat()
            else:
                fecha_recepcion = ""

            total = round(rng.uniform(100.0, 15000.0), 2)

            writer.writerow([
                orden_id, proveedor_id, cedi_id, fecha_creacion.isoformat(),
                fecha_entrega_solicitada.isoformat(), fecha_recepcion, estado, f"{total:.2f}"
            ])

    print(f"✅ Archivo listo: {CSV_FILE}")

if __name__ == "__main__":
    generar_ordenes()