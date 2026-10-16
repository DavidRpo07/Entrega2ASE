#!/usr/bin/env python3
"""Compara qué peticiones afectó una falla en dos corridas (condición "reproducible").

    python3 lab/experimentos/comparar_inyecciones.py <RUN_1> <RUN_2> [--falla A1]

Cada petición de k6 lleva su clave (X-Clave-Carga = índice de la carga). Se comparan las claves
expuestas a la falla en ambas corridas, excluyendo `--margen` segundos tras la activación y tras el
kill switch: en ese intervalo cada proceso todavía puede no haber releído faults.yaml
(FAULTS_RECARGA_S), así que ahí la decisión depende del tiempo, no de la clave.
"""
import argparse
import csv
import gzip
import json
from datetime import datetime
from pathlib import Path

EVID = Path(__file__).resolve().parents[2] / "evidencia"


def ts_utc(texto):
    return datetime.fromisoformat(texto).timestamp()


def cargar(run, falla, margen):
    manifest = json.loads((EVID / "experiments" / run / "manifest.json").read_text(encoding="utf-8"))
    on, kill = ts_utc(manifest["marcas_utc"]["falla_on"]), ts_utc(manifest["marcas_utc"]["kill"])
    with gzip.open(EVID / "metrics" / run / "peticiones.csv.gz", "rt", encoding="utf-8") as f:
        expuestas = {r["clave"] for r in csv.DictReader(f) if on + margen <= float(r["ts"]) < kill}
    # una petición que salió justo antes del kill switch puede llegar después: se excluye el margen tras él
    with gzip.open(EVID / "metrics" / run / "peticiones.csv.gz", "rt", encoding="utf-8") as f:
        expuestas -= {r["clave"] for r in csv.DictReader(f) if kill - margen <= float(r["ts"]) < kill + margen}
    with (EVID / "logs" / run / "inyecciones.csv").open(encoding="utf-8") as f:
        afectadas = {r["clave"] for r in csv.DictReader(f) if r["falla_id"] == falla and r["clave"]}
    return expuestas, afectadas, manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run1")
    ap.add_argument("run2")
    ap.add_argument("--falla", default=None)
    ap.add_argument("--margen", type=float, default=0.5, help="segundos excluidos tras activación y kill switch")
    a = ap.parse_args()
    falla = a.falla or a.run1.split("_")[0].replace("PRUEBA-", "")
    e1, af1, m1 = cargar(a.run1, falla, a.margen)
    e2, af2, m2 = cargar(a.run2, falla, a.margen)
    print(f"margen excluido tras activación y kill switch: {a.margen} s")
    comunes = e1 & e2
    d1, d2 = af1 & comunes, af2 & comunes
    print(f"falla {falla}: configuración idéntica = {m1['falla_aplicada'] | {'inicio_utc': None} == m2['falla_aplicada'] | {'inicio_utc': None}}")
    print(f"claves expuestas: corrida 1 = {len(e1)}, corrida 2 = {len(e2)}, en ambas = {len(comunes)}")
    print(f"afectadas entre las comunes: corrida 1 = {len(d1)}, corrida 2 = {len(d2)}")
    print(f"mismas peticiones afectadas: {d1 == d2}  (solo en 1: {len(d1 - d2)}, solo en 2: {len(d2 - d1)})")
    print(f"muestra de claves afectadas en ambas: {sorted(d1 & d2, key=lambda c: int(c[1:]))[:12]}")
    raise SystemExit(0 if d1 == d2 else 1)


if __name__ == "__main__":
    main()
