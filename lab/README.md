# Laboratorio de fallas — Entregable 3

`lab/fallas/inyector.py` implementa las fallas configurables:

| Condición | Cómo se cumple |
| --- | --- |
| Sin redespliegue | `lab/faults.yaml` se relee cada segundo; `activar()` para `POST /admin/faults` |
| Parametrizada | `probabilidad`, `porcentaje_trafico`, `duracion_s`, intensidad (`ms_fijos`, `mu`/`sigma`, `codigo_http`, `hilos`, `carga_cpu`) |
| Focalizable | `target` por punto de falla (`catalogo.validar_sku`, `catalogo.*`, `api-1`) |
| Reversible | `kill_switch()` / `kill_switch: true` en el archivo / `DELETE /admin/faults` |
| Reproducible | `semilla` por falla; % de tráfico determinista por clave de petición |

- `lab/fallas/catalogo.yaml`: las 8 fallas (A1–D2) con sus parámetros.
- `lab/faults.yaml`: fallas activas (vacío por defecto).
- Tests: `make test-lab`.

## Uso en el modulith

```python
from lab.fallas.inyector import INYECTOR, FallaInyectada

INYECTOR.punto("catalogo.validar_sku", clave=str(orden_id))  # latencia/errores
if INYECTOR.pausado("worker.outbox"): ...                    # consumidor (C2)
```

Variables de entorno: `FAULTS_FILE` (ruta del YAML) e `INSTANCIA` (`api-1`, `api-2`).
B2 (bloqueo en BD) y D1 (caída de instancia) son de tipo `externa`: las ejecuta el runner
de experimentos y el inyector solo las registra.
