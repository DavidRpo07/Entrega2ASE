#!/usr/bin/env python3
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_OUT = BASE_DIR / "csv" / "ordenes_fase4_5k.csv"

# Parámetros del dominio según el modelo existente
PROVEEDORES_VALIDOS = list(range(1, 52))  # IDs con contratos activos
CEDIS_VALIDOS = [1, 2, 3, 4, 5]
ESTADOS = ["CONFIRMADA", "RECIBIDA", "ENTREGADA"]

def generar_ordenes_fase4():
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    
    id_inicio = 600001
    total_registros = 5000
    
    fecha_base = datetime(2026, 9, 1, 10, 0, 0)
    
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "orden_id", "proveedor_id", "cedi_id", 
            "fecha_creacion", "fecha_entrega_solicitada", 
            "fecha_recepcion", "estado", "total"
        ])
        
        for i in range(total_registros):
            orden_id = id_inicio + i
            prov_id = random.choice(PROVEEDORES_VALIDOS)
            cedi_id = random.choice(CEDIS_VALIDOS)
            
            # Generar fechas coherentes
            f_creacion = fecha_base + timedelta(minutes=random.randint(1, 10000))
            f_entrega = f_creacion + timedelta(days=random.randint(1, 3))
            f_recepcion = f_entrega + timedelta(hours=random.randint(1, 5))
            
            estado = random.choice(ESTADOS)
            total = round(random.uniform(500.0, 15000.0), 2)
            
            writer.writerow([
                orden_id,
                prov_id,
                cedi_id,
                f_creacion.strftime("%Y-%m-%d %H:%M:%S-05"),
                f_entrega.strftime("%Y-%m-%d %H:%M:%S-05"),
                f_recepcion.strftime("%Y-%m-%d %H:%M:%S-05"),
                estado,
                total
            ])

    print(f"✅ Archivo CSV generado exitosamente en: {CSV_OUT}")
    print(f"  - Registros creados: {total_registros:,}")
    print(f"  - Rango de IDs: {id_inicio:,} a {id_inicio + total_registros - 1:,}")

if __name__ == "__main__":
    generar_ordenes_fase4()
