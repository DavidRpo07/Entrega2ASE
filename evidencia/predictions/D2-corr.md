# D2 corregido — retry con backoff + mensajes muertos + circuit breaker hacia ext-sap

Estado: PENDIENTE

> Corrección `worker` de `lab/correcciones.yaml`. Se compara contra la corrida sin corregir
> `D2_20261016T233309Z` (predicción `D2.md`): misma falla, misma semilla, misma carga.
> Corrida: `make experimento ID=D2 CORRECCION=on`. Antes de correr: escribir la predicción, cambiar a `Estado: LISTA` y hacer commit.

**Falla:** Falla D2 sin cambios: ext-sap tarda 2 s y responde 503 en el 40 % de las llamadas (decisión por clave), semilla 42.

**Corrección aplicada (toda la corrida, también el baseline):**
- Retry: un evento que falla se reprograma con backoff 100 · 2^(n−1) ms + hasta 50 % de jitter (determinista por `outbox_id`) y el worker sigue con los demás eventos del lote.
- Máximo 3 intentos; al 3.er fallo el evento pasa a `ordenes.outbox_muerto`.
- Circuit breaker hacia ext-sap: abre tras 5 fallos consecutivos, semiabierto a los 30 s; abierto, corta el lote sin gastar intentos.

**Para la tabla:**

**Hipótesis:**

**Predicción:**
-
