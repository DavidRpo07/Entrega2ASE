# D2 — ext-sap con 503 en el 40 % (tras 2 s)

Estado: LISTA

**Para la tabla:** API sin cambio; outbox atascado (~3.800 pendientes) y 40 % sin confirmar

**Hipótesis:** Si ext-sap tarda 2 s y falla el 40 %, la API no se entera pero el worker en serie se vuelve cuello de botella (~0,8 s por evento → ~1,25 eventos/s frente a 14/s) y, sin reintentos, pierde el 40 % de las notificaciones.

**Predicción:**
- POST: latencia y errores sin cambio.
- Pendientes ≈ 3.800 y lag ≈ 5 min al final.
- 40 % de los eventos procesados quedan como fallo permanente.
- Tras el kill switch drena en ~40 s; los fallidos no se recuperan solos.

