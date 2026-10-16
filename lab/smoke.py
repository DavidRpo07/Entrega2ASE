#!/usr/bin/env python3
"""Smoke test de la fase 1 contra el laboratorio levantado (`make lab-up`).

Solo usa la librería estándar. Verifica: balanceo entre réplicas, POST /ordenes
con outbox → worker → ext-sap, endpoints de lectura, y que las fallas A1, B1,
C1, C2 y D2 se activan por /admin/faults en todos los procesos y se apagan con
el kill switch.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get("LAB_URL", "http://localhost:8080")
fallos: list[str] = []


def http(metodo, ruta, cuerpo=None, timeout=60):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            codigo, cuerpo_r, inst = r.status, r.read(), r.headers.get("X-Instancia")
    except urllib.error.HTTPError as e:
        codigo, cuerpo_r, inst = e.code, e.read(), e.headers.get("X-Instancia")
    ms = (time.perf_counter() - t0) * 1000
    try:
        cuerpo_r = json.loads(cuerpo_r)
    except ValueError:
        pass
    return codigo, cuerpo_r, inst, ms


def check(cond, msg):
    print(("  OK   " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)


def psql(sql):
    return subprocess.check_output(["docker", "exec", "postgres-escalables", "psql", "-U", "postgres",
                                    "-d", "escalables", "-Atc", sql], text=True).split()


def esperar(pred, timeout_s, paso=0.5):
    fin = time.time() + timeout_s
    while time.time() < fin:
        v = pred()
        if v:
            return v
        time.sleep(paso)
    return pred()


def pendientes():
    return http("GET", "/outbox/pendientes")[1]["pendientes"]


def activar(cuerpo):
    c, r, _, _ = http("POST", "/admin/faults", cuerpo)
    check(c == 201, f"POST /admin/faults {cuerpo} -> {c}")
    time.sleep(1.5)  # el inyector de cada proceso relee faults.yaml cada 1 s


def kill_switch():
    c, _, _, _ = http("DELETE", "/admin/faults")
    check(c == 200, f"DELETE /admin/faults (kill switch) -> {c}")
    time.sleep(1.5)


def activa_en_ambas(falla_id):
    vistas = {}
    for _ in range(20):
        _, r, inst, _ = http("GET", "/admin/faults")
        vistas[inst] = falla_id in [f["id"] for f in r["activas"]]
    return vistas


def crear_ordenes(provs, n, cedi=1):
    return [http("POST", "/ordenes", {"proveedor_id": provs[i % len(provs)], "cedi_id": cedi, "total": 1000 + i})
            for i in range(n)]


def main():
    print(f"Smoke test contra {BASE}")
    provs = [int(x) for x in psql(
        "SELECT p.proveedor_id FROM proveedores.proveedor p JOIN proveedores.contrato_suministro c "
        "USING (proveedor_id) WHERE p.estado='ACTIVO' AND c.estado='VIGENTE' "
        "AND now() BETWEEN c.fecha_inicio AND c.fecha_fin ORDER BY 1 LIMIT 20")]
    sin_contrato = int(psql("SELECT max(proveedor_id) + 1 FROM proveedores.proveedor")[0])

    print("\n[1] Balanceo y salud")
    kill_switch()
    instancias = {http("GET", "/health")[2] for _ in range(10)}
    check(instancias == {"api-1", "api-2"}, f"nginx reparte entre réplicas: {sorted(i or '?' for i in instancias)}")

    print("\n[2] POST /ordenes → outbox → worker → ext-sap")
    res = crear_ordenes(provs, 20)
    ids = [r[1]["orden_id"] for r in res if r[0] == 201]
    check(len(ids) == 20, f"20 órdenes creadas (201): {len(ids)}")
    check({r[2] for r in res} == {"api-1", "api-2"}, "las órdenes las atienden ambas réplicas")
    c, r, _, _ = http("POST", "/ordenes", {"proveedor_id": sin_contrato, "cedi_id": 1, "total": 10})
    check(c == 422, f"proveedor sin contrato vigente -> 422 ({c})")
    check(esperar(lambda: pendientes() == 0, 20), "el worker vacía el outbox")
    c, o, _, _ = http("GET", f"/ordenes/{ids[0]}")
    check(c == 200 and o["estado"] == "CONFIRMADA" and o["eventos"][0]["publicado"] and o["lineas"],
          f"orden {ids[0]} CONFIRMADA con línea y evento publicado")

    print("\n[3] Endpoints de lectura")
    p = provs[0]
    for ruta in (f"/proveedores/{p}/ordenes", f"/proveedores/{p}/otif", f"/catalogo/precio?proveedor_id={p}&sku_id=101",
                 "/logistica/franjas?cedi_id=1&fecha=2026-10-20", "/ordenes/999999999"):
        c, _, _, ms = http("GET", ruta)
        check(c == (404 if ruta.endswith("999999999") else 200), f"GET {ruta} -> {c} ({ms:.0f} ms)")

    print("\n[4] A1: latencia fija en catalogo.validar_sku")
    activar({"id": "A1", "probabilidad": 1.0, "duracion_s": 60})
    vistas = activa_en_ambas("A1")
    check(vistas == {"api-1": True, "api-2": True}, f"A1 activa en ambas réplicas: {vistas}")
    lat = [http("GET", f"/catalogo/precio?proveedor_id={p}&sku_id=101")[3] for _ in range(4)]
    check(min(lat) >= 800, f"precio con A1 tarda >= 800 ms: {[round(x) for x in lat]}")
    kill_switch()
    lat = [http("GET", f"/catalogo/precio?proveedor_id={p}&sku_id=101")[3] for _ in range(4)]
    check(max(lat) < 400, f"tras kill switch vuelve a ser rápido: {[round(x) for x in lat]}")
    vistas = activa_en_ambas("A1")
    check(vistas == {"api-1": False, "api-2": False}, f"A1 apagada en ambas réplicas: {vistas}")

    print("\n[5] C2: consumidor del outbox pausado")
    activar({"id": "C2", "duracion_s": 60})
    crear_ordenes(provs, 5)
    time.sleep(3)
    n = pendientes()
    check(n >= 5, f"con C2 el outbox acumula eventos: {n}")
    kill_switch()
    check(esperar(lambda: pendientes() == 0, 20), "tras kill switch el worker drena el outbox")

    print("\n[6] D2: ext-sap responde 503")
    activar({"id": "D2", "probabilidad": 1.0, "duracion_s": 60})
    crear_ordenes(provs, 3)
    time.sleep(3)
    n = pendientes()
    check(n >= 3, f"con D2 los eventos quedan pendientes (worker recibe 503): {n}")
    kill_switch()
    check(esperar(lambda: pendientes() == 0, 20), "tras kill switch se publican")

    print("\n[7] B1: retención de conexión con pool max 5")
    activar({"id": "B1", "duracion_s": 60})
    with ThreadPoolExecutor(40) as ex:
        res = list(ex.map(lambda i: http("POST", "/ordenes", {"proveedor_id": provs[i % len(provs)],
                                                              "cedi_id": 2, "total": 50}), range(40)))
    codigos = sorted({r[0] for r in res})
    n503 = sum(r[0] == 503 for r in res)
    p_max = max(r[3] for r in res)
    check(n503 > 0 and 201 in codigos, f"pool agotado: {n503}/40 con 503, resto 201, latencia máx {p_max:.0f} ms")
    kill_switch()
    c, _, _, ms = http("POST", "/ordenes", {"proveedor_id": provs[0], "cedi_id": 2, "total": 50})
    check(c == 201 and ms < 1000, f"tras kill switch POST /ordenes -> {c} ({ms:.0f} ms)")

    print("\n[8] C1: CPU solo en api-1")
    activar({"id": "C1", "duracion_s": 60})
    vistas = activa_en_ambas("C1")
    check(vistas.get("api-1") and vistas.get("api-2"), f"C1 registrada en ambas réplicas: {vistas}")
    cpu = subprocess.check_output(["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}}"], text=True)
    uso = {r: float(l.split()[1].rstrip("%")) for l in cpu.splitlines()
           for r in ("api-1", "api-2") if f"-{r}-" in l}
    check(uso.get("api-1", 0) > 50 > uso.get("api-2", 100), f"CPU api-1 alta y api-2 baja: {uso}")
    kill_switch()

    print("\n[9] Validación de configuración")
    c, _, _, _ = http("POST", "/admin/faults", {"id": "X1", "tipo": "latencia_fija", "target": "x", "probabilidad": 2})
    check(c == 422, f"falla inválida -> 422 ({c})")

    observabilidad(provs)

    print("\nRESULTADO:", "OK" if not fallos else f"{len(fallos)} fallo(s)")
    for f in fallos:
        print("  -", f)
    sys.exit(1 if fallos else 0)


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def prom(expr):
    import urllib.parse
    return get_json(PROMETHEUS + "/api/v1/query?" + urllib.parse.urlencode({"query": expr}))["data"]["result"]


def observabilidad(provs):
    print("\n[10] Observabilidad (fase 2)")
    objetivos = get_json(PROMETHEUS + "/api/v1/targets")["data"]["activeTargets"]
    caidos = [t["labels"]["job"] for t in objetivos if t["health"] != "up"]
    check(len(objetivos) >= 6 and not caidos, f"Prometheus raspa {len(objetivos)} targets, caídos: {caidos}")

    c, r, _, _ = http("POST", "/ordenes", {"proveedor_id": provs[0], "cedi_id": 1, "total": 10})
    req = urllib.request.Request(BASE + f"/ordenes/{r['orden_id']}")
    with urllib.request.urlopen(req) as resp:
        trace_id = resp.headers.get("X-Trace-Id")
    check(bool(trace_id), f"la respuesta trae X-Trace-Id: {trace_id}")

    # Traza del POST: api → worker → ext-sap con el mismo trace_id (via traceparent en el outbox).
    req = urllib.request.Request(BASE + "/ordenes", data=json.dumps(
        {"proveedor_id": provs[0], "cedi_id": 1, "total": 10}).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        tid_post = resp.headers.get("X-Trace-Id")

    def servicios_de_traza():
        try:
            t = get_json(f"{JAEGER}/api/traces/{tid_post}")["data"][0]
        except (urllib.error.HTTPError, IndexError, KeyError):
            return None
        s = {p["serviceName"] for p in t["processes"].values()}
        return s if {"ordenes-api", "outbox-worker", "ext-sap"} <= s else None
    s = esperar(servicios_de_traza, 20, 1)
    check(bool(s), f"Jaeger: la traza del POST cruza api, worker y ext-sap: {sorted(s or [])}")

    logs = subprocess.run(["docker", "compose", "logs", "--no-log-prefix", "--since", "2m", "api-1", "api-2"],
                          capture_output=True, text=True).stdout.splitlines()
    con_trace = [json.loads(l) for l in logs if tid_post and tid_post in l]
    check(any(l.get("logger") == "acceso" and l.get("ruta") == "/ordenes" for l in con_trace),
          f"log JSON de acceso con trace_id {tid_post}")

    for metrica in ("http_peticion_duracion_segundos_bucket", "db_pool_conexiones", "outbox_lag_segundos",
                    "falla_activa", "fallas_inyectadas_total", "pg_locks_count"):
        check(bool(esperar(lambda: prom(metrica), 15, 1)), f"Prometheus tiene {metrica}")

    tablero = get_json(GRAFANA + "/api/search?query=Laboratorio")
    check(any(d.get("uid") == "lab-entregable3" for d in tablero), "Grafana: dashboard 'Laboratorio de fallas' provisionado")


PROMETHEUS = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
JAEGER = os.environ.get("JAEGER_URL", "http://localhost:16686")
GRAFANA = os.environ.get("GRAFANA_URL", "http://localhost:3000")


if __name__ == "__main__":
    main()
