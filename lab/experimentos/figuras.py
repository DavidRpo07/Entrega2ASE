#!/usr/bin/env python3
"""Figuras del informe (Entregable 3), una por experimento, desde la evidencia ya guardada.

    venv/bin/python lab/experimentos/figuras.py [A1 B2 ...]      # o:  make figuras

Cada figura muestra, en el tiempo (minutos desde que se activa la falla):
  - p95 y p99 de POST /ordenes por ventanas de 10 s, lado cliente (k6, peticiones.csv.gz: lo
    mismo que usa el resumen de cada corrida), con las líneas del SLO;
  - % de errores (5xx o sin respuesta, más la carga que k6 no pudo enviar) en una ventana móvil
    de 60 s evaluada cada 10 s, como se define el SLO, con su línea del 1 %;
  - para C2 y D2, el lag del outbox (prometheus/outbox_lag_s.csv) con su SLO de 10 s.
Las fases baseline / falla / recuperación van sombreadas. Si el experimento tiene corrida
corregida (fase 4), antes y después van en la misma figura; O1 compara trazas on vs. off.

Solo lee evidencia/; escribe evidencia/figuras/<ID>.png.
"""
import argparse
import csv
import gzip
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
EVID = RAIZ / "evidencia"
DEFS = Path(__file__).resolve().parent / "definiciones"

# Corridas válidas (ver lab/NOTAS_SESION.md). Por experimento: (corrida, etiqueta), la primera es la referencia.
CORRIDAS = {
    "A1": [("A1_20261016T205354Z", "antes"), ("A1-corr_20261017T002059Z", "después (catálogo: timeout + breaker)")],
    "A2": [("A2_20261016T211219Z", "antes"), ("A2-corr_20261017T005544Z", "después (bulkhead)")],
    "B1": [("B1_20261016T222927Z", "antes"), ("B1-corr_20261017T010803Z", "después (bulkhead)")],
    "B2": [("B2_20261016T224212Z", "antes"), ("B2-corr_20261017T012023Z", "después (bulkhead)")],
    "C1": [("C1_20261016T225444Z", "corrida")],
    "C2": [("C2_20261016T230717Z", "corrida")],
    "D1": [("D1_20261016T232015Z", "corrida")],
    "D2": [("D2_20261016T233309Z", "antes"), ("D2-corr_20261017T013242Z", "después (worker: retry + breaker)")],
    "O1": [("O1-trazas-on_20261017T014501Z", "trazas on"), ("O1-trazas-off_20261017T015738Z", "TRAZAS=off")],
}
CON_LAG = {"C2", "D2"}
COLORES = ["#c0392b", "#2471a3"]
# La segunda serie va discontinua y algo transparente: si coincide con la primera (p. ej. 0 % de errores
# o el mismo lag en D2), ambas se siguen viendo.
TRAZOS = [{"ls": "-", "alpha": 1.0}, {"ls": (0, (5, 3)), "alpha": 0.85}]
BIN_S, VENTANA_S = 10, 60
LEYENDA = {"fontsize": 8, "loc": "upper left", "bbox_to_anchor": (1.01, 1), "borderaxespad": 0}


def ts(texto):
    return datetime.fromisoformat(texto).timestamp()


def cargar(run):
    m = json.loads((EVID / "results" / run / "resumen.json").read_text(encoding="utf-8"))["marcas_utc"]
    marcas = {k: ts(v) for k, v in m.items()}
    with gzip.open(EVID / "metrics" / run / "peticiones.csv.gz", "rt", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    t = np.array([float(r["ts"]) for r in filas])
    ms = np.array([float(r["ms"]) for r in filas])
    st = np.array([int(r["status"]) for r in filas])
    post = np.array([r["op"] == "crear" for r in filas])
    no_env = np.array([])
    ruta = EVID / "metrics" / run / "no_enviadas.csv.gz"
    if ruta.exists():   # las primeras corridas (A1, A2) son anteriores a este archivo; no tuvieron no enviadas
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            no_env = np.array([float(r["ts"]) for r in csv.DictReader(f)])
    lag = []
    ruta = EVID / "metrics" / run / "prometheus" / "outbox_lag_s.csv"
    if ruta.exists():
        with ruta.open(encoding="utf-8") as f:
            lag = [(float(r["ts"]), float(r["valor"])) for r in csv.DictReader(f) if r["valor"] not in ("", "NaN")]
    return {"marcas": marcas, "t": t, "ms": ms, "error": (st == 0) | (st >= 500), "post": post,
            "no_env": no_env, "lag": lag}


def series(c):
    """Todo en minutos relativos a falla_on."""
    t0, ini, fin = c["marcas"]["falla_on"], c["marcas"]["baseline"], c["marcas"]["fin"]
    bordes = np.arange(ini, fin + BIN_S, BIN_S)
    tp, mp = c["t"][c["post"]], c["ms"][c["post"]]
    idx = np.digitize(tp, bordes) - 1
    p95, p99 = [], []
    for i in range(len(bordes) - 1):
        v = mp[idx == i]
        p95.append(np.percentile(v, 95) if len(v) else np.nan)
        p99.append(np.percentile(v, 99) if len(v) else np.nan)
    centros = (bordes[:-1] + BIN_S / 2 - t0) / 60
    # errores: ventana móvil [u - 60 s, u) sobre la carga planificada (enviadas + no enviadas)
    fins = np.arange(ini + VENTANA_S, fin + BIN_S, BIN_S)
    t_s, t_e = np.sort(c["t"]), np.sort(c["t"][c["error"]])
    ne = np.sort(c["no_env"])
    cuenta = lambda a, u: np.searchsorted(a, u) - np.searchsorted(a, u - VENTANA_S)
    n = cuenta(t_s, fins) + cuenta(ne, fins)
    err = np.where(n > 0, 100 * (cuenta(t_e, fins) + cuenta(ne, fins)) / np.maximum(n, 1), np.nan)
    lag = np.array([((x - t0) / 60, v) for x, v in c["lag"] if ini - 30 <= x <= fin + 15]).reshape(-1, 2)
    return {"x": centros, "p95": np.array(p95), "p99": np.array(p99), "x_err": (fins - t0) / 60, "err": err, "lag": lag}


def sombrear(ax, m):
    t0 = m["falla_on"]
    rel = lambda k: (m[k] - t0) / 60
    ax.axvspan(rel("baseline"), 0, color="#7f8c8d", alpha=0.08, lw=0)
    ax.axvspan(0, rel("kill"), color="#e74c3c", alpha=0.10, lw=0)
    ax.axvspan(rel("kill"), rel("fin"), color="#27ae60", alpha=0.10, lw=0)
    ax.set_xlim(rel("baseline"), rel("fin"))


def figura(exp_id, slo):
    corridas = CORRIDAS[exp_id]
    defin = yaml.safe_load((DEFS / f"{exp_id}.yaml").read_text(encoding="utf-8"))
    datos = [(run, etiqueta, cargar(run)) for run, etiqueta in corridas]
    filas = 3 if exp_id in CON_LAG else 2
    fig, axs = plt.subplots(filas, 1, figsize=(13, 3.2 * filas + 0.9), sharex=True,
                            gridspec_kw={"height_ratios": [1.4] + [1] * (filas - 1)})
    ref = datos[0][2]["marcas"]
    for ax in axs:
        sombrear(ax, ref)
        ax.grid(alpha=0.3)
    ax_lat, ax_err = axs[0], axs[1]
    calculadas = [series(c) for _, _, c in datos]
    # Serie de errores en 0 en toda la corrida: línea más gruesa (si no, queda pegada al eje).
    en_cero = [bool(np.nanmax(s["err"], initial=0) == 0) for s in calculadas]
    for i, ((run, etiqueta, c), s) in enumerate(zip(datos, calculadas)):
        col, trazo = COLORES[i % len(COLORES)], TRAZOS[i % len(TRAZOS)]
        nombre = etiqueta if len(datos) > 1 else run
        ax_lat.plot(s["x"], s["p95"], color=col, lw=1.6, alpha=trazo["alpha"], label=f"p95 · {nombre}")
        ax_lat.plot(s["x"], s["p99"], color=col, lw=1.0, ls=":", alpha=trazo["alpha"], label=f"p99 · {nombre}")
        ax_err.plot(s["x_err"], s["err"], color=col, lw=3.0 if en_cero[i] else 1.6, **trazo, label=nombre)
        if exp_id in CON_LAG and len(s["lag"]):
            axs[2].plot(s["lag"][:, 0], s["lag"][:, 1], color=col, lw=1.6, **trazo, label=nombre)
    ax_lat.axhline(slo["p95_post_ms"], color="#e67e22", ls="--", lw=1, label=f"SLO p95 {slo['p95_post_ms']} ms")
    ax_lat.axhline(slo["p99_post_ms"], color="#8e44ad", ls="--", lw=1, label=f"SLO p99 {slo['p99_post_ms']} ms")
    ax_lat.set_yscale("log")
    ax_lat.set_ylabel("POST /ordenes (ms, log)")
    ax_lat.legend(**LEYENDA)
    ax_err.axhline(slo["errores_pct"], color="#e67e22", ls="--", lw=1, label=f"SLO {slo['errores_pct']:g} %")
    ax_err.set_ylabel(f"% errores (ventana {VENTANA_S} s)")
    if any(en_cero):
        tope = max([slo["errores_pct"]] + [np.nanmax(s["err"]) for s in calculadas]) * 1.1
        ax_err.set_ylim(-0.05 * tope, tope)   # la línea en 0 queda separada del eje
        quienes = [e for (_, e, _), z in zip(datos, en_cero) if z]
        if len(datos) == 1:
            texto = "0 % de errores en toda la corrida"
        elif all(en_cero):
            texto = f"0 % de errores en toda la corrida ({' y '.join(e.split(' (')[0] for e in quienes)})"
        else:
            texto = "; ".join(f"{e.split(' (')[0]}: 0 % de errores en toda la corrida" for e in quienes)
        # Todo en 0: centrado. Si alguna serie tiene errores, arriba a la izquierda (sobre el baseline,
        # que no tiene errores) para no taparla.
        x, y, ha, va = (0.5, 0.5, "center", "center") if all(en_cero) else (0.02, 0.94, "left", "top")
        ax_err.text(x, y, texto, transform=ax_err.transAxes, ha=ha, va=va, fontsize=11,
                    color="#333", bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": "#bbb", "alpha": 0.9})
    else:
        ax_err.set_ylim(bottom=0)
    ax_err.legend(**LEYENDA)
    if exp_id in CON_LAG:
        axs[2].axhline(slo["lag_outbox_s"], color="#e67e22", ls="--", lw=1, label=f"SLO {slo['lag_outbox_s']} s")
        axs[2].set_ylabel("lag del outbox (s)")
        axs[2].set_ylim(bottom=0)
        axs[2].legend(**LEYENDA)
    if defin.get("falla"):
        axs[-1].set_xlabel("minutos desde la activación de la falla  ·  gris: baseline · rojo: falla · verde: recuperación")
    else:   # O1: mismas fases y marcas que el resto, pero sin falla inyectada
        axs[-1].set_xlabel("minutos desde la marca falla_on (sin falla inyectada: las tres fases tienen la misma carga)")
    fig.suptitle(f"{exp_id} — {defin['descripcion']}", fontsize=11)
    fig.text(0.01, 0.005, "Corridas: " + " · ".join(f"{e}: {r}" for r, e, _ in datos) if len(datos) > 1
             else f"Corrida: {datos[0][0]}", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    destino = EVID / "figuras" / f"{exp_id}.png"
    destino.parent.mkdir(exist_ok=True)
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*", help=f"experimentos (por defecto todos: {' '.join(CORRIDAS)})")
    args = ap.parse_args()
    slo = yaml.safe_load((RAIZ / "lab" / "slo.yaml").read_text(encoding="utf-8"))["slo"]
    for exp_id in args.ids or CORRIDAS:
        print(figura(exp_id.upper(), slo).relative_to(RAIZ))


if __name__ == "__main__":
    main()
