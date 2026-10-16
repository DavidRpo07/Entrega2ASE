# B2 — Bloqueo sobre franjas del CEDI más usado (30 s cada 60 s)

Estado: LISTA

**Para la tabla:** Cascada: errores en todos los CEDI cada 60 s, no solo en el bloqueado

**Hipótesis:** Si una transacción retiene 30 s el lock de las franjas del CEDI más usado, fallan TODAS las órdenes y no solo las de ese CEDI, porque las peticiones bloqueadas retienen sus conexiones y agotan el pool en segundos.

**Predicción:**
- Durante cada lock: 60–90 % de errores globales (otros CEDI y lecturas incluidos); pg_locks en espera ≈ 8–10.
- Entre locks: SLO normal en 1–3 s → diente de sierra de periodo 60 s.
- Error promedio de la fase ≈ 40 %, que esconde que la mitad del tiempo el servicio está caído.
- Recuperación < 3 s tras liberar el lock.

