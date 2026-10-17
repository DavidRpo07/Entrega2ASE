# A2-corr-INVALIDA_20261017T003353Z — corrida inválida (id original `A2-corr_20261017T003353Z`)

**Motivo: OOM de Jaeger en plena falla.** El contenedor `jaeger` (all-in-one, almacenamiento en memoria
**sin límite**) fue matado por falta de memoria (`OOMKilled=true`, código 137) a las **00:41:14 UTC**, unos 2 min
después de activar la falla (00:39:05). Llevaba 6,5 h encendido y ocupaba ~6,8 GB de los 7,75 GiB de la VM de
Docker (serie `memoria_por_contenedor_bytes`, `servicio=jaeger`). La carga terminó (k6 código 0) y el runner
apagó las correcciones, pero al recolectar evidencia la consulta a Jaeger falló (`Connection refused`) y el runner
salió con código 2 sin escribir `resumen.md`, el manifest ni el baseline.

No se analiza: la presión de memoria en la VM durante la falla puede haber afectado latencias, y faltan las
trazas desde las 00:41. Se conserva lo que alcanzó a guardarse: `logs/` (incluido `runner.jsonl`) y `metrics/`
(`peticiones.csv.gz` de k6 y series de Prometheus).

Corrección aplicada al laboratorio: Jaeger con `MEMORY_MAX_TRACES=20000` y `mem_limit: 1536m` (`compose.yaml`).
La corrida se repitió después con el límite. Ver `lab/NOTAS_SESION.md`.
