# Entregable 2 — Escalabilidad de datos

## Requisitos

- Docker Desktop con Docker Compose.
- Python 3.10 o superior.
- `make`.

Instale la dependencia de Python una única vez:

```bash
python3 -m pip install -r requirements.txt
```

## Ejecución reproducible

Desde la raíz del repositorio:

```bash
make datos
```

El comando levanta PostgreSQL 15 con Docker Compose, espera a que esté disponible,
genera los CSV con semilla `42`, recrea los esquemas, carga por `COPY`, ejecuta
`ANALYZE` y verifica volumen, sesgo, estacionalidad, casos borde y determinismo.

Resultados persistentes:

- `datos/resultados/generacion.csv`: filas, tamaños y tiempo de generación.
- `datos/resultados/carga.csv`: tiempo de cada `COPY` y total de carga.
- `datos/resultados/`: CSV crudos de mediciones y de la Fase 4 cuando se ejecuten.

Comandos adicionales:

```bash
make estrategias  # cuatro estrategias de inyección
make fase4        # ruta real del modulith: módulos y 5.000 órdenes incrementales
make medir        # Q1–Q5 y su evidencia CSV
```

Ejecute `make datos` antes de `make fase4`. La Fase 4 usa los módulos de
proveedores, catálogo, logística y órdenes, e incluye sus resultados en
`datos/resultados/fase4_modulith_operaciones.csv` y
`datos/resultados/fase4_modulith_resumen.csv`.

## Cómo reproducir el Entregable 3

Requisitos adicionales: `pip install -r requirements.txt` en `venv/` (el Makefile usa `venv/bin/python`
si existe) y Docker Desktop (medido con 10 CPU y 7,75 GiB); k6 corre en contenedor (`grafana/k6:0.55.0`). Detalle del laboratorio en
[`lab/README.md`](lab/README.md); bitácora y decisiones en [`lab/NOTAS_SESION.md`](lab/NOTAS_SESION.md).

### 1. Momento 1: punto de partida derivado del E2

```bash
make datos        # solo si no hay base: genera (semilla 42), carga y verifica
make momento1     # manifest: filas por entidad, semilla, parámetros, checksum SHA-256, Postgres, commit
```

Evidencia: `evidencia/momento1/manifest.json`. Valores de referencia del informe del E2 (con el método
de percentil de cada uno): `lab/momento1/referencia_e2.yaml`.

### 2. Línea base y tabla de objetivos (mismas cargas del E2)

```bash
make linea-base                   # baja el lab, recarga la base, Q1–Q5 frío/caliente y Fase 4 (5.000 órdenes)
make linea-base MEDIANA_Q1_Q3=on  # estado final: además Q1–Q3 tres veces (mediana)
venv/bin/python lab/momento1/linea_base.py comparar evidencia/linea_base/<BASE> evidencia/linea_base/<FINAL>
```

Evidencia: `evidencia/linea_base/<UTC>/` (`tabla.md`: E2 vs. E3 vs. objetivo 0,90 × E2; CSV crudos,
EXPLAIN en `consultas.log`, `manifest.json`). Línea base E3: `20261017T034200Z`; estado final:
`20261017T035415Z` con `tabla_final.md`. Optimizaciones (un commit cada una) y su aporte por paso:
`evidencia/optimizaciones/README.md`.

### 3. Laboratorio de fallas

```bash
make lab-up && make lab-smoke              # API, worker, ext-sap, nginx, Prometheus, Grafana, Jaeger
make experimento ID=A1                     # A1 A2 B1 B2 C1 C2 D1 D2 (exige evidencia/predictions/<ID>.md LISTA)
make experimento ID=B2 CORRECCION=on       # misma falla y semilla con la corrección de lab/correcciones.yaml
make experimento ID=O1                     # overhead de trazas; repetir tras `TRAZAS=off make lab-up`
make experimento ID=A1 RUNNER_ARGS="--baseline-s 120 --falla-s 180 --recuperacion-s 60 --etiqueta rep"
make figuras                               # evidencia/figuras/<ID>.png
```

Cada corrida: `make lab-reset` → baseline → falla → kill switch → recuperación (≈ 12 min), con
`caffeinate` y detector de reposo (aborta con código 3 si el Mac se suspende).

**Kill switch** (revierte toda falla sin redesplegar, incluidas B2 y D1):

```bash
curl -X DELETE localhost:8080/admin/faults        # o kill_switch: true en lab/runtime/faults.yaml
```

Las fallas se activan en caliente editando `lab/runtime/faults.yaml` (catálogo en
`lab/fallas/catalogo.yaml`) y las correcciones en `lab/runtime/correcciones.yaml`.

### Dónde queda la evidencia

| Qué | Dónde |
| --- | --- |
| Predicción previa de cada experimento | `evidencia/predictions/<ID>.md` |
| Corrida (`<RUN>` = `<ID>[-corr][-trazas-off][-rep]_<UTC>`) | `evidencia/{experiments,baseline,metrics,logs,traces,results}/<RUN>/` |
| Resumen por fase, SLO y recuperación | `evidencia/results/<RUN>/resumen.md` y `resumen.json` |
| Figuras por experimento (antes/después) | `evidencia/figuras/` |
| Momento 1, línea base, tabla final, optimizaciones | `evidencia/momento1/`, `evidencia/linea_base/`, `evidencia/optimizaciones/` |
| Estado de cada corrida (válidas, inválidas, repeticiones) | `lab/NOTAS_SESION.md` |
