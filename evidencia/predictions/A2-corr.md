# A2 corregido — bulkhead lectura/escritura + fail-fast + lock_timeout

Estado: PENDIENTE

> Corrección `bulkhead` de `lab/correcciones.yaml`. Se compara contra la corrida sin corregir
> `A2_20261016T211219Z` (predicción `A2.md`): misma falla, misma semilla, misma carga.
> Corrida: `make experimento ID=A2 CORRECCION=on`. Antes de correr: escribir la predicción, cambiar a `Estado: LISTA` y hacer commit.

**Falla:** Falla A2 sin cambios: jitter lognormal (mu 5,5, sigma 1,0, máx 10 s) en `logistica.reservar_franja`, 100 %, semilla 42.

**Corrección aplicada (toda la corrida, también el baseline):**
- Pools separados por réplica: escritura 3 (POST /ordenes) + lectura 2 (GET), mismo total de 5.
- Espera máxima por conexión: 500 ms (fail-fast → 503).
- `lock_timeout` de 1 s en la transacción de POST /ordenes.

**Para la tabla:**

**Hipótesis:**

**Predicción:**
-
