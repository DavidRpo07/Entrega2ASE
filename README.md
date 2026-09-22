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
