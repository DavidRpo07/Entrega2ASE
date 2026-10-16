# C1 — CPU saturada en api-1 (2 hilos al 90 %)

Estado: LISTA

**Para la tabla:** Solo api-1 se degrada (GIL); p95 global ≈ 100 ms, sin errores

**Hipótesis:** Si dos hilos queman CPU dentro de api-1, esa réplica se vuelve lenta aunque la máquina tenga núcleos libres, porque en Python los hilos compiten por el GIL y cada petición espera su turno.

**Predicción:**
- api-1: p50 20–40 ms, p95 60–120 ms; api-2 sin cambio.
- Global: p95 ≈ 60–120 ms, en el límite del SLO; 0 % errores.
- CPU de api-1 ≈ 180 % de un núcleo, host sin saturar.
- Recuperación inmediata.


