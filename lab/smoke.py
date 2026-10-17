#!/usr/bin/env python3
"""Smoke test de la fase 1 contra el laboratorio levantado (`make lab-up`).

Solo usa la librería estándar. Verifica: balanceo entre réplicas, POST /ordenes
con outbox → worker → ext-sap, endpoints de lectura, y que las fallas A1, B1,
C1, C2 y D2 se activan por /admin/faults en todos los procesos y se apagan con
el kill switch. Sección [12]: las correcciones de la fase 4 (lab/correcciones.yaml)
se encienden y apagan en caliente y hacen su efecto.
"""
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get("LAB_URL", "http://localhost:8080")
fallos: list[str] = []


def http(metodo, ruta, cuerpo=None, timeout=60, cabeceras=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers={"Content-Type": "application/json", **(cabeceras or {})})
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

    focalizacion_y_externas(provs)

    print("\n[10] Duración absoluta: un contenedor que reinicia aplica solo lo que queda")
    t0 = time.time()
    activar({"id": "A1", "probabilidad": 1.0, "duracion_s": 15})
    time.sleep(6)
    subprocess.run(["docker", "compose", "restart", "api-2"], capture_output=True, check=True)
    subprocess.run(["docker", "compose", "up", "-d", "--wait", "api-2"], capture_output=True, check=True)
    espera = 15 - (time.time() - t0) + 1.5
    if espera > 0:
        time.sleep(espera)
    vistas = activa_en_ambas("A1")
    check(vistas == {"api-1": False, "api-2": False},
          f"A1 (15 s) expiró también en api-2 reiniciada a los 6 s: {vistas} a los {time.time() - t0:.0f} s")
    kill_switch()

    observabilidad(provs)

    try:
        correcciones(provs)
    finally:
        http("PUT", "/admin/correcciones", {"activas": []})
        http("DELETE", "/admin/faults")

    print("\nRESULTADO:", "OK" if not fallos else f"{len(fallos)} fallo(s)")
    for f in fallos:
        print("  -", f)
    sys.exit(1 if fallos else 0)


def estado_contenedor(servicio):
    cid = subprocess.run(["docker", "compose", "ps", "-a", "-q", servicio], capture_output=True, text=True).stdout.strip()
    return subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", cid], capture_output=True, text=True).stdout.strip()


def focalizacion_y_externas(provs):
    p = provs[0]
    precio = f"/catalogo/precio?proveedor_id={p}&sku_id=101"

    print("\n[F1] Filtro por ruta: A1 solo en POST /ordenes")
    activar({"id": "A1", "probabilidad": 1.0, "duracion_s": 60, "rutas": ["POST /ordenes"]})
    lat_get = [http("GET", precio)[3] for _ in range(4)]
    lat_post = [http("POST", "/ordenes", {"proveedor_id": p, "cedi_id": 1, "total": 1})[3] for _ in range(2)]
    check(max(lat_get) < 400 and min(lat_post) >= 800,
          f"GET precio sin A1 {[round(x) for x in lat_get]} ms; POST con A1 {[round(x) for x in lat_post]} ms")
    kill_switch()

    print("\n[F2] Filtro por instancia: A1 solo en api-1")
    activar({"id": "A1", "probabilidad": 1.0, "duracion_s": 60, "instancias": ["api-1"]})
    por_inst = {}
    for _ in range(8):
        _, _, inst, ms = http("GET", precio)
        por_inst.setdefault(inst, []).append(round(ms))
    check(min(por_inst.get("api-1", [0])) >= 800 and max(por_inst.get("api-2", [9999])) < 400,
          f"latencias por réplica: {por_inst}")
    kill_switch()

    print("\n[F3] D2: ext-sap tarda 2 s antes del 503")
    antes = prom('sum(ext_sap_llamada_duracion_segundos_count{resultado="error"})')
    antes = float(antes[0]["value"][1]) if antes else 0.0
    activar({"id": "D2", "probabilidad": 1.0, "duracion_s": 60})
    crear_ordenes(provs, 1)
    time.sleep(10)   # 1+ llamadas de 2 s + scrape de Prometheus
    r = prom('sum(ext_sap_llamada_duracion_segundos_count{resultado="error"}) - '
             'sum(ext_sap_llamada_duracion_segundos_bucket{resultado="error",le="1.5"})')
    lentas = float(r[0]["value"][1]) if r else 0.0
    total = float(prom('sum(ext_sap_llamada_duracion_segundos_count{resultado="error"})')[0]["value"][1]) - antes
    check(total >= 1 and lentas >= total, f"{total:.0f} llamadas fallidas nuevas, todas de más de 1,5 s")
    kill_switch()
    check(esperar(lambda: pendientes() == 0, 30), "tras kill switch el outbox se vacía")

    print("\n[F4] B2: lock FOR UPDATE sobre las franjas del CEDI 5, y kill switch lo libera")
    activar({"id": "B2", "duracion_s": 120, "parametros": {"cedi_id": 5, "retencion_s": 60, "ciclo_s": 120}})
    time.sleep(1)
    with ThreadPoolExecutor(1) as ex:
        t0 = time.time()
        fut = ex.submit(http, "POST", "/ordenes", {"proveedor_id": p, "cedi_id": 5, "total": 1})
        time.sleep(3)
        check(not fut.done(), "POST al CEDI 5 queda bloqueado por el lock")
        t_kill = time.time()
        kill_switch()
        c, _, _, _ = fut.result(timeout=30)
        liberado = time.time() - t_kill
    check(c == 201 and liberado < 5, f"tras kill switch el POST termina ({c}) a los {liberado:.1f} s")
    c, _, _, ms = http("POST", "/ordenes", {"proveedor_id": p, "cedi_id": 1, "total": 1})
    check(c == 201 and ms < 500, f"otro CEDI no se ve afectado fuera del lock ({ms:.0f} ms)")

    print("\n[F5] D1: caída de api-2 por fallas-ext y kill switch la levanta")
    activar({"id": "D1", "duracion_s": 120, "parametros": {"servicio": "api-2", "caida_tras_s": 0, "caida_s": 120}})
    check(esperar(lambda: estado_contenedor("api-2") == "exited", 15), "api-2 detenida")
    codigos = [http("GET", "/health")[0] for _ in range(10)]
    check(all(c == 200 for c in codigos[2:]), f"nginx sigue respondiendo con api-1: {codigos}")
    t_kill = time.time()
    kill_switch()
    arriba = esperar(lambda: estado_contenedor("api-2") == "running" and "api-2" in {http("GET", "/health")[2] for _ in range(4)}, 30)
    check(bool(arriba), f"api-2 vuelve a atender a los {time.time() - t_kill:.1f} s del kill switch")

    print("\n[F6] cAdvisor: CPU y memoria por contenedor")
    r = prom('sum by (servicio) (container_memory_working_set_bytes{id=~"/docker/.+"} * on (id) group_left (servicio) contenedor_info)')
    servicios = {x["metric"].get("servicio") for x in r}
    check({"postgres", "api-1", "api-2", "worker"} <= servicios, f"memoria por contenedor: {sorted(servicios)}")


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def prom(expr):
    import urllib.parse
    return get_json(PROMETHEUS + "/api/v1/query?" + urllib.parse.urlencode({"query": expr}))["data"]["result"]


def observabilidad(provs):
    print("\n[11] Observabilidad (fase 2)")
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


def poner_correcciones(activas, corrida="smoke"):
    c, r, _, _ = http("PUT", "/admin/correcciones", {"activas": activas, "corrida": f"{corrida}-{time.time():.3f}"})
    check(c == 200 and r.get("activas") == activas, f"PUT /admin/correcciones {activas} -> {c}")

    def vista():
        filas = prom('correccion_activa{job=~"api|worker"}')
        procesos = {x["metric"].get("instancia") for x in filas}
        return {"api-1", "api-2", "worker"} <= procesos and all(
            float(x["value"][1]) == (1.0 if x["metric"]["correccion"] in activas else 0.0) for x in filas)
    check(bool(esperar(vista, 20, 1)), f"Prometheus: correccion_activa = {activas or 'ninguna'} en api-1, api-2 y worker")


def breakers_en_replicas():
    vistos = {}
    for _ in range(12):
        _, r, inst, _ = http("GET", "/admin/correcciones")
        vistos[inst] = r["breakers"].get("catalogo")
    return vistos


def afectada(falla_id, clave, prob, semilla=42):
    """Misma decisión que el inyector (lab/fallas/inyector.py: _sorteo con sal "p")."""
    return random.Random(f"{semilla}|{falla_id}|{clave}|p").random() < prob


def muertos(orden_ids):
    lista = ",".join(str(i) for i in orden_ids)
    return int(psql(f"SELECT count(*) FROM ordenes.outbox_muerto WHERE aggregate_id IN ({lista})")[0])


def publicados(orden_ids):
    lista = ",".join(str(i) for i in orden_ids)
    return int(psql(f"SELECT count(*) FROM ordenes.outbox_evento WHERE publicado AND aggregate_id IN ({lista})")[0])


def correcciones(provs):
    p = provs[0]
    precio = lambda sku=101: http("GET", f"/catalogo/precio?proveedor_id={p}&sku_id={sku}")

    print("\n[12] Correcciones (fase 4) en caliente")
    kill_switch()
    poner_correcciones([])
    c, r, _, _ = http("PUT", "/admin/correcciones", {"activas": ["cache"]})
    check(c == 422, f"corrección desconocida -> 422 ({c})")

    print("\n[12a] catalogo: timeout 200 ms + breaker + último precio conocido")
    poner_correcciones(["catalogo"])
    for _ in range(6):                    # calienta la caché de precios en ambas réplicas
        precio()
    activar({"id": "A1", "probabilidad": 1.0, "duracion_s": 90})
    res = [precio() for _ in range(6)]
    check(all(x[0] == 200 for x in res) and max(x[3] for x in res) < 400,
          f"con A1 (800 ms) el precio conocido sale en < 400 ms: {[(x[0], round(x[3])) for x in res]}")
    c, r, _, ms = precio(sku=987654)
    check(c == 503 and ms < 400 and isinstance(r, dict) and r.get("dependencia") == "catalogo",
          f"SKU sin precio conocido -> 503 inmediato ({c}, {ms:.0f} ms)")
    for _ in range(10):                   # >= 5 fallos seguidos por réplica abren el breaker
        precio()
    vistos = breakers_en_replicas()
    check(vistos == {"api-1": "abierto", "api-2": "abierto"}, f"breaker de catálogo abierto en ambas réplicas: {vistos}")
    lat = [precio()[3] for _ in range(4)]
    check(max(lat) < 100, f"con el breaker abierto no se llama a Catálogo: {[round(x) for x in lat]} ms")
    check(bool(esperar(lambda: prom('sum(catalogo_fallback_total{resultado="hit"}) > 0') and
                       prom('max(circuit_breaker_estado{nombre="catalogo"}) == 2'), 15, 1)),
          "Prometheus: catalogo_fallback_total y circuit_breaker_estado = 2")
    kill_switch()
    poner_correcciones([])
    lat = [precio()[3] for _ in range(4)]
    check(max(lat) < 400, f"corrección apagada: el precio vuelve al camino de siempre {[round(x) for x in lat]} ms")

    print("\n[12b] bulkhead: lecturas aisladas de escrituras lentas, fail-fast 500 ms")
    poner_correcciones(["bulkhead"])
    activar({"id": "SMK", "tipo": "latencia_fija", "target": "logistica.reservar_franja", "ms_fijos": 2000,
             "probabilidad": 1.0, "duracion_s": 60})
    with ThreadPoolExecutor(40) as ex:
        escrituras = [ex.submit(http, "POST", "/ordenes", {"proveedor_id": provs[i % len(provs)], "cedi_id": 3, "total": 5})
                      for i in range(20)]
        time.sleep(0.3)
        lecturas = [ex.submit(http, "GET", f"/proveedores/{p}/ordenes") for _ in range(10)]
        escrituras = [f.result() for f in escrituras]
        lecturas = [f.result() for f in lecturas]
    rechazos = [x for x in escrituras if x[0] == 503]
    check(rechazos and all(x[3] < 1500 for x in rechazos) and any(x[0] == 201 for x in escrituras),
          f"POST: {len(rechazos)}/20 con 503 fail-fast (máx {max((x[3] for x in rechazos), default=0):.0f} ms), resto 201")
    check(all(x[0] == 200 for x in lecturas) and max(x[3] for x in lecturas) < 1000,
          f"GET Q5 durante las escrituras lentas: {sorted({x[0] for x in lecturas})}, máx {max(x[3] for x in lecturas):.0f} ms")
    pools = {x["metric"].get("pool") for x in prom('db_pool_max{job="api"}')}
    check({"general", "lectura", "escritura"} <= pools, f"Prometheus: db_pool_* por pool {sorted(p_ for p_ in pools if p_)}")
    kill_switch()

    print("\n[12c] bulkhead: lock_timeout de 1 s frente a B2")
    activar({"id": "B2", "duracion_s": 60, "parametros": {"cedi_id": 5, "retencion_s": 60, "ciclo_s": 120}})
    time.sleep(1)
    c, r, _, ms = http("POST", "/ordenes", {"proveedor_id": p, "cedi_id": 5, "total": 1})
    check(c == 503 and 900 <= ms < 2500 and "lock_timeout" in str(r), f"POST al CEDI bloqueado -> {c} en {ms:.0f} ms (lock_timeout)")
    kill_switch()
    c, _, _, ms = http("POST", "/ordenes", {"proveedor_id": p, "cedi_id": 5, "total": 1})
    check(c == 201, f"tras kill switch el CEDI 5 acepta órdenes ({c}, {ms:.0f} ms)")
    poner_correcciones([])

    print("\n[12d] worker: reintentos con backoff, mensajes muertos, sin head-of-line blocking")
    poner_correcciones(["worker"])
    claves = [f"smoke-{time.time():.0f}-{i}" for i in range(400)]
    envenenada = next(k for k in claves if afectada("D2", k, 0.5))
    sanas = [k for k in claves if not afectada("D2", k, 0.5)][:4]
    activar({"id": "D2", "probabilidad": 0.5, "ms_fijos": 50, "duracion_s": 90})
    ids = []
    for k in [envenenada] + sanas:        # la envenenada queda a la cabeza del outbox
        c, r, _, _ = http("POST", "/ordenes", {"proveedor_id": p, "cedi_id": 1, "total": 1}, cabeceras={"X-Clave-Carga": k})
        ids.append(r["orden_id"])
    check(bool(esperar(lambda: publicados(ids[1:]) == 4, 15)), f"las 4 órdenes sanas se publican detrás de la envenenada")
    check(bool(esperar(lambda: muertos(ids[:1]) == 1, 15)), f"la envenenada (orden {ids[0]}) termina en outbox_muerto")
    n = int(psql(f"SELECT intentos FROM ordenes.outbox_muerto WHERE aggregate_id = {ids[0]}")[0])
    check(n == 3, f"intentos registrados del mensaje muerto: {n}")
    check(bool(esperar(lambda: prom("sum(outbox_reintentos_total) > 0") and prom("max(outbox_mensajes_muertos) > 0"), 15, 1)),
          "Prometheus: outbox_reintentos_total y outbox_mensajes_muertos")

    print("\n[12e] worker: circuit breaker hacia ext-sap")
    activar({"id": "D2", "probabilidad": 1.0, "ms_fijos": 50, "duracion_s": 90})
    ids = [r[1]["orden_id"] for r in crear_ordenes(provs, 6) if r[0] == 201]
    check(bool(esperar(lambda: prom('max(circuit_breaker_estado{nombre="ext_sap"}) == 2'), 20, 1)),
          "breaker ext_sap abierto tras 5 fallos seguidos")
    check(muertos(ids) < len(ids), f"con el breaker abierto no se gastan intentos: {muertos(ids)}/{len(ids)} muertos")
    kill_switch()
    poner_correcciones(["worker"], "smoke-reinicio")   # nueva corrida: breaker reiniciado
    check(bool(esperar(lambda: publicados(ids) + muertos(ids) == len(ids) and pendientes() == 0, 20)),
          "tras kill switch y reinicio del breaker el outbox se vacía")
    poner_correcciones([])


PROMETHEUS = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
JAEGER = os.environ.get("JAEGER_URL", "http://localhost:16686")
GRAFANA = os.environ.get("GRAFANA_URL", "http://localhost:3000")


if __name__ == "__main__":
    main()
