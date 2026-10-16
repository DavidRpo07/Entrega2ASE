#!/usr/bin/env python3
"""Runner de experimentos (Entregable 3, fase 3).

    make experimento ID=A1            # corrida real: exige evidencia/predictions/A1.md en estado LISTA
    make experimento-prueba ID=A1     # corrida corta de prueba (prefijo PRUEBA-, ignorada por git)

Protocolo (lab/slo.yaml): kill switch → make lab-reset → k6 a tasa constante durante
baseline + falla + recuperación → activar la falla (POST /admin/faults) al terminar el
baseline → kill switch (DELETE /admin/faults) al terminar la falla → recolectar evidencia.

Evidencia por corrida (<RUN> = <ID>_<UTC>):
  evidencia/experiments/<RUN>/   manifest.json (config usada, marcas de tiempo, versiones), prediccion.md
  evidencia/baseline/<RUN>/      métricas del cliente en la fase baseline
  evidencia/metrics/<RUN>/       peticiones.csv.gz (k6, una fila por petición), prometheus/*.csv, k6_resumen.json
  evidencia/logs/<RUN>/          logs JSON por servicio, nginx, timeline del runner, inyecciones.csv
  evidencia/traces/<RUN>/        trazas de Jaeger (baseline, más lentas y con error durante la falla)
  evidencia/results/<RUN>/       resumen.json y resumen.md (por fase, SLO, recuperación)

Solo librería estándar + pyyaml (venv del repo).
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from lab.fallas.inyector import falla_desde_dict  # noqa: E402  (valida la configuración antes de correr)

API = "http://localhost:8080"
PROM = "http://localhost:9090"
JAEGER = "http://localhost:16686"
GRAFANA = "http://localhost:3000"
EVID = RAIZ / "evidencia"
K6_IMAGEN = "grafana/k6:0.55.0"
SERVICIOS_LOGS = ["api-1", "api-2", "worker", "ext-sap", "fallas-ext", "nginx", "postgres"]

# Series de Prometheus que se guardan por corrida (CSV, paso 5 s).
CONSULTAS = {
    "latencia_post_p50_ms": '1000*histogram_quantile(0.50, sum by (le) (rate(http_peticion_duracion_segundos_bucket{job="api",metodo="POST",ruta="/ordenes"}[30s])))',
    "latencia_post_p95_ms": '1000*histogram_quantile(0.95, sum by (le) (rate(http_peticion_duracion_segundos_bucket{job="api",metodo="POST",ruta="/ordenes"}[30s])))',
    "latencia_post_p99_ms": '1000*histogram_quantile(0.99, sum by (le) (rate(http_peticion_duracion_segundos_bucket{job="api",metodo="POST",ruta="/ordenes"}[30s])))',
    "latencia_p95_por_ruta_ms": '1000*histogram_quantile(0.95, sum by (le, metodo, ruta) (rate(http_peticion_duracion_segundos_bucket{job="api"}[30s])))',
    "latencia_post_p95_por_replica_ms": '1000*histogram_quantile(0.95, sum by (le, instancia) (rate(http_peticion_duracion_segundos_bucket{job="api",metodo="POST",ruta="/ordenes"}[30s])))',
    "peticiones_por_s_por_codigo": 'sum by (codigo) (rate(http_peticion_duracion_segundos_count{job="api"}[30s]))',
    "errores_5xx_ratio_60s": 'sum(rate(http_peticion_duracion_segundos_count{job="api",codigo=~"5.."}[60s])) / clamp_min(sum(rate(http_peticion_duracion_segundos_count{job="api"}[60s])), 1e-9)',
    "pool_en_uso": 'db_pool_conexiones{job="api",estado="en_uso"}',
    "pool_esperando": 'db_pool_esperando{job="api"}',
    "pool_timeouts_por_s": 'rate(db_pool_timeouts_total{job="api"}[30s])',
    "pool_espera_p95_ms": '1000*histogram_quantile(0.95, sum by (le, instancia) (rate(db_pool_espera_segundos_bucket{job="api"}[30s])))',
    "outbox_pendientes": 'outbox_pendientes',
    "outbox_lag_s": 'outbox_lag_segundos',
    "outbox_publicados_por_s": 'sum(rate(outbox_publicados_total{job="worker"}[30s]))',
    "outbox_fallos_por_s": 'sum by (motivo) (rate(outbox_fallos_total[30s]))',
    "ext_sap_p95_ms": '1000*histogram_quantile(0.95, sum by (le, resultado) (rate(ext_sap_llamada_duracion_segundos_bucket[30s])))',
    "falla_activa": 'max by (falla_id) (falla_activa)',
    "falla_externa_efecto": 'max by (falla_id, efecto) (falla_externa_efecto)',
    "fallas_inyectadas_por_s": 'sum by (falla_id) (rate(fallas_inyectadas_total[30s]))',
    "cpu_por_proceso": 'rate(process_cpu_seconds_total{job=~"api|worker|ext-sap|fallas-ext"}[30s])',
    "memoria_por_proceso_bytes": 'process_resident_memory_bytes{job=~"api|worker|ext-sap|fallas-ext"}',
    "gc_colecciones_por_s": 'sum by (instancia, generation) (rate(python_gc_collections_total[30s]))',
    "cpu_por_contenedor": 'sum by (servicio) (rate(container_cpu_usage_seconds_total{id=~"/docker/.+"}[30s]) * on (id) group_left (servicio) contenedor_info)',
    "memoria_por_contenedor_bytes": 'sum by (servicio) (container_memory_working_set_bytes{id=~"/docker/.+"} * on (id) group_left (servicio) contenedor_info)',
    "pg_locks_por_modo": 'sum by (mode) (pg_locks_count{datname="escalables"})',
    "pg_conexiones_por_estado": 'sum by (state) (pg_stat_activity_count{datname="escalables"})',
    "pg_rollback_por_s": 'rate(pg_stat_database_xact_rollback{datname="escalables"}[30s])',
    "trazas_activas": 'trazas_activas',
}


# ---------------------------------------------------------------- utilidades
def ahora() -> float:
    return time.time()


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


def http(metodo, url, cuerpo=None, timeout=15):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def prom_instant(expr):
    q = urllib.parse.urlencode({"query": expr})
    _, r = http("GET", f"{PROM}/api/v1/query?{q}")
    return r["data"]["result"] if isinstance(r, dict) else []


def prom_rango(expr, ini, fin, paso=5):
    q = urllib.parse.urlencode({"query": expr, "start": ini, "end": fin, "step": paso})
    _, r = http("GET", f"{PROM}/api/v1/query_range?{q}", timeout=60)
    return r["data"]["result"] if isinstance(r, dict) else []


def valor(expr, defecto=float("nan")):
    r = prom_instant(expr)
    try:
        return float(r[0]["value"][1])
    except (IndexError, KeyError, ValueError):
        return defecto


def sh(*cmd, **kw):
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, **kw)


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def percentil(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] * (c - k) + xs[c] * (k - f)


class Timeline:
    """Eventos del runner (JSON por línea): marcas de fase y muestras del monitor."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.eventos = []

    def __call__(self, evento, **datos):
        e = {"ts": iso(ahora()), "t": round(ahora(), 3), "evento": evento, **datos}
        self.eventos.append(e)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        extra = " ".join(f"{k}={v}" for k, v in datos.items() if k != "config")
        print(f"[{e['ts'][11:19]}] {evento} {extra}", flush=True)


# ---------------------------------------------------------------- preparación
def cargar_definicion(exp_id: str, slo: dict, prueba: bool, fases_cli: dict) -> dict:
    ruta = RAIZ / "lab" / "experimentos" / "definiciones" / f"{exp_id}.yaml"
    if not ruta.exists():
        raise SystemExit(f"no existe {ruta.relative_to(RAIZ)}")
    d = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    catalogo = {f["id"]: f for f in yaml.safe_load((RAIZ / "lab/fallas/catalogo.yaml").read_text(encoding="utf-8"))["fallas"]}
    base = catalogo[d.get("falla", exp_id)]
    fases = {**slo["fases"], **(d.get("fases") or {})}
    if prueba:
        fases = {"baseline_s": 30, "falla_s": 30, "recuperacion_s": 25}
    fases.update({k: v for k, v in fases_cli.items() if v})
    falla = {**base, **(d.get("configuracion") or {})}
    falla.setdefault("duracion_s", None)
    if not (d.get("configuracion") or {}).get("duracion_s"):
        falla["duracion_s"] = fases["falla_s"] + 30   # red de seguridad: expira sola
    falla_desde_dict(dict(falla))                    # valida antes de tocar nada
    return {"definicion": d, "archivo": str(ruta.relative_to(RAIZ)), "falla": falla, "fases": fases}


def prediccion(exp_id: str, prueba: bool) -> dict:
    ruta = EVID / "predictions" / f"{exp_id}.md"
    if not ruta.exists():
        raise SystemExit(f"falta la predicción {ruta.relative_to(RAIZ)}")
    texto = ruta.read_text(encoding="utf-8")
    pendiente = "Estado: PENDIENTE" in texto
    if pendiente and not prueba:
        raise SystemExit(f"{ruta.relative_to(RAIZ)} sigue en 'Estado: PENDIENTE': escriba la predicción y haga commit antes de correr")
    rel = str(ruta.relative_to(RAIZ))
    sucia = bool(sh("git", "status", "--porcelain", "--", rel).stdout.strip())
    commit = sh("git", "log", "-1", "--format=%H %cI", "--", rel).stdout.strip()
    if sucia and not prueba:
        print(f"AVISO: {rel} tiene cambios sin commit; la evidencia de 'predicción previa' será más débil.")
    return {"archivo": rel, "sha256": sha256(ruta), "pendiente": pendiente,
            "commit_ultimo_cambio": commit or None, "cambios_sin_commit": sucia, "texto": texto}


def prechecks(timeline) -> dict:
    c, r = http("GET", f"{API}/health")
    if c != 200:
        raise SystemExit(f"el laboratorio no responde ({c}); corra `make lab-up`")
    vistas = {http("GET", f"{API}/health")[1].get("instancia") for _ in range(6)}
    _, t = http("GET", f"{PROM}/api/v1/targets")
    caidos = [x["labels"]["job"] for x in t["data"]["activeTargets"] if x["health"] != "up"]
    ajenos = [n for n in sh("docker", "ps", "--format", "{{.Names}}").stdout.split()
              if not n.startswith("proyectoase-") and n != "postgres-escalables"]
    info = {"replicas_vistas": sorted(v for v in vistas if v), "targets_caidos": caidos,
            "trazas_activas": valor("min(trazas_activas)"), "contenedores_ajenos": ajenos}
    timeline("prechecks", **info)
    if caidos:
        raise SystemExit(f"targets de Prometheus caídos: {caidos}")
    if ajenos:
        print(f"AVISO: hay {len(ajenos)} contenedores ajenos al laboratorio corriendo (ruido en las mediciones): {ajenos[:6]}…")
    return info


# ---------------------------------------------------------------- ejecución
def correr_k6(run: str, duracion_s: int, slo: dict, dir_metrics: Path) -> subprocess.Popen:
    carga = slo["carga"]
    datos = f"carga_s{carga['semilla']}_n{carga['n']}.json"
    if not (RAIZ / "lab/carga/datos" / datos).exists():
        sh("make", "lab-carga-datos", f"SEMILLA={carga['semilla']}", f"N={carga['n']}", check=True)
    cmd = ["docker", "run", "--rm", "--name", f"k6-{run.lower()}", "--network", "escalables-lab",
           "-e", "K6_CSV_TIME_FORMAT=unix_milli",
           "-v", f"{RAIZ / 'lab/carga'}:/carga:ro", "-v", f"{dir_metrics}:/salida",
           K6_IMAGEN, "run", "--quiet",
           "-e", "BASE=http://nginx", "-e", f"CARGA=/carga/datos/{datos}",
           "-e", f"RATE={carga['tasa_rps']}", "-e", f"DURACION={duracion_s}s", "-e", f"ETIQUETA={run}",
           "--summary-export", "/salida/k6_resumen.json", "--out", "csv=/salida/k6_crudo.csv.gz",
           "/carga/k6/carga.js"]
    return subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def primera_peticion(desde: float, timeout_s: float = 60) -> float:
    """Hora (UTC) de la primera petición de k6 según el access log JSON de nginx."""
    fin = ahora() + timeout_s
    while ahora() < fin:
        r = sh("docker", "compose", "logs", "--no-log-prefix", "--since", iso(desde - 1), "nginx")
        for linea in r.stdout.splitlines():
            if '"/ordenes' in linea or '"/proveedores' in linea or '"/catalogo' in linea:
                try:
                    return float(json.loads(linea)["t"])   # $msec: epoch con milisegundos
                except (ValueError, KeyError):
                    continue
        time.sleep(0.2)
    raise SystemExit("k6 no envió peticiones en 60 s (ver evidencia/logs/<RUN>/k6.log)")


def monitor(timeline, parar: threading.Event, fase: dict):
    while not parar.wait(10):
        timeline("muestra", fase=fase["actual"],
                 p95_post_ms=round(valor('1000*histogram_quantile(0.95, sum by (le) (rate(http_peticion_duracion_segundos_bucket{job="api",metodo="POST",ruta="/ordenes"}[30s])))'), 1),
                 errores_pct_60s=round(100 * valor('sum(rate(http_peticion_duracion_segundos_count{job="api",codigo=~"5.."}[60s])) / clamp_min(sum(rate(http_peticion_duracion_segundos_count{job="api"}[60s])), 1e-9)', 0), 2),
                 lag_outbox_s=round(valor("max(outbox_lag_segundos)", 0), 1),
                 fallas_activas=[r["metric"]["falla_id"] for r in prom_instant("max by (falla_id) (falla_activa) == 1")])


# ---------------------------------------------------------------- evidencia
def compactar_k6(dir_metrics: Path) -> list[dict]:
    """k6 escribe ~20 filas por petición; se deja una por petición (http_req_duration)."""
    crudo = dir_metrics / "k6_crudo.csv.gz"
    filas = []
    with gzip.open(crudo, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["metric_name"] != "http_req_duration":
                continue
            extra = dict(urllib.parse.parse_qsl(r.get("extra_tags") or ""))
            # k6 fecha la muestra al terminar la petición; ts = inicio, para asignar cada petición a la
            # fase en que se envió (una petición lenta enviada durante la falla no cuenta como recuperación).
            ms = float(r["metric_value"])
            filas.append({"ts": round(int(r["timestamp"]) / 1000.0 - ms / 1000.0, 3), "op": extra.get("op", ""),
                          "clave": extra.get("clave", ""), "status": int(r["status"] or 0), "ms": ms})
    filas.sort(key=lambda x: x["ts"])
    with gzip.open(dir_metrics / "peticiones.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "op", "clave", "status", "ms"])
        w.writeheader()
        w.writerows(filas)
    crudo.unlink()
    return filas


def es_error(status: int) -> bool:
    return status == 0 or status >= 500


def stats(filas: list[dict]) -> dict:
    if not filas:
        return {"peticiones": 0}
    dur = filas[-1]["ts"] - filas[0]["ts"] or 1
    post = [x["ms"] for x in filas if x["op"] == "crear"]
    codigos = {}
    for x in filas:
        codigos[str(x["status"])] = codigos.get(str(x["status"]), 0) + 1
    r = lambda v: None if v is None else round(v, 1)
    return {
        "peticiones": len(filas), "throughput_rps": round(len(filas) / dur, 2),
        "post": {"n": len(post), "p50_ms": r(percentil(post, 50)), "p95_ms": r(percentil(post, 95)),
                 "p99_ms": r(percentil(post, 99)), "max_ms": r(max(post) if post else None)},
        "todas": {"p50_ms": r(percentil([x["ms"] for x in filas], 50)), "p95_ms": r(percentil([x["ms"] for x in filas], 95)),
                  "p99_ms": r(percentil([x["ms"] for x in filas], 99))},
        "por_op": {op: {"n": len(v), "p95_ms": r(percentil(v, 95))} for op in ("crear", "listar", "precio")
                   if (v := [x["ms"] for x in filas if x["op"] == op])},
        "codigos": dict(sorted(codigos.items())),
        "errores_pct": round(100 * sum(es_error(x["status"]) for x in filas) / len(filas), 3),
    }


def peor_ventana_errores(filas, ini, fin, ventana):
    peor = 0.0
    t = ini
    while t < fin:
        v = [x for x in filas if t <= x["ts"] < min(t + ventana, fin)]
        if v:
            peor = max(peor, 100 * sum(es_error(x["status"]) for x in v) / len(v))
        t += ventana
    return round(peor, 3)


def recuperacion(filas, t_kill, t_fin, slo, lag_serie):
    """Primer instante tras el kill switch desde el que, durante 20 s seguidos, cada
    bloque de 5 s cumple p95 POST ≤ SLO y errores < SLO (cliente), y el lag < SLO."""
    bloque, sostener = 5.0, 20.0

    def ok_cliente(t):
        u = t
        while u < t + sostener:
            v = [x for x in filas if u <= x["ts"] < u + bloque]
            post = [x["ms"] for x in v if x["op"] == "crear"]
            if v and (100 * sum(es_error(x["status"]) for x in v) / len(v) >= slo["errores_pct"]):
                return False
            if post and percentil(post, 95) > slo["p95_post_ms"]:
                return False
            u += bloque
        return True

    t_cli = None
    t = t_kill
    while t + sostener <= t_fin:
        if ok_cliente(t):
            t_cli = t
            break
        t += 1.0
    # Lag (Prometheus, paso 5 s): se parte de la última muestra en o antes del kill switch, para
    # no contar como "recuperación" la espera hasta la siguiente muestra si el lag ya estaba bien.
    t_lag = None
    serie = sorted(lag_serie)
    previas = [p for p in serie if p[0] <= t_kill]
    candidatas = ([previas[-1]] if previas else []) + [p for p in serie if p[0] > t_kill]
    for ts, v in candidatas:
        if v < slo["lag_outbox_s"] and all(v2 < slo["lag_outbox_s"] for ts2, v2 in serie if ts <= ts2 <= ts + sostener):
            t_lag = max(ts, t_kill)
            break
    if t_cli is None or t_lag is None:
        return {"recuperado": False, "cliente_s": None if t_cli is None else round(t_cli - t_kill, 1),
                "lag_s": None if t_lag is None else round(t_lag - t_kill, 1)}
    total = max(t_cli, t_lag) - t_kill
    return {"recuperado": True, "segundos": round(total, 1), "cliente_s": round(t_cli - t_kill, 1),
            "lag_s": round(t_lag - t_kill, 1), "cumple_slo": total < slo["recuperacion_s"]}


def guardar_prometheus(dir_prom: Path, ini, fin) -> dict:
    dir_prom.mkdir(parents=True, exist_ok=True)
    series = {}
    for nombre, expr in CONSULTAS.items():
        res = prom_rango(expr, ini, fin)
        with (dir_prom / f"{nombre}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts_utc", "ts", "serie", "valor"])
            for s in res:
                etiqueta = ",".join(f"{k}={v}" for k, v in sorted(s["metric"].items()) if k not in ("job", "instance", "__name__"))
                for ts, v in s["values"]:
                    w.writerow([iso(float(ts)), ts, etiqueta, v])
        series[nombre] = res
    (dir_prom / "consultas.json").write_text(json.dumps(CONSULTAS, indent=2, ensure_ascii=False), encoding="utf-8")
    return series


def guardar_logs(dir_logs: Path, ini, fin) -> list[dict]:
    dir_logs.mkdir(parents=True, exist_ok=True)
    inyecciones = []
    for s in SERVICIOS_LOGS:
        r = sh("docker", "compose", "logs", "--no-log-prefix", "--since", iso(ini - 5), "--until", iso(fin + 5), s)
        nombre = f"{s}.log.gz" if s == "postgres" else f"{s}.jsonl.gz"   # postgres no escribe JSON
        with gzip.open(dir_logs / nombre, "wt", encoding="utf-8") as f:
            f.write(r.stdout)
        for linea in r.stdout.splitlines():
            if '"falla inyectada' not in linea:
                continue
            try:
                e = json.loads(linea)
            except ValueError:
                continue
            inyecciones.append({"ts": e["ts"], "instancia": e.get("instancia"), "falla_id": e.get("falla_id"),
                                "target": e.get("target"), "clave": e.get("clave"), "ruta": e.get("ruta"), "ms": e.get("ms")})
    inyecciones.sort(key=lambda x: x["ts"])
    with (dir_logs / "inyecciones.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "instancia", "falla_id", "target", "clave", "ruta", "ms"])
        w.writeheader()
        w.writerows(inyecciones)
    return inyecciones


def guardar_trazas(dir_traces: Path, marcas: dict, slo: dict) -> list[dict]:
    dir_traces.mkdir(parents=True, exist_ok=True)
    us = lambda t: int(t * 1e6)
    pedidos = [
        ("baseline_muestra", "ordenes-api", "POST /ordenes", marcas["baseline"], marcas["falla_on"], None, None, 5),
        ("falla_lentas", "ordenes-api", "POST /ordenes", marcas["falla_on"], marcas["kill"], f"{slo['p99_post_ms']}ms", None, 15),
        ("falla_errores", "ordenes-api", "POST /ordenes", marcas["falla_on"], marcas["kill"], None, '{"error":"true"}', 10),
        ("falla_worker_errores", "outbox-worker", "outbox.publicar", marcas["falla_on"], marcas["kill"], None, '{"error":"true"}', 5),
        ("recuperacion_muestra", "ordenes-api", "POST /ordenes", marcas["kill"], marcas["fin"], None, None, 5),
    ]
    indice = []
    for nombre, servicio, op, ini, fin, min_dur, tags, limite in pedidos:
        p = {"service": servicio, "operation": op, "start": us(ini), "end": us(fin), "limit": limite}
        if min_dur:
            p["minDuration"] = min_dur
        if tags:
            p["tags"] = tags
        c, r = http("GET", f"{JAEGER}/api/traces?{urllib.parse.urlencode(p)}", timeout=30)
        trazas = r.get("data", []) if isinstance(r, dict) else []
        if trazas:   # formato de la API de Jaeger: se puede abrir en Jaeger UI ("JSON File")
            with gzip.open(dir_traces / f"{nombre}.json.gz", "wt", encoding="utf-8") as f:
                f.write(json.dumps({"data": trazas}, ensure_ascii=False))
        for t in trazas:
            raiz = min(t["spans"], key=lambda s: s["startTime"])
            indice.append({"grupo": nombre, "trace_id": t["traceID"], "servicio": servicio,
                           "inicio_utc": iso(raiz["startTime"] / 1e6), "duracion_ms": round(raiz["duration"] / 1000, 1),
                           "spans": len(t["spans"]), "jaeger": f"{JAEGER}/trace/{t['traceID']}"})
    with (dir_traces / "indice.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["grupo", "trace_id", "servicio", "inicio_utc", "duracion_ms", "spans", "jaeger"])
        w.writeheader()
        w.writerows(indice)
    return indice


def resumen_md(run, exp, marcas, por_fase, rec, slo, pred, inyecciones, trazas, enlaces) -> str:
    def fila(nombre, s):
        if not s.get("peticiones"):
            return f"| {nombre} | 0 | | | | | | |"
        return (f"| {nombre} | {s['peticiones']} | {s['throughput_rps']} | {s['post']['p50_ms']} | {s['post']['p95_ms']} | "
                f"{s['post']['p99_ms']} | {s['errores_pct']} | {s['peor_ventana_errores_pct']} | {s.get('lag_max_s', '')} |")
    ok = lambda b: "✅" if b else "❌"
    lineas = [
        f"# Resultado {run}", "",
        f"- Experimento: **{exp['definicion']['id']}** — {exp['definicion']['descripcion']}",
        f"- Configuración de la falla: `{json.dumps({k: v for k, v in exp['falla'].items() if k not in ('descripcion',)}, ensure_ascii=False)}`",
        f"- Fases: baseline {exp['fases']['baseline_s']} s · falla {exp['fases']['falla_s']} s · recuperación {exp['fases']['recuperacion_s']} s · tasa {slo['carga']['tasa_rps']} req/s",
        f"- Marcas (UTC): baseline {iso(marcas['baseline'])} · falla {iso(marcas['falla_on'])} · kill switch {iso(marcas['kill'])} · fin {iso(marcas['fin'])}",
        f"- Predicción: `{pred['archivo']}` sha256 `{pred['sha256'][:12]}…`" + (" (**PENDIENTE: corrida de prueba**)" if pred["pendiente"] else ""),
        f"- Grafana: {enlaces['grafana']}", "",
        "## Por fase (cliente: k6, todas las peticiones; latencias de POST /ordenes)", "",
        "| Fase | Peticiones | req/s | p50 POST ms | p95 POST ms | p99 POST ms | % errores | peor ventana 60 s % | lag máx s |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        fila("baseline", por_fase["baseline"]), fila("falla", por_fase["falla"]), fila("recuperación", por_fase["recuperacion"]), "",
        "## SLO", "",
        "| Fase | p95 ≤ {p95} ms | p99 ≤ {p99} ms | errores < {e} % (60 s) | lag < {lag} s |".format(
            p95=slo["slo"]["p95_post_ms"], p99=slo["slo"]["p99_post_ms"], e=slo["slo"]["errores_pct"], lag=slo["slo"]["lag_outbox_s"]),
        "| --- | --- | --- | --- | --- |",
    ]
    for f in ("baseline", "falla", "recuperacion"):
        c = por_fase[f].get("cumple", {})
        if c:
            lineas.append(f"| {f} | {ok(c['p95'])} | {ok(c['p99'])} | {ok(c['errores'])} | {ok(c['lag'])} |")
    rtxt = (f"{rec['segundos']} s (cliente {rec['cliente_s']} s, lag {rec['lag_s']} s) → {ok(rec['cumple_slo'])} SLO < {slo['slo']['recuperacion_s']} s"
            if rec.get("recuperado") else f"no se recuperó dentro de la fase de recuperación (cliente {rec.get('cliente_s')}, lag {rec.get('lag_s')})")
    lineas += ["", f"**Recuperación tras el kill switch:** {rtxt}", "",
               "## Evidencia", "",
               f"- Inyecciones registradas: {len(inyecciones)} (`evidencia/logs/{run}/inyecciones.csv`, con la clave de cada petición)",
               f"- Trazas guardadas: {len(trazas)} (`evidencia/traces/{run}/indice.csv`)",
               f"- Métricas: `evidencia/metrics/{run}/` (peticiones.csv.gz de k6 y series de Prometheus)",
               f"- Logs: `evidencia/logs/{run}/` (JSON por servicio con trace_id; nginx con upstream/status)", "",
               "## Predicción vs. resultado (lo completa el equipo)", "",
               "| Señal | Predicción | Resultado | Diferencia y por qué |", "| --- | --- | --- | --- |", "| | | | |", ""]
    return "\n".join(lineas)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True)
    ap.add_argument("--prueba", action="store_true", help="fases cortas, prefijo PRUEBA-, permite predicción PENDIENTE")
    ap.add_argument("--baseline-s", type=int)
    ap.add_argument("--falla-s", type=int)
    ap.add_argument("--recuperacion-s", type=int)
    a = ap.parse_args()

    slo = yaml.safe_load((RAIZ / "lab/slo.yaml").read_text(encoding="utf-8"))
    exp = cargar_definicion(a.id, slo, a.prueba, {"baseline_s": a.baseline_s, "falla_s": a.falla_s, "recuperacion_s": a.recuperacion_s})
    pred = prediccion(a.id, a.prueba)
    run = ("PRUEBA-" if a.prueba else "") + f"{a.id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    dirs = {k: EVID / k / run for k in ("experiments", "baseline", "metrics", "logs", "traces", "results")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    timeline = Timeline(dirs["logs"] / "runner.jsonl")
    timeline("inicio", run=run, fases=exp["fases"])
    entorno = prechecks(timeline)

    fases = exp["fases"]
    total = fases["baseline_s"] + fases["falla_s"] + fases["recuperacion_s"]
    http("DELETE", f"{API}/admin/faults")
    time.sleep(2)
    r = sh("make", "lab-reset")
    timeline("lab_reset", salida=r.stdout.strip().splitlines()[-2:] if r.stdout else r.stderr[-300:])
    if r.returncode != 0:
        raise SystemExit(f"make lab-reset falló: {r.stderr}")

    lanzado = ahora()
    k6 = correr_k6(run, total, slo, dirs["metrics"].resolve())
    estado = {"actual": "arranque"}
    parar = threading.Event()
    hilo = threading.Thread(target=monitor, args=(timeline, parar, estado), daemon=True)
    marcas = {}
    try:
        # El baseline empieza con la primera petición real de k6 (vista en el log de nginx), no
        # con el arranque del contenedor: así las mismas claves caen en la misma fase en cada corrida.
        marcas["baseline"] = primera_peticion(lanzado)
        estado["actual"] = "baseline"
        timeline("fase_baseline", primera_peticion_utc=iso(marcas["baseline"]))
        hilo.start()
        time.sleep(max(0.0, marcas["baseline"] + fases["baseline_s"] - ahora()))

        c, resp = http("POST", f"{API}/admin/faults", exp["falla"])
        marcas["falla_on"] = ahora()
        estado["actual"] = "falla"
        timeline("falla_activada", codigo=c, config=exp["falla"])
        if c != 201:
            raise SystemExit(f"no se pudo activar la falla: {c} {resp}")
        time.sleep(max(0.0, marcas["falla_on"] + fases["falla_s"] - ahora()))

        c, _ = http("DELETE", f"{API}/admin/faults")
        marcas["kill"] = ahora()
        estado["actual"] = "recuperacion"
        timeline("kill_switch", codigo=c)
        salida_k6, _ = k6.communicate(timeout=fases["recuperacion_s"] + 120)
        marcas["fin"] = ahora()
        timeline("fin_carga", k6_codigo=k6.returncode)
    except BaseException:
        timeline("abortado", detalle="kill switch de emergencia")
        http("DELETE", f"{API}/admin/faults")
        sh("docker", "rm", "-f", f"k6-{run.lower()}")
        raise
    finally:
        parar.set()
    (dirs["logs"] / "k6.log").write_text(salida_k6 or "", encoding="utf-8")

    # ------------------------------------------------------------ evidencia
    print("recolectando evidencia…", flush=True)
    filas = compactar_k6(dirs["metrics"])
    ini, fin = marcas["baseline"], marcas["fin"]
    series = guardar_prometheus(dirs["metrics"] / "prometheus", ini - 30, fin + 15)
    lag_serie = [(float(ts), float(v)) for s in series.get("outbox_lag_s", []) for ts, v in s["values"]]
    inyecciones = guardar_logs(dirs["logs"], ini, fin)
    trazas = guardar_trazas(dirs["traces"], marcas, slo["slo"])

    tramos = {"baseline": (filas[0]["ts"] if filas else ini, marcas["falla_on"]),
              "falla": (marcas["falla_on"], marcas["kill"]), "recuperacion": (marcas["kill"], fin + 1)}
    por_fase = {}
    for nombre, (t0, t1) in tramos.items():
        sub = [x for x in filas if t0 <= x["ts"] < t1]
        s = stats(sub)
        if s.get("peticiones"):
            s["peor_ventana_errores_pct"] = peor_ventana_errores(sub, t0, t1, slo["slo"]["ventana_errores_s"])
            s["lag_max_s"] = round(max([v for ts, v in lag_serie if t0 <= ts < t1] or [0]), 1)
            s["cumple"] = {"p95": (s["post"]["p95_ms"] or 0) <= slo["slo"]["p95_post_ms"],
                           "p99": (s["post"]["p99_ms"] or 0) <= slo["slo"]["p99_post_ms"],
                           "errores": s["peor_ventana_errores_pct"] < slo["slo"]["errores_pct"],
                           "lag": s["lag_max_s"] < slo["slo"]["lag_outbox_s"]}
        por_fase[nombre] = s
    rec = recuperacion(filas, marcas["kill"], fin, slo["slo"], lag_serie)
    claves_expuestas = sorted({x["clave"] for x in filas if marcas["falla_on"] <= x["ts"] < marcas["kill"]})
    enlaces = {"grafana": f"{GRAFANA}/d/lab-entregable3?from={int((ini - 30) * 1000)}&to={int((fin + 15) * 1000)}",
               "jaeger": f"{JAEGER}/search?service=ordenes-api&start={int(marcas['falla_on'] * 1e6)}&end={int(marcas['kill'] * 1e6)}"}

    (dirs["baseline"] / "resumen_baseline.json").write_text(json.dumps(
        {"run": run, "desde_utc": iso(tramos["baseline"][0]), "hasta_utc": iso(tramos["baseline"][1]), **por_fase["baseline"]},
        indent=2, ensure_ascii=False), encoding="utf-8")
    resumen = {"run": run, "experimento": exp["definicion"]["id"], "prueba": a.prueba, "marcas_utc": {k: iso(v) for k, v in marcas.items()},
               "por_fase": por_fase, "recuperacion": rec, "slo": slo["slo"], "inyecciones": len(inyecciones),
               "claves_expuestas_durante_falla": len(claves_expuestas), "trazas": len(trazas), "enlaces": enlaces}
    (dirs["results"] / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    (dirs["results"] / "resumen.md").write_text(resumen_md(run, exp, marcas, por_fase, rec, slo, pred, inyecciones, trazas, enlaces), encoding="utf-8")
    (dirs["experiments"] / "prediccion.md").write_text(pred.pop("texto"), encoding="utf-8")
    datos = RAIZ / "lab/carga/datos" / f"carga_s{slo['carga']['semilla']}_n{slo['carga']['n']}.json"
    manifest = {
        "run": run, "prueba": a.prueba, "definicion": exp["archivo"], "falla_aplicada": exp["falla"], "fases": fases,
        "carga": {**slo["carga"], "archivo": str(datos.relative_to(RAIZ)), "sha256": sha256(datos)},
        "marcas_utc": {k: iso(v) for k, v in marcas.items()}, "prediccion": pred, "entorno": entorno,
        "git": {"commit": sh("git", "rev-parse", "HEAD").stdout.strip(), "cambios_sin_commit": bool(sh("git", "status", "--porcelain", "--", "app", "lab", "infra", "compose.yaml").stdout.strip())},
        "k6": {"imagen": K6_IMAGEN, "codigo_salida": k6.returncode}, "claves_expuestas_durante_falla": claves_expuestas,
    }
    (dirs["experiments"] / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    timeline("evidencia_lista", resultados=str(dirs["results"].relative_to(RAIZ)))
    print("\n" + (dirs["results"] / "resumen.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
