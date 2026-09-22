# Evidencia reproducible

`make datos` produce `generacion.csv` (filas, tamaño, semilla y duración total)
y `carga.csv` (una fila por `COPY` y una fila de tiempo total).

`make medir` agrega los CSV crudos de Q1--Q5: una fila por ejecución, con
parámetros, escenario y latencia en milisegundos.

La Fase 4 del modulith deja `fase4_modulith_operaciones.csv` (una fila por
orden transaccional) y `fase4_modulith_resumen.csv` (resultado agregado).
