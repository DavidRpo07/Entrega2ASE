# A2 — Jitter lognormal en Logística (μ=5,5, σ=1,0)

Estado: LISTA

**Para la tabla:** p50 ≈ 250 ms, p99 ≈ 2,5 s (cola lognormal); errores < 1 %

**Hipótesis:** Si todas las reservas de franja suman un retraso lognormal, la cola se alarga mucho más que la mediana, porque con σ=1 los percentiles altos quedan muy lejos del centro (p50 ≈ 245 ms, p99 ≈ 2,5 s).

**Predicción:**
- POST: p50 ≈ 250 ms, p95 ≈ 1,3 s, p99 ≈ 2,5 s; lecturas sin cambio.
- Errores < 1 % (sin timeout); algo de espera por pool en ráfagas.
- Si el retraso cayera después del UPDATE de Q3, los locks del día amplificarían la cola (p99 > 5 s). Apostamos a que no.
- Recuperación < 3 s.

