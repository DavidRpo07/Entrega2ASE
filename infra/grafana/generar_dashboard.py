"""Genera infra/grafana/dashboards/laboratorio.json (el dashboard se versiona como JSON;
este script es su fuente). Los umbrales salen de lab/slo.yaml.
Uso (con el venv activo, necesita pyyaml):  python3 infra/grafana/generar_dashboard.py
"""
import json
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "infra" / "grafana" / "dashboards" / "laboratorio.json"
SLO = yaml.safe_load((RAIZ / "lab" / "slo.yaml").read_text(encoding="utf-8"))["slo"]
P95, P99 = SLO["p95_post_ms"], SLO["p99_post_ms"]
ERR = SLO["errores_pct"] / 100.0
VENTANA_ERR = f'{SLO["ventana_errores_s"]}s'
LAG = SLO["lag_outbox_s"]
DS = {"type": "prometheus", "uid": "prometheus"}
pid = [0]


def fusionar(dst, src):
    """Mezcla profunda: los extras no deben borrar unidad/opciones ya puestas."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            fusionar(dst[k], v)
        else:
            dst[k] = v
    return dst


def panel(title, exprs, x, y, w=12, h=8, kind="timeseries", unit="short", desc="", extra=None, legend=None):
    pid[0] += 1
    targets = [{"datasource": DS, "expr": e, "legendFormat": l, "refId": chr(65 + i)} for i, (e, l) in enumerate(exprs)]
    p = {"id": pid[0], "type": kind, "title": title, "description": desc, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
         # "sin datos" en vez de un valor viejo cuando la serie no tiene tráfico
         "fieldConfig": {"defaults": {"unit": unit, "noValue": "sin datos"}, "overrides": []}, "options": {}}
    if kind == "timeseries":
        p["fieldConfig"]["defaults"]["custom"] = {"lineWidth": 1, "fillOpacity": 8, "showPoints": "never"}
        p["options"] = {"legend": {"displayMode": "table", "placement": "bottom", "calcs": legend or ["last", "max"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}}
    if kind == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["last"]}, "colorMode": "background", "graphMode": "area"}
    if extra:
        fusionar(p, extra)
    return p
def row(title, y):
    pid[0] += 1
    return {"id": pid[0], "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}

R = '$__rate_interval'
H = 'http_peticion_duracion_segundos'
API = 'job="api"'
SEL = API + ',metodo=~"$metodo",ruta=~"$ruta"'
q = lambda p, s: f'1000 * histogram_quantile({p}, sum by (le) (rate({H}_bucket{{{s}}}[{R}])))'
umbral = lambda verde_hasta, rojo: {"fieldConfig": {"defaults": {"thresholds": {"mode": "absolute", "steps": [
    {"color": "green", "value": None}, {"color": "orange", "value": verde_hasta}, {"color": "red", "value": rojo}]}}}}
# Línea punteada del SLO en series de tiempo.
linea_slo = lambda *pasos: fusionar(umbral(*pasos), {"fieldConfig": {"defaults": {"custom": {"thresholdsStyle": {"mode": "dashed"}}}}})
ERRORES = lambda por="": (f'sum{por} (rate({H}_count{{{API},codigo=~"5.."}}[{VENTANA_ERR}])) / '
                          f'clamp_min(sum{por} (rate({H}_count{{{API}}}[{VENTANA_ERR}])), 1e-9)')
# cAdvisor (cgroups en crudo) unido con contenedor_info para tener el nombre del servicio.
CAD = lambda m: f'sum by (servicio) ({m} * on (id) group_left (servicio) contenedor_info{{proyecto="$proyecto"}})'

panels = [
  row("Resumen (API detrás de nginx)", 0),
  panel("Throughput", [(f'sum(rate({H}_count{{{API}}}[{R}]))', "req/s")], 0, 1, 4, 4, "stat", "reqps"),
  panel(f"Errores 5xx (ventana {VENTANA_ERR})", [(ERRORES(), "5xx")],
        4, 1, 4, 4, "stat", "percentunit", desc=f"SLO: < {SLO['errores_pct']} % por ventana de {VENTANA_ERR}.",
        extra=umbral(ERR / 2, ERR)),
  panel("p95 $metodo $ruta", [(q(0.95, SEL), "p95")], 8, 1, 4, 4, "stat", "ms",
        desc=f"SLO (POST /ordenes): p95 ≤ {P95} ms.", extra=umbral(0.8 * P95, P95)),
  panel("p99 $metodo $ruta", [(q(0.99, SEL), "p99")], 12, 1, 4, 4, "stat", "ms",
        desc=f"SLO (POST /ordenes): p99 ≤ {P99} ms.", extra=umbral(0.8 * P99, P99)),
  panel("Lag del outbox", [('max(outbox_lag_segundos)', "lag")], 16, 1, 4, 4, "stat", "s",
        desc=f"SLO: < {LAG} s.", extra=umbral(LAG / 2, LAG)),
  panel("Fallas activas", [('count(count by (falla_id) (falla_activa == 1)) or vector(0)', "activas")], 20, 1, 4, 4, "stat", "short",
        extra=umbral(1, 1)),

  row("Latencia y errores", 5),
  panel("Latencia $metodo $ruta — p50 / p95 / p99", [(q(0.50, SEL), "p50"), (q(0.95, SEL), "p95"), (q(0.99, SEL), "p99")],
        0, 6, 12, 9, unit="ms", extra=linea_slo(P95, P99),
        desc=f"Cuantiles del histograma (ambas réplicas). Líneas: SLO p95 {P95} ms y p99 {P99} ms (aplican a POST /ordenes)."),
  panel("p95 por réplica — $metodo $ruta", [(f'1000 * histogram_quantile(0.95, sum by (le, instancia) (rate({H}_bucket{{{SEL}}}[{R}])))', "{{instancia}}")],
        12, 6, 12, 9, unit="ms", extra=linea_slo(P95, P99), desc="Permite ver C1 (solo api-1) y D1 (api-2 caída)."),
  panel("Peticiones/s por código", [(f'sum by (codigo) (rate({H}_count{{{API}}}[{R}]))', "{{codigo}}")], 0, 15, 12, 8, unit="reqps"),
  panel(f"% errores 5xx por réplica (ventana {VENTANA_ERR})", [(ERRORES(" by (instancia)"), "{{instancia}}")],
        12, 15, 12, 8, unit="percentunit", extra=linea_slo(ERR, ERR),
        desc="Visto por la API. Los 502 de nginx (réplica caída) no llegan aquí: ver k6 y el log de nginx."),

  row("Pool de conexiones (psycopg_pool, max 5 por réplica)", 23),
  panel("Conexiones en uso vs máximo", [('db_pool_conexiones{job="api",estado="en_uso"}', "en uso {{instancia}}"),
                                        ('db_pool_max{job="api"}', "max {{instancia}}")], 0, 24, 8, 8),
  panel("Peticiones esperando conexión", [('db_pool_esperando{job="api"}', "{{instancia}}")], 8, 24, 8, 8),
  panel("Espera por conexión p95 y timeouts/s", [(f'1000 * histogram_quantile(0.95, sum by (le, instancia) (rate(db_pool_espera_segundos_bucket{{{API}}}[{R}])))', "p95 espera {{instancia}}"),
                                                 (f'rate(db_pool_timeouts_total{{{API}}}[{R}])', "timeouts/s {{instancia}}")], 16, 24, 8, 8, unit="ms",
        extra={"fieldConfig": {"overrides": [{"matcher": {"id": "byRegexp", "options": "timeouts.*"},
               "properties": [{"id": "unit", "value": "reqps"}, {"id": "custom.axisPlacement", "value": "right"}]}]}}),

  row("Outbox → worker → ext-sap", 32),
  panel("Outbox: pendientes y lag", [('outbox_pendientes', "pendientes"), ('outbox_lag_segundos', "lag (s)")], 0, 33, 8, 8,
        extra={"fieldConfig": {"overrides": [{"matcher": {"id": "byName", "options": "lag (s)"},
               "properties": [{"id": "unit", "value": "s"}, {"id": "custom.axisPlacement", "value": "right"}]}]}}),
  panel("Publicados y fallos por segundo", [(f'sum(rate(outbox_publicados_total{{job="worker"}}[{R}]))', "publicados"),
                                            (f'sum by (motivo) (rate(outbox_fallos_total[{R}]))', "fallo {{motivo}}"),
                                            ('worker_pausado', "worker pausado (C2)")], 8, 33, 8, 8),
  panel("Llamadas a ext-sap — p95 por resultado", [(f'1000 * histogram_quantile(0.95, sum by (le, resultado) (rate(ext_sap_llamada_duracion_segundos_bucket[{R}])))', "{{resultado}}")],
        16, 33, 8, 8, unit="ms"),

  row("Fallas inyectadas", 41),
  {**panel("falla_activa (cualquier proceso)", [('max by (falla_id) (falla_activa)', "{{falla_id}}")], 0, 42, 12, 8, "state-timeline"),
   "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8},
   "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [
       {"color": "transparent", "value": None}, {"color": "red", "value": 1}]}}, "overrides": []}},
  panel("Inyecciones por segundo", [(f'sum by (falla_id) (rate(fallas_inyectadas_total[{R}]))', "{{falla_id}}")], 12, 42, 6, 8),
  {**panel("Efectos de fallas externas (fallas-ext)", [('max by (falla_id, efecto) (falla_externa_efecto)', "{{falla_id}} {{efecto}}")],
           18, 42, 6, 8, "state-timeline", desc="B2: lock FOR UPDATE retenido. D1: servicio detenido."),
   "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8},
   "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [
       {"color": "transparent", "value": None}, {"color": "purple", "value": 1}]}}, "overrides": []}},

  row("PostgreSQL (postgres-exporter)", 50),
  panel("Conexiones por estado", [('sum by (state) (pg_stat_activity_count{datname="escalables"})', "{{state}}")], 0, 51, 8, 8),
  panel("Locks por modo", [('sum by (mode) (pg_locks_count{datname="escalables"})', "{{mode}}")], 8, 51, 8, 8,
        desc="B2 (SELECT … FOR UPDATE retenido) se ve en RowShareLock / ExclusiveLock."),
  panel("Transacciones/s", [(f'rate(pg_stat_database_xact_commit{{datname="escalables"}}[{R}])', "commit"),
                            (f'rate(pg_stat_database_xact_rollback{{datname="escalables"}}[{R}])', "rollback"),
                            (f'rate(pg_stat_database_deadlocks{{datname="escalables"}}[{R}])', "deadlocks")], 16, 51, 8, 8),

  row("Recursos por proceso (Python)", 59),
  panel("CPU por proceso", [(f'rate(process_cpu_seconds_total{{job=~"api|worker|ext-sap"}}[{R}])', "{{instancia}}")], 0, 60, 8, 8,
        unit="percentunit", desc="1.0 = un núcleo. C1 debe subir solo api-1."),
  panel("Memoria residente por proceso", [('process_resident_memory_bytes{job=~"api|worker|ext-sap|fallas-ext"}', "{{instancia}}")],
        8, 60, 8, 8, unit="bytes"),
  panel("GC: colecciones/s por generación", [(f'sum by (instancia, generation) (rate(python_gc_collections_total{{job=~"api|worker|ext-sap"}}[{R}]))',
                                              "{{instancia}} gen{{generation}}")], 16, 60, 8, 8,
        desc="Recolecciones del GC de CPython; una subida con latencia alta apunta a presión de memoria."),

  row("Correcciones (fase 4: lab/correcciones.yaml)", 77),
  {**panel("Corrección activa", [('min by (correccion) (correccion_activa{job=~"api|worker"})', "{{correccion}}")], 0, 78, 8, 8, "state-timeline",
           desc="1 = encendida en api-1, api-2 y worker (min entre procesos)."),
   "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8},
   "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [
       {"color": "transparent", "value": None}, {"color": "green", "value": 1}]}}, "overrides": []}},
  {**panel("Circuit breakers (0 cerrado · 1 semiabierto · 2 abierto)", [('max by (instancia, nombre) (circuit_breaker_estado)', "{{nombre}} {{instancia}}")],
           8, 78, 8, 8, "state-timeline", desc="catalogo: por réplica (A1). ext_sap: en el worker (D2)."),
   "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8},
   "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [
       {"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 2}]}}, "overrides": []}},
  panel("Catálogo: timeouts y fallback/s", [(f'sum(rate(catalogo_timeouts_total[{R}]))', "timeouts"),
                                           (f'sum by (motivo, resultado) (rate(catalogo_fallback_total[{R}]))', "fallback {{motivo}} {{resultado}}"),
                                           (f'sum by (nombre) (rate(circuit_breaker_rechazos_total[{R}]))', "rechazos breaker {{nombre}}")],
        16, 78, 8, 8, unit="reqps", desc="hit = último precio conocido; miss = 503 inmediato."),
  panel("Bulkhead: conexiones en uso por pool", [('sum by (instancia, pool) (db_pool_conexiones{job="api",estado="en_uso"})', "{{pool}} {{instancia}}"),
                                                ('sum by (instancia, pool) (db_pool_esperando{job="api"})', "esperando {{pool}} {{instancia}}")], 0, 86, 8, 8),
  panel("Bulkhead: fail-fast y lock_timeout/s", [(f'sum by (pool) (rate(db_pool_timeouts_total{{{API}}}[{R}]))', "pool timeout {{pool}}"),
                                                (f'sum(rate(db_lock_timeouts_total[{R}]))', "lock_timeout")], 8, 86, 8, 8, unit="reqps"),
  panel("Worker: reintentos, muertos y diferidos", [(f'sum(rate(outbox_reintentos_total[{R}]))', "reintentos/s"),
                                                    (f'sum(rate(outbox_muertos_total[{R}]))', "a muertos/s"),
                                                    (f'sum(rate(outbox_breaker_diferidos_total[{R}]))', "lotes cortados por breaker/s"),
                                                    ('max(outbox_mensajes_muertos)', "en outbox_muerto")], 16, 86, 8, 8,
        extra={"fieldConfig": {"overrides": [{"matcher": {"id": "byName", "options": "en outbox_muerto"},
               "properties": [{"id": "custom.axisPlacement", "value": "right"}]}]}}),

  row("Contenedores (cAdvisor)", 68),
  panel("CPU por contenedor", [(CAD(f'rate(container_cpu_usage_seconds_total{{id=~"/docker/.+"}}[{R}])'), "{{servicio}}")],
        0, 69, 12, 8, unit="percentunit", desc="Incluye postgres, nginx y la observabilidad (su costo)."),
  panel("Memoria por contenedor (working set)", [(CAD('container_memory_working_set_bytes{id=~"/docker/.+"}'), "{{servicio}}")],
        12, 69, 12, 8, unit="bytes"),
]

def var(name, query, default):
    return {"name": name, "type": "query", "datasource": DS, "query": {"query": query, "refId": name},
            "definition": query, "refresh": 2, "includeAll": False, "multi": False,
            "current": {"text": default, "value": default}, "sort": 1}

dash = {
  "uid": "lab-entregable3", "title": "Laboratorio de fallas — Entregable 3", "tags": ["entregable3"],
  "timezone": "browser", "schemaVersion": 39, "version": 1, "refresh": "5s",
  "time": {"from": "now-15m", "to": "now"},
  "templating": {"list": [var("proyecto", 'label_values(contenedor_info, proyecto)', "proyectoase"),
                          var("metodo", 'label_values(http_peticion_duracion_segundos_count{job="api"}, metodo)', "POST"),
                          var("ruta", 'label_values(http_peticion_duracion_segundos_count{job="api", metodo=~"$metodo"}, ruta)', "/ordenes")]},
  "annotations": {"list": [
    {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": True,
     "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"},
    {"datasource": DS, "enable": True, "iconColor": "red", "name": "Falla activa",
     "expr": "max by (falla_id) (falla_activa) > 0", "step": "10s", "titleFormat": "Falla {{falla_id}}",
     "textFormat": "activa", "useValueForTime": False}]},
  "panels": panels,
}
SALIDA.write_text(json.dumps(dash, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"{len(panels)} paneles → {SALIDA}")
