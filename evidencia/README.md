# Evidencia de los experimentos (Entregable 3)

Cada corrida de `make experimento ID=<ID>` crea `<ID>_<UTC>` en cada carpeta:

| Carpeta | Contenido |
| --- | --- |
| `predictions/` | `<ID>.md`: predicción escrita **antes** de correr (el runner exige `Estado: LISTA` y registra su sha256 y commit) |
| `experiments/<RUN>/` | `manifest.json` (configuración aplicada, fases, marcas UTC, commit, carga y su sha256, entorno) y copia de la predicción usada |
| `baseline/<RUN>/` | métricas del cliente (k6) en la fase baseline |
| `metrics/<RUN>/` | `peticiones.csv.gz` (una fila por petición: ts de inicio, op, clave, status, ms), `k6_resumen.json`, `prometheus/*.csv` (series cada 5 s) |
| `logs/<RUN>/` | logs JSON por servicio (`*.jsonl.gz`, con `trace_id`), nginx (upstream/status), `runner.jsonl` (marcas y muestras), `inyecciones.csv` (cada inyección con su clave) |
| `traces/<RUN>/` | trazas de Jaeger (`*.json.gz`, formato de su API; se abren en Jaeger UI → JSON File): muestra del baseline, las más lentas y las con error durante la falla, muestra de la recuperación; `indice.csv` |
| `results/<RUN>/` | `resumen.md` / `resumen.json`: por fase, cumplimiento del SLO, tiempo de recuperación y tabla predicción vs. resultado (la completa el equipo) |
| `momento1/` | `manifest.json` (`make momento1`): volumen canónico del E2 (filas por entidad del informe, de los CSV y de la base), semilla y parámetros del generador, checksum SHA-256 de los 11 CSV frente al del E2, versión y ajustes de PostgreSQL, índices, commit y entorno |
| `linea_base/<UTC>/` | `make linea-base`: recarga la base y mide con las mismas cargas del E2 (Q1–Q5 frío/caliente con `datos/medir_q*.py`, Fase 4 con las mismas 5.000 órdenes); `tabla.md` / `resumen.json` = E2 (informe) vs. E3 vs. objetivo 0,90 × E2; CSV crudos, logs con EXPLAIN, `carga.csv` y `manifest.json`. `diagnostico_fase4_<UTC>/`: corridas de la Fase 4 en otros estados de la base |
| `figuras/` | `<ID>.png` por experimento (`make figuras`, `lab/experimentos/figuras.py`): p95/p99 de POST y % de errores (ventana de 60 s) en el tiempo con las fases y el SLO; antes/después en la misma figura cuando hay corrección; lag del outbox en C2 y D2 |

Fase 4: `make experimento ID=<ID> CORRECCION=on` crea `<ID>-corr_<UTC>` (sin ficha de predicción) con la
misma falla y semilla que `<ID>_<UTC>`; el manifest guarda las correcciones aplicadas. El experimento de
overhead O1 crea `O1-trazas-on_<UTC>` y `O1-trazas-off_<UTC>` (sin ficha de predicción). Cualquier corrida hecha con
`TRAZAS=off` lleva `-trazas-off` en el nombre.

Las corridas `PRUEBA-*` (`make experimento-prueba`) son ensayos del runner: git las ignora y
`make limpiar-pruebas` las borra.
