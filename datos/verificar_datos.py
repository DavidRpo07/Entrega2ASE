#!/usr/bin/env python3

import csv
import hashlib
import calendar
from pathlib import Path
from collections import Counter
from datetime import datetime, date

BASE_DIR = Path(__file__).resolve().parent
CSV_DIR = BASE_DIR / "csv"

VOLUMENES_MINIMOS = {
    "proveedor.csv": 100_000,
    "contrato_suministro.csv": 10_000,
    "sku.csv": 200_000,
    "catalogo_negociado.csv": 200_000,
    "cedi.csv": 5,
    "franja_descargue.csv": 90_000,
    "orden_compra.csv": 300_000,
    "linea_orden.csv": 1_500_000,
    "evento_auditoria.csv": 500_000,
}


def verificar_volumetria() -> bool:
    print("\n--- 1. VERIFICACIÓN DE VOLUMETRÍA MÍNIMA (9 TABLAS) ---")
    todo_pasa = True
    for archivo, minimo in VOLUMENES_MINIMOS.items():
        ruta = CSV_DIR / archivo
        if not ruta.exists():
            print(f"❌ {archivo}: No existe en {CSV_DIR}")
            todo_pasa = False
            continue

        with open(ruta, "r", encoding="utf-8") as f:
            total = sum(1 for _ in f) - 1

        if total >= minimo:
            print(f"[PASA] {archivo}: {total:,} filas (Mínimo exigido: {minimo:,})")
        else:
            print(f"❌ [FALLA] {archivo}: {total:,} filas (Mínimo exigido: {minimo:,})")
            todo_pasa = False

    return todo_pasa


def verificar_distribucion_zipf() -> bool:
    print("\n--- 2. VERIFICACIÓN DE SESGO ZIPF EN PROVEEDORES ---")
    ruta_ord = CSV_DIR / "orden_compra.csv"
    if not ruta_ord.exists():
        print("❌ orden_compra.csv no existe")
        return False

    conteo = Counter()
    total_ordenes = 0
    with open(ruta_ord, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conteo[int(r["proveedor_id"])] += 1
            total_ordenes += 1

    proveedores_ordenados = conteo.most_common()
    num_provs_contrato = len(conteo)

    top_1_pct_count = max(1, int(num_provs_contrato * 0.01))
    top_5_pct_count = max(1, int(num_provs_contrato * 0.05))

    sum_top_1 = sum(c for _, c in proveedores_ordenados[:top_1_pct_count])
    sum_top_5 = sum(c for _, c in proveedores_ordenados[:top_5_pct_count])

    pct_top_1 = (sum_top_1 / total_ordenes) * 100
    pct_top_5 = (sum_top_5 / total_ordenes) * 100

    print(f"  Concentración Top 1% ({top_1_pct_count} provs): {pct_top_1:.2f}% de órdenes (Objetivo ~15%)")
    print(f"  Concentración Top 5% ({top_5_pct_count} provs): {pct_top_5:.2f}% de órdenes (Objetivo ~40%)")

    if 10.0 <= pct_top_1 <= 25.0 and 30.0 <= pct_top_5 <= 55.0:
        print("[PASA] Distribución Zipf de proveedores verificada.")
        return True
    else:
        print("❌ [FALLA] Distribución Zipf de proveedores fuera de rango.")
        return False


def verificar_sesgo_catalogo() -> bool:
    print("\n--- 3. VERIFICACIÓN DE SESGO EN EL CATÁLOGO (10% SKU -> 60% LÍNEAS) ---")
    ruta_lin = CSV_DIR / "linea_orden.csv"
    if not ruta_lin.exists():
        print("❌ linea_orden.csv no existe")
        return False

    conteo_sku = Counter()
    total_lineas = 0
    with open(ruta_lin, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conteo_sku[int(r["sku_id"])] += 1
            total_lineas += 1

    top_10_pct_count = max(1, int(400_000 * 0.10))
    skus_ordenados = conteo_sku.most_common()
    sum_top_10 = sum(c for _, c in skus_ordenados[:top_10_pct_count])
    pct_top_10 = (sum_top_10 / total_lineas) * 100

    print(f"  SKUs únicos presentes: {len(conteo_sku):,}")
    print(f"  Concentración Top 10% de SKUs ({top_10_pct_count:,} SKUs): {pct_top_10:.2f}% de las líneas (Objetivo ~60%)")

    if 50.0 <= pct_top_10 <= 70.0:
        print("[PASA] Sesgo del catálogo verificado correctamente.")
        return True
    else:
        print("❌ [FALLA] Sesgo del catálogo fuera del rango esperado.")
        return False


def obtener_ultimos_tres_dias_habiles(year: int, month: int) -> set:
    _, num_days = calendar.monthrange(year, month)
    dias_habiles = []
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        if d.weekday() < 5:
            dias_habiles.append(d)
    return set(dias_habiles[-3:]) if len(dias_habiles) >= 3 else set(dias_habiles)


def verificar_estacionalidad_mensual() -> bool:
    print("\n--- 4. VERIFICACIÓN DE ESTACIONALIDAD MENSUAL (25% EN ÚLTIMOS 3 DÍAS HÁBILES) ---")
    ruta_ord = CSV_DIR / "orden_compra.csv"
    if not ruta_ord.exists():
        print("❌ orden_compra.csv no existe")
        return False

    cache_dias_habiles = {}
    ordenes_fin_mes = 0
    total_ordenes = 0

    with open(ruta_ord, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dt = datetime.fromisoformat(r["fecha_creacion"])
            key_mes = (dt.year, dt.month)
            if key_mes not in cache_dias_habiles:
                cache_dias_habiles[key_mes] = obtener_ultimos_tres_dias_habiles(dt.year, dt.month)

            if dt.date() in cache_dias_habiles[key_mes]:
                ordenes_fin_mes += 1
            total_ordenes += 1

    pct_fin_mes = (ordenes_fin_mes / total_ordenes) * 100
    print(f"  Órdenes en últimos 3 días hábiles del mes: {ordenes_fin_mes:,} / {total_ordenes:,} ({pct_fin_mes:.2f}%) (Objetivo ~25%)")

    if 18.0 <= pct_fin_mes <= 32.0:
        print("[PASA] Estacionalidad mensual verificada.")
        return True
    else:
        print("❌ [FALLA] Estacionalidad mensual fuera de rango.")
        return False


def verificar_estacionalidad_horaria() -> bool:
    print("\n--- 5. VERIFICACIÓN DE ESTACIONALIDAD HORARIA (PICO 8-11 AM Y VALLE NOCTURNO) ---")
    ruta_ord = CSV_DIR / "orden_compra.csv"
    if not ruta_ord.exists():
        print("❌ orden_compra.csv no existe")
        return False

    conteo_horas = Counter()
    total_ordenes = 0

    with open(ruta_ord, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dt = datetime.fromisoformat(r["fecha_creacion"])
            conteo_horas[dt.hour] += 1
            total_ordenes += 1

    ordenes_pico = sum(conteo_horas[h] for h in range(8, 11))
    ordenes_valle = sum(conteo_horas[h] for h in range(0, 5))

    pct_pico = (ordenes_pico / total_ordenes) * 100
    pct_valle = (ordenes_valle / total_ordenes) * 100

    print(f"  Concentración en Pico (08:00 AM - 11:00 AM): {ordenes_pico:,} órdenes ({pct_pico:.2f}%)")
    print(f"  Concentración en Valle Nocturno (00:00 AM - 05:00 AM): {ordenes_valle:,} órdenes ({pct_valle:.2f}%)")

    if pct_pico > 30.0 and pct_valle < 5.0:
        print("[PASA] Estacionalidad horaria verificada (Pico marcado y valle cercano a cero).")
        return True
    else:
        print("❌ [FALLA] Estacionalidad horaria fuera del comportamiento esperado.")
        return False


def verificar_checksum_determinismo() -> str:
    print("\n--- 6. CHECKSUM DE DETERMINISMO (SHA-256) ---")
    hasher = hashlib.sha256()
    archivos_clave = sorted([f.name for f in CSV_DIR.glob("*.csv")])

    for archivo in archivos_clave:
        ruta = CSV_DIR / archivo
        if ruta.exists():
            with open(ruta, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)

    digest = hasher.hexdigest()
    print(f"Checksum conjunto (semilla 42 sobre {len(archivos_clave)} archivos): {digest}")
    return digest


def verificar_los_8_casos_borde() -> bool:
    print("\n--- 7. IDENTIFICACIÓN RIGUROSA Y DETALLE DE LOS 8 CASOS BORDE ---")
    todo_pasa = True

    ruta_ord = CSV_DIR / "orden_compra.csv"
    ruta_lin = CSV_DIR / "linea_orden.csv"
    ruta_contratos = CSV_DIR / "contrato_suministro.csv"
    ruta_prov = CSV_DIR / "proveedor.csv"
    ruta_sku = CSV_DIR / "sku.csv"
    ruta_cat = CSV_DIR / "catalogo_negociado.csv"
    ruta_franjas = CSV_DIR / "franja_descargue.csv"

    # CB1
    muestra_lineas = []
    with open(ruta_lin, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["orden_id"]) == 1:
                muestra_lineas.append(r)

    if len(muestra_lineas) == 300:
        print("  ✓ Caso Borde 1: Orden ID 1 contiene exactamente 300 líneas de orden")
        print(f"    📌 Registro (Línea 1):   {dict(muestra_lineas[0])}")
        print(f"    📌 Registro (Línea 300): {dict(muestra_lineas[-1])}")
    else:
        print(f"  ❌ Caso Borde 1: Falló")
        todo_pasa = False

    # CB2
    reg_cb2 = None
    with open(ruta_contratos, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["proveedor_id"]) == 1 and r["fecha_fin"].startswith("2026-09-15") and r["estado"] == "VENCIDO":
                reg_cb2 = dict(r)
                break
    if reg_cb2:
        print("  ✓ Caso Borde 2: Contrato vencido ayer (2026-09-15) en Proveedor ID 1")
        print(f"    📌 Registro: {reg_cb2}")
    else:
        print("  ❌ Caso Borde 2: Falló")
        todo_pasa = False

    # CB3
    reg_cb3 = None
    with open(ruta_contratos, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["proveedor_id"]) == 2 and r["fecha_fin"].startswith("2026-09-16T12:00:00"):
                reg_cb3 = dict(r)
                break
    if reg_cb3:
        print("  ✓ Caso Borde 3: Contrato vence HOY a mediodía (2026-09-16 12:00:00) en Proveedor ID 2")
        print(f"    📌 Registro: {reg_cb3}")
    else:
        print("  ❌ Caso Borde 3: Falló")
        todo_pasa = False

    # CB4
    reg_cb4 = None
    with open(ruta_franjas, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["cedi_id"]) == 1 and r["fecha"] == "2026-09-16" and r["hora_inicio"] == "08:00:00":
                if (int(r["capacidad"]) - int(r["reservas_actuales"]) == 1) and r["estado"] == "DISPONIBLE":
                    reg_cb4 = dict(r)
                    break
    if reg_cb4:
        print("  ✓ Caso Borde 4: Última franja disponible en CEDI 1 (08:00 AM) con 1 cupo libre")
        print(f"    📌 Registro: {reg_cb4}")
    else:
        print("  ❌ Caso Borde 4: Falló")
        todo_pasa = False

    # CB5
    reg_cb5 = None
    with open(ruta_contratos, "r", encoding="utf-8") as f:
        prov_con_contrato = {int(r["proveedor_id"]) for r in csv.DictReader(f)}

    with open(ruta_prov, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p_id = int(r["proveedor_id"])
            if r["estado"] == "ACTIVO" and p_id not in prov_con_contrato:
                reg_cb5 = dict(r)
                break

    if reg_cb5:
        print(f"  ✓ Caso Borde 5: Proveedor ID {reg_cb5['proveedor_id']} verificado ACTIVO y sin contrato")
        print(f"    📌 Registro: {reg_cb5}")
    else:
        print("  ❌ Caso Borde 5: Falló")
        todo_pasa = False

    # CB6
    skus_alpina_map = {}
    with open(ruta_sku, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if "Alpina" in r["nombre"]:
                skus_alpina_map[int(r["sku_id"])] = dict(r)

    with open(ruta_cat, "r", encoding="utf-8") as f:
        skus_neg_p1 = {int(r["sku_id"]) for r in csv.DictReader(f) if int(r["proveedor_id"]) == 1}

    excluidos_ids = set(skus_alpina_map.keys()) - skus_neg_p1
    if len(skus_alpina_map) == 1000 and len(skus_neg_p1) == 997 and len(excluidos_ids) == 3:
        print("  ✓ Caso Borde 6: Proveedor 1 (Alpina) tiene 3 SKUs maestros excluidos del catálogo negociado")
        for s_id in sorted(list(excluidos_ids)):
            print(f"    📌 Registro SKU Maestro Excluido (id={s_id}): {skus_alpina_map[s_id]}")
    else:
        print("  ❌ Caso Borde 6: Falló")
        todo_pasa = False

    # CB7
    conteo_prov = Counter()
    with open(ruta_ord, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conteo_prov[int(r["proveedor_id"])] += 1

    top_prov_id, max_ordenes = conteo_prov.most_common(1)[0]
    reg_cb7 = None
    with open(ruta_prov, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["proveedor_id"]) == top_prov_id:
                reg_cb7 = dict(r)
                break

    if max_ordenes >= 5000:
        print(f"  ✓ Caso Borde 7: Proveedor Hot ID {top_prov_id} acumula {max_ordenes:,} órdenes (>= 5,000)")
        print(f"    📌 Registro Proveedor: {reg_cb7} | Total órdenes: {max_ordenes:,}")
    else:
        print(f"  ❌ Caso Borde 7: Falló")
        todo_pasa = False

    # CB8
    ordenes_p10_junio = 0
    with open(ruta_ord, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["proveedor_id"]) == 10 and r["fecha_creacion"].startswith("2026-06"):
                ordenes_p10_junio += 1

    reg_cb8 = None
    with open(ruta_prov, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["proveedor_id"]) == 10:
                reg_cb8 = dict(r)
                break

    if ordenes_p10_junio == 0:
        print("  ✓ Caso Borde 8: Proveedor ID 10 verificado con 0 órdenes en el mes de Junio 2026")
        print(f"    📌 Registro Proveedor: {reg_cb8} | Órdenes en 2026-06: {ordenes_p10_junio}")
    else:
        print(f"  ❌ Caso Borde 8: Falló")
        todo_pasa = False

    return todo_pasa


def main():
    print("==============================================")
    print("EJECUTANDO VERIFICACIÓN AUTOMÁTICA COMPLETA DE DATOS")
    print("==============================================")

    volumen_ok = verificar_volumetria()
    zipf_ok = verificar_distribucion_zipf()
    cat_ok = verificar_sesgo_catalogo()
    mes_ok = verificar_estacionalidad_mensual()
    hora_ok = verificar_estacionalidad_horaria()
    verificar_checksum_determinismo()
    casos_ok = verificar_los_8_casos_borde()

    print("\n==============================================")
    if volumen_ok and zipf_ok and cat_ok and mes_ok and hora_ok and casos_ok:
        print("RESULTADO GENERAL: VERIFICACIÓN PASÓ (100% EXIGENCIAS CUMPLIDAS)")
    else:
        print("RESULTADO GENERAL: FALLÓ (Inconsistencia detectada en datos)")
    print("==============================================\n")


if __name__ == "__main__":
    main()