#!/usr/bin/env python3
"""Momento 1 del Entregable 3: punto de partida reproducible derivado del Entregable 2.

    make momento1          (o: venv/bin/python lab/momento1/manifest.py [--salida RUTA])

Escribe evidencia/momento1/manifest.json con:
  - el volumen canónico del E2 (lab/momento1/referencia_e2.yaml, del informe) y las filas por
    entidad de los CSV y de la base actual, separando lo que agregaron el E2 (fase 4, orden_id
    600001–605000) y el laboratorio (API, orden_id >= 1000001);
  - semilla y parámetros del generador (datos/generar_datos.py);
  - checksum SHA-256 de los 11 CSV (mismo cálculo que datos/verificar_datos.py) y si coincide
    con el del E2; sha256 por archivo;
  - versión y configuración de PostgreSQL, índices presentes, commit de git y entorno.
No modifica la base ni los CSV. Sale con código 1 si el checksum o el volumen no coinciden.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import yaml

RAIZ = Path(__file__).resolve().parents[2]
CSV_DIR = RAIZ / "datos" / "csv"
REFERENCIA = Path(__file__).resolve().parent / "referencia_e2.yaml"
DB = {"dbname": "escalables", "user": "postgres", "password": "postgres", "host": "localhost", "port": 5432}

# tabla -> (archivo CSV, columna id para separar filas agregadas después de la carga)
ENTIDADES = {
    "proveedores.proveedor": ("proveedor.csv", None),
    "proveedores.contrato_suministro": ("contrato_suministro.csv", None),
    "catalogo.sku": ("sku.csv", None),
    "catalogo.catalogo_negociado": ("catalogo_negociado.csv", None),
    "logistica.cedi": ("cedi.csv", None),
    "logistica.franja_descargue": ("franja_descargue.csv", None),
    "ordenes.orden_compra": ("orden_compra.csv", "orden_id"),
    "ordenes.linea_orden": ("linea_orden.csv", "orden_id"),
    "auditoria.evento_auditoria": ("evento_auditoria.csv", None),
}
PARAMETROS_GENERADOR = ["SEED", "NUM_PROVEEDORES", "NUM_CONTRATOS", "PORCENTAJE_PROVEEDORES_CON_CONTRATO", "NUM_SKUS",
                        "NUM_ORDENES", "NUM_LINEAS", "NUM_FRANJAS", "NUM_AUDITORIAS", "ZIPF_S", "FECHA_INICIO",
                        "FECHA_FIN", "FECHA_REFERENCIA"]
AJUSTES_PG = ["server_version", "shared_buffers", "work_mem", "effective_cache_size", "max_connections",
              "synchronous_commit", "fsync", "wal_level", "random_page_cost", "jit", "autovacuum", "max_wal_size"]


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        while bloque := f.read(1 << 20):
            h.update(bloque)
    return h.hexdigest()


def checksum_conjunto() -> tuple[str, list[str]]:
    """Igual que datos/verificar_datos.py: sha256 de los CSV de datos/csv concatenados en orden."""
    nombres = sorted(f.name for f in CSV_DIR.glob("*.csv"))
    h = hashlib.sha256()
    for n in nombres:
        with (CSV_DIR / n).open("rb") as f:
            while bloque := f.read(1 << 20):
                h.update(bloque)
    return h.hexdigest(), nombres


def filas_csv(ruta: Path) -> int:
    with ruta.open("rb") as f:
        return sum(1 for _ in f) - 1


def parametros_generador() -> dict:
    sys.path.insert(0, str(RAIZ / "datos"))
    import generar_datos  # solo constantes; main() no se ejecuta
    return {p: str(getattr(generar_datos, p)) if not isinstance(getattr(generar_datos, p), (int, float))
            else getattr(generar_datos, p) for p in PARAMETROS_GENERADOR}


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True).stdout.strip()


def estado_bd(cur) -> dict:
    filas = {}
    for tabla, (_, col) in ENTIDADES.items():
        cur.execute(f"SELECT count(*) FROM {tabla}")
        total = cur.fetchone()[0]
        d = {"total": total}
        if col:
            cur.execute(f"SELECT count(*) FILTER (WHERE {col} BETWEEN 600001 AND 999999),"
                        f"       count(*) FILTER (WHERE {col} >= 1000001) FROM {tabla}")
            fase4, lab = cur.fetchone()
            d.update({"fase4_e2": fase4, "lab_api": lab, "canonicas": total - fase4 - lab})
        else:
            d["canonicas"] = total
        filas[tabla] = d
    cur.execute("SELECT sum(reservas_actuales), count(*) FILTER (WHERE estado = 'COMPLETA') FROM logistica.franja_descargue")
    reservas, completas = cur.fetchone()
    cur.execute("SELECT name, setting || coalesce(unit, '') FROM pg_settings WHERE name = ANY(%s)", (AJUSTES_PG,))
    ajustes = dict(cur.fetchall())
    cur.execute("SELECT version()")
    version = cur.fetchone()[0]
    cur.execute("""SELECT schemaname || '.' || indexname FROM pg_indexes
                   WHERE schemaname IN ('proveedores','catalogo','logistica','ordenes','auditoria')
                     AND indexname LIKE 'idx%' ORDER BY 1""")
    indices = [r[0] for r in cur.fetchall()]
    return {"filas": filas, "franjas": {"reservas_actuales_total": int(reservas), "completas": completas},
            "postgres": {"version": version, "ajustes": ajustes}, "indices_secundarios": indices}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default=str(RAIZ / "evidencia" / "momento1" / "manifest.json"))
    args = ap.parse_args()
    ref = yaml.safe_load(REFERENCIA.read_text(encoding="utf-8"))

    digest, nombres = checksum_conjunto()
    archivos = {n: {"sha256": sha256_archivo(CSV_DIR / n), "filas": filas_csv(CSV_DIR / n),
                    "bytes": (CSV_DIR / n).stat().st_size} for n in nombres}
    with psycopg2.connect(**DB) as conn, conn.cursor() as cur:
        bd = estado_bd(cur)

    entidades, problemas = {}, []
    for tabla, (archivo, _) in ENTIDADES.items():
        e2, csv_n, bd_n = ref["filas"][tabla], archivos[archivo]["filas"], bd["filas"][tabla]["canonicas"]
        entidades[tabla] = {"e2_informe": e2, "csv": csv_n, "bd_canonicas": bd_n,
                            "bd_total": bd["filas"][tabla]["total"], "coincide": e2 == csv_n == bd_n}
        if not entidades[tabla]["coincide"]:
            problemas.append(f"{tabla}: E2={e2} CSV={csv_n} BD={bd_n}")
    if digest != ref["checksum_sha256"]:
        problemas.append(f"checksum {digest} != E2 {ref['checksum_sha256']}")

    manifest = {
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "comando": "make momento1",
        "referencia_e2": {"fuente": ref["fuente"], "archivo": str(REFERENCIA.relative_to(RAIZ))},
        "semilla": ref["semilla"],
        "generador": {"script": "datos/generar_datos.py --seed 42", "parametros": parametros_generador()},
        "checksum": {"sha256_11_csv": digest, "e2_informe": ref["checksum_sha256"],
                     "coincide": digest == ref["checksum_sha256"], "archivos": nombres,
                     "metodo": "sha256 de datos/csv/*.csv concatenados en orden alfabético (datos/verificar_datos.py)"},
        "archivos_csv": archivos,
        "entidades": entidades,
        "total_filas": {"e2_informe": ref["filas"]["total"],
                        "bd_canonicas": sum(v["bd_canonicas"] for v in entidades.values())},
        "bd": {k: v for k, v in bd.items() if k != "filas"} | {"filas_agregadas": {
            t: {k: v for k, v in d.items() if k in ("fase4_e2", "lab_api")} for t, d in bd["filas"].items() if "lab_api" in d}},
        "reproducir": ["make datos   # o, sin regenerar los CSV versionados: make cargar",
                       "make momento1", "make linea-base"],
        "git": {"commit": git("rev-parse", "HEAD"), "rama": git("rev-parse", "--abbrev-ref", "HEAD"),
                "cambios_sin_commit_en_datos": git("status", "--porcelain", "datos", "modelo-fisico.sql") or None},
        "entorno": {"python": platform.python_version(), "so": platform.platform(),
                    "docker": subprocess.run(["docker", "version", "-f", "{{.Server.Version}}"], capture_output=True,
                                             text=True).stdout.strip()},
        "problemas": problemas,
    }
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{salida.relative_to(RAIZ) if salida.is_relative_to(RAIZ) else salida}")
    print(f"checksum: {digest} ({'= E2' if manifest['checksum']['coincide'] else 'DISTINTO del E2'})")
    for tabla, e in entidades.items():
        print(f"  {'✓' if e['coincide'] else '✗'} {tabla:34} E2 {e['e2_informe']:>9,}  CSV {e['csv']:>9,}  "
              f"BD {e['bd_canonicas']:>9,} (total {e['bd_total']:,})")
    for p in problemas:
        print(f"PROBLEMA: {p}")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
