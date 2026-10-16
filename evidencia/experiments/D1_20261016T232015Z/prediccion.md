# D1 — Caída de api-2 (3 min)

Estado: LISTA

**Para la tabla:** ~0,5 % de 502 (uno cada ~10 s); api-1 absorbe todo sin degradarse

**Hipótesis:** Si api-2 se cae, nginx la saca tras el primer fallo y api-1 absorbe todo sin degradarse, porque hay mucho margen de capacidad. Quedan fallos periódicos porque nginx reprueba cada 10 s y no reintenta los POST (no idempotentes).

**Predicción:**
- ~1 POST con 502 cada ~10 s → ~0,5 % de errores (SLO al límite).
- api-1 con el doble de carga: p95 12–20 ms.
- Prometheus no ve los 502; solo k6 y el log de nginx.
- Reincorporación de api-2 en ≤ 10 s.

