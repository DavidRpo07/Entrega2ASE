# Tabla final: E2 vs. línea base E3 vs. final E3

Línea base E3: `evidencia/linea_base/20261017T034200Z` · Final E3: `evidencia/linea_base/20261017T035415Z` · E2: informe (`lab/momento1/referencia_e2.yaml`). Objetivo = 0,90 × E2. Mejora = (línea base − final) / línea base. Q4/Q5 «antes_indice» son solo referencia (sin objetivo).

| Consulta | Fase | Escenario | Métrica | E2 (ms) | Línea base E3 (ms) | Final E3 (ms) | Objetivo (ms) | ¿Cumple? | Mejora vs. línea base |
|---|---|---|---|---|---|---|---|---|---|
| Q1 | base | frio | p50 | 0.177 | 0.162 | 0.142 | 0.159 | sí | +12.3 % |
| Q1 | base | frio | p95 | 0.252 | 0.253 | 0.186 | 0.227 | sí | +26.5 % |
| Q1 | base | frio | p99 | 3.575 | 1.312 | 0.43 | 3.218 | sí | +67.2 % |
| Q1 | base | caliente | p50 | 0.161 | 0.16 | 0.141 | 0.145 | sí | +11.9 % |
| Q1 | base | caliente | p95 | 0.217 | 0.261 | 0.18 | 0.195 | sí | +31.0 % |
| Q1 | base | caliente | p99 | 0.386 | 0.405 | 0.194 | 0.347 | sí | +52.1 % |
| Q2 | base | frio | p50 | 0.226 | 0.238 | 0.186 | 0.203 | sí | +21.8 % |
| Q2 | base | frio | p95 | 0.944 | 0.373 | 0.207 | 0.85 | sí | +44.5 % |
| Q2 | base | frio | p99 | 1.605 | 0.453 | 0.211 | 1.445 | sí | +53.4 % |
| Q2 | base | caliente | p50 | 0.312 | 0.27 | 0.223 | 0.281 | sí | +17.4 % |
| Q2 | base | caliente | p95 | 1.97 | 1.009 | 0.487 | 1.773 | sí | +51.7 % |
| Q2 | base | caliente | p99 | 10.389 | 1.344 | 0.548 | 9.35 | sí | +59.2 % |
| Q3 | base | frio | p50 | 0.167 | 0.173 | 0.146 | 0.15 | sí | +15.6 % |
| Q3 | base | frio | p95 | 0.249 | 0.235 | 0.161 | 0.224 | sí | +31.5 % |
| Q3 | base | frio | p99 | 0.464 | 0.243 | 0.168 | 0.418 | sí | +30.9 % |
| Q3 | base | caliente | p50 | 0.181 | 0.18 | 0.14 | 0.163 | sí | +22.2 % |
| Q3 | base | caliente | p95 | 0.336 | 0.249 | 0.157 | 0.302 | sí | +36.9 % |
| Q3 | base | caliente | p99 | 0.927 | 0.277 | 0.168 | 0.834 | sí | +39.4 % |
| Q4 | antes_indice | frio | p50 | 34.217 | 57.859 | 39.366 | — | — | +32.0 % |
| Q4 | antes_indice | frio | p95 | 35.41 | 68.667 | 42.442 | — | — | +38.2 % |
| Q4 | antes_indice | frio | p99 | 39.323 | 73.489 | 51.002 | — | — | +30.6 % |
| Q4 | antes_indice | caliente | p50 | 36.413 | 60.961 | 42.588 | — | — | +30.1 % |
| Q4 | antes_indice | caliente | p95 | 40.786 | 105.042 | 53.255 | — | — | +49.3 % |
| Q4 | antes_indice | caliente | p99 | 74.687 | 181.888 | 65.888 | — | — | +63.8 % |
| Q4 | despues_indice | frio | p50 | 0.358 | 0.362 | 0.342 | 0.322 | **no** | +5.5 % |
| Q4 | despues_indice | frio | p95 | 0.419 | 0.418 | 0.437 | 0.377 | **no** | -4.5 % |
| Q4 | despues_indice | frio | p99 | 0.435 | 0.464 | 0.472 | 0.392 | **no** | -1.7 % |
| Q4 | despues_indice | caliente | p50 | 2.839 | 3.407 | 2.721 | 2.555 | **no** | +20.1 % |
| Q4 | despues_indice | caliente | p95 | 9.334 | 10.315 | 8.141 | 8.401 | sí | +21.1 % |
| Q4 | despues_indice | caliente | p99 | 14.481 | 14.566 | 11.466 | 13.033 | sí | +21.3 % |
| Q5 | antes_indice | frio | p50 | 6.901 | 13.167 | 7.479 | — | — | +43.2 % |
| Q5 | antes_indice | frio | p95 | 8.213 | 14.175 | 8.899 | — | — | +37.2 % |
| Q5 | antes_indice | frio | p99 | 10.279 | 16.21 | 14.81 | — | — | +8.6 % |
| Q5 | antes_indice | caliente | p50 | 6.994 | 11.038 | 7.49 | — | — | +32.1 % |
| Q5 | antes_indice | caliente | p95 | 8.188 | 12.963 | 9.781 | — | — | +24.5 % |
| Q5 | antes_indice | caliente | p99 | 9.346 | 13.87 | 11.512 | — | — | +17.0 % |
| Q5 | despues_indice | frio | p50 | 0.156 | 0.193 | 0.154 | 0.14 | **no** | +20.2 % |
| Q5 | despues_indice | frio | p95 | 0.181 | 0.252 | 0.195 | 0.163 | **no** | +22.6 % |
| Q5 | despues_indice | frio | p99 | 0.191 | 0.273 | 0.199 | 0.172 | **no** | +27.1 % |
| Q5 | despues_indice | caliente | p50 | 0.25 | 0.328 | 0.282 | 0.225 | **no** | +14.0 % |
| Q5 | despues_indice | caliente | p95 | 0.327 | 0.487 | 0.401 | 0.294 | **no** | +17.7 % |
| Q5 | despues_indice | caliente | p99 | 0.374 | 0.531 | 0.43 | 0.337 | **no** | +19.0 % |

## Fase 4 (5.000 órdenes; req/s = exitosas / duración)

| Métrica | E2 | Línea base E3 | Final E3 | Objetivo | ¿Cumple? | Mejora vs. línea base |
|---|---|---|---|---|---|---|
| Throughput (req/s) | 413.69 | 296.42 | 1036.37 | ≥ 459.66 | sí | +249.6 % |
| Duración (s) | 3.6815 | 5.1380 | 1.4696 | ≤ 3.3134 | sí | |
