#!/usr/bin/env python3
"""Línea base del Entregable 3 con las MISMAS cargas del Entregable 2 (Momento 1).

    make linea-base                                   # recarga la base, mide todo y arma la tabla
    venv/bin/python lab/momento1/linea_base.py todo --recargar
    venv/bin/python lab/momento1/linea_base.py fase4 --salida DIR [--restaurar-franjas] [--desglose]
    venv/bin/python lab/momento1/linea_base.py tabla DIR

Reutiliza sin modificarlos los scripts del E2 (datos/medir_q*.py, datos/crear_indice_q*.py,
datos/ejecutar_fase4_modulith.py y datos/cargar_datos.sh): solo redirige su evidencia a
evidencia/linea_base/<UTC>/, así los CSV del E2 en datos/resultados/ no se tocan.
  - consultas: misma secuencia que `make medir` (Q1–Q3 base; Q4 y Q5 antes del índice, se crea
    el índice, después del índice), 100 ejecuciones por escenario frío/caliente;
  - fase4: las mismas 5.000 órdenes de datos/csv/ordenes_fase4_5k.csv (no se regeneran: el
    generador no tiene semilla) por la ruta del modulith; throughput = exitosas / duración, el
    criterio del E2;
  - tabla: valor E2 (del informe, lab/momento1/referencia_e2.yaml), objetivo E3 = 0,90 × E2 y
    valor E3, con el mismo método de percentil que el informe (ver referencia_e2.yaml).
"""
import argparse
import contextlib
import csv
import importlib.util
import io
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import yaml

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "datos"
REFERENCIA = Path(__file__).resolve().parent / "referencia_e2.yaml"
DB = {"dbname": "escalables", "user": "postgres", "password": "postgres", "host": "localhost", "port": 5432}
CSV_FASE4 = DATOS / "csv" / "ordenes_fase4_5k.csv"
INDICES_Q4_Q5 = ["idx_orden_proveedor_confirmada", "idx_linea_orden_id", "idx_orden_proveedor_fecha"]
# Misma secuencia que el target `medir` del Makefile: (script, BENCHMARK_ETIQUETA)
SECUENCIA_MEDIR = [("medir_q1.py", "base"), ("medir_q2.py", "base"), ("medir_q3.py", "base"),
                   ("medir_q4.py", "antes_indice"), ("crear_indice_q4.py", None), ("medir_q4.py", "despues_indice"),
                   ("medir_q5.py", "antes_indice"), ("crear_indice_q5.py", None), ("medir_q5.py", "despues_indice")]


def ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cargar_modulo(nombre: str):
    """Importa un script de datos/ sin ejecutar su main()."""
    if str(DATOS) not in sys.path:
        sys.path.insert(0, str(DATOS))
    spec = importlib.util.spec_from_file_location(f"e2_{Path(nombre).stem}", DATOS / nombre)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def percentiles(v: list[float], metodo: str) -> dict:
    q = statistics.quantiles(v, n=100, method=metodo)
    return {"p50": round(q[49], 3), "p95": round(q[94], 3), "p99": round(q[98], 3)}


def indices_presentes() -> list[str]:
    with psycopg2.connect(**DB) as conn, conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE indexname = ANY(%s)", (INDICES_Q4_Q5,))
        return sorted(r[0] for r in cur.fetchall())


# --------------------------------------------------------------------- recarga
def recargar(salida: Path):
    """datos/cargar_datos.sh (modelo-fisico.sql + COPY + índices base + ANALYZE) con su reporte
    de carga en `salida` en vez de datos/resultados/."""
    print("recargando la base desde datos/csv (datos/cargar_datos.sh)…", flush=True)
    with (salida / "cargar.log").open("w", encoding="utf-8") as log:
        subprocess.run(["./datos/cargar_datos.sh"], cwd=RAIZ, check=True, stdout=log, stderr=subprocess.STDOUT,
                       env={**os.environ, "RESULTADOS_DIR": str(salida)})


# --------------------------------------------------------------------- consultas
def consultas(salida: Path):
    presentes = indices_presentes()
    if presentes:
        sys.exit(f"Los índices de Q4/Q5 ya existen ({presentes}): la medición 'antes del índice' no sería la del E2. "
                 "Recargue la base (make linea-base, o linea_base.py todo --recargar).")
    registrar = cargar_modulo("registrar_evidencia.py")
    sys.modules["registrar_evidencia"] = registrar
    registrar.RESULTADOS_DIR = salida          # los medir_q*.py escriben aquí, no en datos/resultados/
    with (salida / "consultas.log").open("w", encoding="utf-8") as log:
        for script, etiqueta in SECUENCIA_MEDIR:
            print(f"  {script} {etiqueta or ''}", flush=True)
            if etiqueta:
                os.environ["BENCHMARK_ETIQUETA"] = etiqueta
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cargar_modulo(script).main()
            log.write(f"===== {script} BENCHMARK_ETIQUETA={etiqueta}\n{buf.getvalue()}\n")


# --------------------------------------------------------------------- fase 4
def estado_franjas(cur) -> dict:
    cur.execute("""SELECT sum(reservas_actuales), count(*) FILTER (WHERE estado = 'COMPLETA'),
                          count(*) FILTER (WHERE fecha BETWEEN '2026-09-02' AND '2026-09-14' AND estado = 'DISPONIBLE'
                                           AND reservas_actuales < capacidad)
                     FROM logistica.franja_descargue""")
    r, c, d = cur.fetchone()
    cur.execute("SELECT n_live_tup, n_dead_tup FROM pg_stat_user_tables WHERE relid = 'logistica.franja_descargue'::regclass")
    vivas, muertas = cur.fetchone()
    cur.execute("SELECT count(*) FROM ordenes.orden_compra")
    return {"reservas_actuales_total": int(r), "franjas_completas": c, "franjas_disponibles_sep_2_14": d,
            "franja_tuplas_vivas": vivas, "franja_tuplas_muertas": muertas, "orden_compra_filas": cur.fetchone()[0]}


def restaurar_franjas(cur):
    """Devuelve las franjas al estado de datos/csv/franja_descargue.csv (como lab/carga/reset.sql)."""
    cur.execute("CREATE TEMP TABLE franja_csv (LIKE logistica.franja_descargue) ON COMMIT DROP")
    with (DATOS / "csv" / "franja_descargue.csv").open(encoding="utf-8") as f:
        cur.copy_expert("COPY franja_csv FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute("""UPDATE logistica.franja_descargue f SET reservas_actuales = c.reservas_actuales, estado = c.estado
                     FROM franja_csv c WHERE f.franja_id = c.franja_id
                      AND (f.reservas_actuales <> c.reservas_actuales OR f.estado <> c.estado)""")
    return cur.rowcount


def fase4(salida: Path, restaurar: bool = False, desglose: bool = False, etiqueta: str = "fase4"):
    mod = cargar_modulo("ejecutar_fase4_modulith.py")
    mod.CSV_OPERACIONES = salida / f"{etiqueta}_operaciones.csv"
    mod.CSV_RESUMEN = salida / f"{etiqueta}_resumen.csv"
    mod.RESULTADOS_DIR = salida
    with psycopg2.connect(**DB) as conn, conn.cursor() as cur:
        restauradas = restaurar_franjas(cur) if restaurar else None
        conn.commit()
        antes = estado_franjas(cur)

    pasos = []
    if desglose:   # tiempo por módulo y filas que toca el UPDATE de Q3, por orden (solo diagnóstico)
        actual = {}

        def medir(clase, metodo, clave, filas=False):
            orig = getattr(clase, metodo)

            def envuelto(self, *a, **kw):
                t = time.perf_counter()
                try:
                    return orig(self, *a, **kw)
                finally:
                    actual[clave] = (time.perf_counter() - t) * 1000
                    if filas:
                        actual["filas_q3"] = self.cursor.rowcount
            setattr(clase, metodo, envuelto)
        medir(mod.ProveedorService, "validar_contrato_vigente", "q1_ms")
        medir(mod.CatalogoService, "validar_sku_y_obtener_precio", "q2_ms")
        medir(mod.LogisticaService, "reservar_franja", "q3_ms", filas=True)
        orig_crear = mod.OrdenesService.crear_orden_transaccional

        def crear(self, dto):
            actual.clear()
            t = time.perf_counter()
            try:
                return orig_crear(self, dto)
            finally:
                actual["orden_id"] = dto[0]
                actual["crear_ms"] = (time.perf_counter() - t) * 1000
                pasos.append(dict(actual))
        mod.OrdenesService.crear_orden_transaccional = crear

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod.main()
    (salida / f"{etiqueta}.log").write_text(buf.getvalue(), encoding="utf-8")

    with psycopg2.connect(**DB) as conn, conn.cursor() as cur:
        despues = estado_franjas(cur)
    with mod.CSV_OPERACIONES.open(encoding="utf-8") as f:
        ops = list(csv.DictReader(f))
    motivos = Counter("ok" if not o["error"] else "sin_contrato_vigente" if "sin contrato vigente" in o["error"]
                      else "check_estado_orden" if "chk_orden_estado" in o["error"] else "otro" for o in ops)
    with mod.CSV_RESUMEN.open(encoding="utf-8") as f:
        res = next(csv.DictReader(f))
    lat = [float(o["latencia_ms"]) for o in ops]
    info = {"etiqueta": etiqueta, "medido_utc": ahora_utc(), "csv_ordenes": str(CSV_FASE4.relative_to(RAIZ)),
            "restaurar_franjas": restaurar, "franjas_restauradas": restauradas, "desglose": desglose,
            "ordenes": len(ops), "exitosas": int(res["exitosas"]), "rechazadas": int(res["rechazadas"]),
            "motivos": dict(motivos), "duracion_s": float(res["duracion_s"]),
            "throughput_req_s": round(float(res["throughput_req_s"]), 2),
            "costo_medio_ms": round(float(res["duracion_s"]) * 1000 / len(ops), 4),
            "latencia_orden_ms": percentiles(lat, "inclusive"), "estado_antes": antes, "estado_despues": despues}
    if pasos:
        with (salida / f"{etiqueta}_desglose.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["orden_id", "q1_ms", "q2_ms", "q3_ms", "filas_q3", "crear_ms"])
            w.writeheader()
            w.writerows(pasos)
        for k in ("q1_ms", "q2_ms", "q3_ms", "crear_ms"):
            info.setdefault("desglose_medias_ms", {})[k] = round(statistics.mean(p[k] for p in pasos if k in p), 4)
        info["filas_q3_media"] = round(statistics.mean(p["filas_q3"] for p in pasos if "filas_q3" in p), 2)
    (salida / f"{etiqueta}.json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  {etiqueta}: {info['exitosas']} exitosas / {info['duracion_s']:.4f} s = {info['throughput_req_s']} req/s "
          f"(motivos {dict(motivos)})", flush=True)
    return info


# --------------------------------------------------------------------- tabla
def tabla(salida: Path) -> dict:
    ref = yaml.safe_load(REFERENCIA.read_text(encoding="utf-8"))
    filas, md = [], []
    for qid, r in ref["consultas"].items():
        consulta = qid.split("_")[0]
        ruta = salida / f"{consulta.lower()}_{r['fase']}.csv"
        if not ruta.exists():
            continue
        datos = defaultdict(list)
        with ruta.open(encoding="utf-8") as f:
            for x in csv.DictReader(f):
                datos[x["escenario"]].append(float(x["latencia_ms"]))
        for esc in ("frio", "caliente"):
            e3 = percentiles(datos[esc], r["metodo"])
            otro = percentiles(datos[esc], "exclusive" if r["metodo"] == "inclusive" else "inclusive")
            con_objetivo = r["fase"] != "antes_indice"
            for m in ("p50", "p95", "p99"):
                e2 = r[esc][m]
                obj = round(0.9 * e2, 3) if con_objetivo else None
                filas.append({"consulta": consulta, "fase": r["fase"], "escenario": esc, "metrica": m, "metodo": r["metodo"],
                              "e2": e2, "objetivo_e3": obj, "e3": e3[m], "e3_otro_metodo": otro[m],
                              "e3_sobre_e2": round(e3[m] / e2, 2), "cumple": (e3[m] <= obj) if obj else None})
    f4 = json.loads((salida / "fase4.json").read_text(encoding="utf-8")) if (salida / "fase4.json").exists() else None
    r4 = ref["fase4"]
    fase4_fila = None
    if f4:
        fase4_fila = {"e2_req_s": r4["throughput_req_s"], "e2_duracion_s": r4["duracion_s"],
                      "objetivo_duracion_s": round(0.9 * r4["duracion_s"], 4),
                      "objetivo_req_s": round(r4["throughput_req_s"] / 0.9, 2),
                      "e3_req_s": f4["throughput_req_s"], "e3_duracion_s": f4["duracion_s"],
                      "e3_exitosas": f4["exitosas"], "e2_exitosas": r4["exitosas"],
                      "cumple": f4["duracion_s"] <= 0.9 * r4["duracion_s"]}
    resumen = {"generado_utc": ahora_utc(), "directorio": str(salida.relative_to(RAIZ)), "consultas": filas,
               "fase4": fase4_fila, "referencia": str(REFERENCIA.relative_to(RAIZ))}
    (salida / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md.append(f"# Línea base E3 vs. E2 — `{salida.name}`\n")
    md.append("Referencia: informe del E2 (`lab/momento1/referencia_e2.yaml`). Objetivo E3 = 0,90 × E2. "
              "Mismo método de percentil que el informe en cada fila (Q1 exclusive; Q2–Q5 inclusive); "
              "la columna «otro método» es la misma medición con el otro.\n")
    md.append("| Consulta | Fase | Escenario | Métrica | E2 (ms) | Objetivo E3 (ms) | E3 (ms) | E3/E2 | Cumple | Otro método (ms) |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for x in filas:
        cumple = "—" if x["cumple"] is None else ("sí" if x["cumple"] else "**no**")
        md.append(f"| {x['consulta']} | {x['fase']} | {x['escenario']} | {x['metrica']} | {x['e2']} | "
                  f"{x['objetivo_e3'] if x['objetivo_e3'] is not None else '—'} | {x['e3']} | {x['e3_sobre_e2']} | "
                  f"{cumple} | {x['e3_otro_metodo']} |")
    if fase4_fila:
        x = fase4_fila
        md.append("\n## Fase 4 (5.000 órdenes, ruta del modulith; req/s = exitosas / duración)\n")
        md.append("| | E2 | Objetivo E3 | E3 | Cumple |\n|---|---|---|---|---|")
        md.append(f"| Duración (s) | {x['e2_duracion_s']} | ≤ {x['objetivo_duracion_s']} | {x['e3_duracion_s']:.4f} | "
                  f"{'sí' if x['cumple'] else '**no**'} |")
        md.append(f"| Throughput (req/s) | {x['e2_req_s']} | ≥ {x['objetivo_req_s']} | {x['e3_req_s']} | |")
        md.append(f"| Exitosas | {x['e2_exitosas']} | | {x['e3_exitosas']} | |")
    (salida / "tabla.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print((salida / "tabla.md").relative_to(RAIZ))
    return resumen


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("todo")
    t.add_argument("--recargar", action="store_true", help="recarga la base desde datos/csv antes de medir")
    t.add_argument("--salida")
    c = sub.add_parser("consultas")
    c.add_argument("--salida", required=True)
    f = sub.add_parser("fase4")
    f.add_argument("--salida", required=True)
    f.add_argument("--etiqueta", default="fase4")
    f.add_argument("--restaurar-franjas", action="store_true")
    f.add_argument("--desglose", action="store_true")
    tb = sub.add_parser("tabla")
    tb.add_argument("salida")
    a = ap.parse_args()

    if a.cmd == "tabla":
        tabla(Path(a.salida).resolve())
        return
    salida = Path(a.salida).resolve() if a.salida else \
        RAIZ / "evidencia" / "linea_base" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    salida.mkdir(parents=True, exist_ok=True)
    if a.cmd == "consultas":
        consultas(salida)
    elif a.cmd == "fase4":
        fase4(salida, a.restaurar_franjas, a.desglose, a.etiqueta)
    else:
        print(f"línea base en {salida.relative_to(RAIZ)}", flush=True)
        if a.recargar:
            recargar(salida)
        subprocess.run([sys.executable, str(Path(__file__).with_name("manifest.py")), "--salida",
                        str(salida / "manifest.json")], check=True)
        consultas(salida)
        fase4(salida)
        tabla(salida)


if __name__ == "__main__":
    main()
