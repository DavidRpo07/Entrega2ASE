"""Genera infra/grafana/dashboards/laboratorio.json (el dashboard se versiona como JSON;
este script es su fuente). Uso:  python3 infra/grafana/generar_dashboard.py
"""
import json
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "dashboards" / "laboratorio.json"
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

panels = [
  row("Resumen (API detrás de nginx)", 0),
  panel("Throughput", [(f'sum(rate({H}_count{{{API}}}[{R}]))', "req/s")], 0, 1, 4, 4, "stat", "reqps"),
  panel("Errores 5xx", [(f'sum(rate({H}_count{{{API},codigo=~"5.."}}[{R}])) / clamp_min(sum(rate({H}_count{{{API}}}[{R}])), 1e-9)', "5xx")],
        4, 1, 4, 4, "stat", "percentunit", extra=umbral(0.01, 0.05)),
  panel("p95 $metodo $ruta", [(q(0.95, SEL), "p95")], 8, 1, 4, 4, "stat", "ms", extra=umbral(500, 2000)),
  panel("p99 $metodo $ruta", [(q(0.99, SEL), "p99")], 12, 1, 4, 4, "stat", "ms", extra=umbral(1000, 5000)),
  panel("Lag del outbox", [('max(outbox_lag_segundos)', "lag")], 16, 1, 4, 4, "stat", "s", extra=umbral(5, 30)),
  panel("Fallas activas", [('count(count by (falla_id) (falla_activa == 1)) or vector(0)', "activas")], 20, 1, 4, 4, "stat", "short",
        extra=umbral(1, 1)),

  row("Latencia y errores", 5),
  panel("Latencia $metodo $ruta — p50 / p95 / p99", [(q(0.50, SEL), "p50"), (q(0.95, SEL), "p95"), (q(0.99, SEL), "p99")],
        0, 6, 12, 9, unit="ms", desc="Cuantiles del histograma http_peticion_duracion_segundos (ambas réplicas)."),
  panel("p95 por réplica — $metodo $ruta", [(f'1000 * histogram_quantile(0.95, sum by (le, instancia) (rate({H}_bucket{{{SEL}}}[{R}])))', "{{instancia}}")],
        12, 6, 12, 9, unit="ms", desc="Permite ver C1 (solo api-1) y D1 (api-2 caída)."),
  panel("Peticiones/s por código", [(f'sum by (codigo) (rate({H}_count{{{API}}}[{R}]))', "{{codigo}}")], 0, 15, 12, 8, unit="reqps"),
  panel("% errores 5xx por réplica", [(f'sum by (instancia) (rate({H}_count{{{API},codigo=~"5.."}}[{R}])) / clamp_min(sum by (instancia) (rate({H}_count{{{API}}}[{R}])), 1e-9)', "{{instancia}}")],
        12, 15, 12, 8, unit="percentunit"),

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
  panel("CPU por proceso", [(f'rate(process_cpu_seconds_total{{job=~"api|worker|ext-sap"}}[{R}])', "{{instancia}}")], 18, 42, 6, 8,
        unit="percentunit", desc="1.0 = un núcleo. C1 debe subir solo api-1."),

  row("PostgreSQL (postgres-exporter)", 50),
  panel("Conexiones por estado", [('sum by (state) (pg_stat_activity_count{datname="escalables"})', "{{state}}")], 0, 51, 8, 8),
  panel("Locks por modo", [('sum by (mode) (pg_locks_count{datname="escalables"})', "{{mode}}")], 8, 51, 8, 8,
        desc="B2 (SELECT … FOR UPDATE retenido) se ve en RowShareLock / ExclusiveLock."),
  panel("Transacciones/s", [(f'rate(pg_stat_database_xact_commit{{datname="escalables"}}[{R}])', "commit"),
                            (f'rate(pg_stat_database_xact_rollback{{datname="escalables"}}[{R}])', "rollback"),
                            (f'rate(pg_stat_database_deadlocks{{datname="escalables"}}[{R}])', "deadlocks")], 16, 51, 8, 8),
]

def var(name, query, default):
    return {"name": name, "type": "query", "datasource": DS, "query": {"query": query, "refId": name},
            "definition": query, "refresh": 2, "includeAll": False, "multi": False,
            "current": {"text": default, "value": default}, "sort": 1}

dash = {
  "uid": "lab-entregable3", "title": "Laboratorio de fallas — Entregable 3", "tags": ["entregable3"],
  "timezone": "browser", "schemaVersion": 39, "version": 1, "refresh": "5s",
  "time": {"from": "now-15m", "to": "now"},
  "templating": {"list": [var("metodo", 'label_values(http_peticion_duracion_segundos_count{job="api"}, metodo)', "POST"),
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
