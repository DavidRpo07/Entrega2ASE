# A1 corregido — timeout + circuit breaker + último precio en Catálogo

Estado: PENDIENTE

> Corrección `catalogo` de `lab/correcciones.yaml`. Se compara contra la corrida sin corregir
> `A1_20261016T205354Z` (predicción `A1.md`): misma falla, misma semilla, misma carga.
> Corrida: `make experimento ID=A1 CORRECCION=on`. Antes de correr: escribir la predicción, cambiar a `Estado: LISTA` y hacer commit.

**Falla:** Falla A1 sin cambios: +800 ms fijos en `catalogo.validar_sku`, 30 % de las llamadas, semilla 42.

**Corrección aplicada (toda la corrida, también el baseline):**
- Timeout de 200 ms sobre la espera a Catálogo (deadline del inyector).
- Circuit breaker por réplica: abre tras 5 fallos consecutivos, semiabierto a los 30 s (una llamada de prueba).
- Fallback: último precio conocido de (proveedor, sku) en la réplica; sin precio → 503 inmediato.

**Para la tabla:**

**Hipótesis:**

**Predicción:**
-
