#!/usr/bin/env python3
"""Generador de la carga del laboratorio (Entregable 3). Semilla fija.

Produce una secuencia de operaciones válidas que k6 recorre en orden
(lab/carga/k6/carga.js), así que misma semilla → mismas peticiones:

  - crear  (POST /ordenes): proveedor ACTIVO con contrato VIGENTE en la
    fecha de creación, y un (CEDI, fecha de entrega) con franjas DISPONIBLES.
    Nunca se asignan más órdenes a un (CEDI, fecha) que las que sus franjas
    admiten, partiendo del estado inicial de datos/csv/franja_descargue.csv
    (el que restaura `make lab-reset`).
  - listar (GET /proveedores/{id}/ordenes, Q5) y precio (GET /catalogo/precio, Q2).

Las fechas son explícitas (no dependen del día en que se corra). Solo lee los
CSV del Entregable 2 (no toca su generador ni la base).

    python3 lab/carga/generar_carga.py --semilla 42 --n 30000
"""
import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CSV = RAIZ / "datos" / "csv"
SALIDA = Path(__file__).resolve().parent / "datos"


def leer(nombre):
    with open(CSV / nombre, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def fecha_iso(texto):
    return datetime.fromisoformat(texto).astimezone(timezone.utc)


def cupos_por_cedi_fecha(desde: date, hasta: date):
    """Órdenes que admite cada (cedi, fecha). LogisticaService.reservar_franja
    incrementa TODAS las franjas DISPONIBLES del día con cupo, así que el día deja
    de reservar cuando se llena la franja con más cupo: max(capacidad - reservas)."""
    cupo = defaultdict(int)
    for r in leer("franja_descargue.csv"):
        dia = date.fromisoformat(r["fecha"])
        if r["estado"] != "DISPONIBLE" or not desde <= dia <= hasta:
            continue
        libre = int(r["capacidad"]) - int(r["reservas_actuales"])
        clave = (int(r["cedi_id"]), dia)
        cupo[clave] = max(cupo[clave], libre)
    return {k: v for k, v in sorted(cupo.items()) if v > 0}


def contratos_vigentes():
    activos = {int(r["proveedor_id"]) for r in leer("proveedor.csv") if r["estado"] == "ACTIVO"}
    return sorted((int(r["proveedor_id"]), fecha_iso(r["fecha_inicio"]), fecha_iso(r["fecha_fin"]))
                  for r in leer("contrato_suministro.csv")
                  if r["estado"] == "VIGENTE" and int(r["proveedor_id"]) in activos)


def catalogo_activo():
    return sorted((int(r["proveedor_id"]), int(r["sku_id"]), fecha_iso(r["fecha_inicio"]), fecha_iso(r["fecha_fin"]))
                  for r in leer("catalogo_negociado.csv") if r["estado"] == "ACTIVO")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--n", type=int, default=30000, help="operaciones totales")
    ap.add_argument("--mezcla", default="crear=0.7,listar=0.2,precio=0.1")
    ap.add_argument("--desde", default="2025-03-01", help="primera fecha de entrega")
    ap.add_argument("--hasta", default="2026-12-31", help="última fecha de entrega")
    ap.add_argument("--salida", type=Path, default=None)
    a = ap.parse_args()

    rng = random.Random(a.semilla)
    mezcla = {k: float(v) for k, v in (p.split("=") for p in a.mezcla.split(","))}
    ops = rng.choices(list(mezcla), weights=list(mezcla.values()), k=a.n)
    n_crear = ops.count("crear")

    cupos = cupos_por_cedi_fecha(date.fromisoformat(a.desde), date.fromisoformat(a.hasta))
    capacidad = sum(cupos.values())
    if n_crear > capacidad:
        raise SystemExit(f"{n_crear} órdenes superan el cupo de franjas ({capacidad}); baje --n o amplíe fechas")
    # Un "slot" por cada orden que admite un (cedi, fecha); barajados con la semilla.
    slots = [k for k, v in cupos.items() for _ in range(v)]
    rng.shuffle(slots)
    slots = slots[:n_crear]

    contratos = contratos_vigentes()
    catalogo = catalogo_activo()

    def proveedor_con_contrato(f_crea):
        for _ in range(200):
            prov, ini, fin = contratos[rng.randrange(len(contratos))]
            if ini <= f_crea <= fin:
                return prov
        raise SystemExit(f"sin proveedor con contrato vigente el {f_crea}")

    items = []
    i_slot = 0
    for op in ops:
        if op == "crear":
            cedi, dia = slots[i_slot]
            i_slot += 1
            f_ent = datetime(dia.year, dia.month, dia.day, 10, 0, tzinfo=timezone.utc)
            f_crea = f_ent - timedelta(days=2, hours=rng.randrange(0, 12))
            items.append({"op": "crear", "body": {
                "proveedor_id": proveedor_con_contrato(f_crea), "cedi_id": cedi,
                "total": round(rng.uniform(500, 15000), 2),
                "fecha_creacion": f_crea.isoformat(), "fecha_entrega_solicitada": f_ent.isoformat()}})
        elif op == "listar":
            prov, ini, fin = contratos[rng.randrange(len(contratos))]
            items.append({"op": "listar", "proveedor_id": prov, "offset": rng.choice([0, 0, 0, 50])})
        else:
            prov, sku, ini, fin = catalogo[rng.randrange(len(catalogo))]
            momento = ini + (fin - ini) * rng.random()
            items.append({"op": "precio", "proveedor_id": prov, "sku_id": sku,
                          "fecha": momento.replace(microsecond=0).isoformat()})

    SALIDA.mkdir(exist_ok=True)
    destino = a.salida or SALIDA / f"carga_s{a.semilla}_n{a.n}.json"
    texto = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    destino.write_text(texto, encoding="utf-8")
    meta = {"semilla": a.semilla, "n": a.n, "mezcla": mezcla, "por_op": {k: ops.count(k) for k in mezcla},
            "cupo_franjas": capacidad, "pares_cedi_fecha": len(cupos), "desde": a.desde, "hasta": a.hasta,
            "sha256": hashlib.sha256(texto.encode()).hexdigest(), "archivo": destino.name}
    destino.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
