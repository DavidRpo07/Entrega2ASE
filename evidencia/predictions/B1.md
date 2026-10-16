# B1 — Pool de conexiones agotado (max 5, +300 ms por consulta)

Estado: LISTA

**Para la tabla:** 50–65 % de 503 por pool agotado; Postgres sano

**Hipótesis:** Si cada consulta retiene su conexión 300 ms más, un POST (~6 consultas) ocupa una conexión ~1,8 s y cada réplica solo puede atender ~2,8 POST/s de los ~7 que recibe; el resto hace fila hasta el timeout del pool.

**Predicción:**
- 50–65 % de POST con 503; las lecturas también fallan, en menor proporción.
- Exitosos: p50 ≈ 2–3 s; pool 5/5 en ambas réplicas, más de 20 en espera.
- Postgres con CPU baja: la base está sana mientras la aplicación falla.
- Recuperación 5–15 s.

