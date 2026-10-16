# A1 — Latencia fija en Catálogo (+800 ms, 30 %)

Estado: LISTA

> Nota: antes de escribir esta ficha vimos una corrida de prueba de 30 s del runner con A1 (p95 ≈ 814 ms).

**Para la tabla:** p50 sin cambio; p95/p99 ≈ +800 ms; 0 % errores

**Hipótesis:** Si el 30 % de las llamadas a Catálogo tarda 800 ms más, la cola de latencia sube ~800 ms pero la mediana casi no cambia, porque solo una de cada tres peticiones es lenta y no hay timeout que la corte.

**Predicción:**
- p50 POST sin cambio (6–10 ms); p95 y p99 ≈ 810–840 ms (rompe el SLO de 100 ms).
- Promedio ≈ 250 ms: no describe a ninguna petición real.
- 0 % de errores; throughput y lag del outbox sin cambio.
- Ambas réplicas igual de afectadas; recuperación < 1 s.


