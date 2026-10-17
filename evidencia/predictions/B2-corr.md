# B2 corregido — bulkhead lectura/escritura + fail-fast + lock_timeout

Estado: PENDIENTE

> Corrección `bulkhead` de `lab/correcciones.yaml`. Se compara contra la corrida sin corregir
> `B2_20261016T224212Z` (predicción `B2.md`): misma falla, misma semilla, misma carga.
> Corrida: `make experimento ID=B2 CORRECCION=on`. Antes de correr: escribir la predicción, cambiar a `Estado: LISTA` y hacer commit.

**Falla:** Falla B2 sin cambios: `SELECT … FOR UPDATE` retenido 30 s cada 60 s sobre las franjas del CEDI 5, semilla 42.

**Corrección aplicada (toda la corrida, también el baseline):**
- Pools separados por réplica: escritura 3 (POST /ordenes) + lectura 2 (GET), mismo total de 5.
- Espera máxima por conexión: 500 ms (fail-fast → 503).
- `lock_timeout` de 1 s en la transacción de POST /ordenes.

**Para la tabla:**

**Hipótesis:**

**Predicción:**
-
