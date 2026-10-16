# C2 — Consumidor del outbox pausado 3 min

Estado: LISTA

**Para la tabla:** API sin cambio; lag del outbox ≈ 180 s; drena en ~30 s

**Hipótesis:** Si el worker se pausa, el usuario no nota nada en la API pero las confirmaciones se acumulan, porque el outbox desacopla el registro de la orden de su envío a SAP: es una falla silenciosa.

**Predicción:**
- POST: latencia y errores sin cambio.
- Pendientes ≈ 2.500 y lag ≈ 180 s al final de la pausa (rompe el SLO de 10 s a los ~10 s).
- Al reanudar, drena en ~30 s.


