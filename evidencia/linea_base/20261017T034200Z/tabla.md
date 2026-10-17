# Línea base E3 vs. E2 — `20261017T034200Z`

Referencia: informe del E2 (`lab/momento1/referencia_e2.yaml`). Objetivo E3 = 0,90 × E2. Mismo método de percentil que el informe en cada fila (Q1 exclusive; Q2–Q5 inclusive); la columna «otro método» es la misma medición con el otro.

| Consulta | Fase | Escenario | Métrica | E2 (ms) | Objetivo E3 (ms) | E3 (ms) | E3/E2 | Cumple | Otro método (ms) |
|---|---|---|---|---|---|---|---|---|---|
| Q1 | base | frio | p50 | 0.177 | 0.159 | 0.162 | 0.92 | **no** | 0.162 |
| Q1 | base | frio | p95 | 0.252 | 0.227 | 0.253 | 1.0 | **no** | 0.236 |
| Q1 | base | frio | p99 | 3.575 | 3.218 | 1.312 | 0.37 | sí | 0.776 |
| Q1 | base | caliente | p50 | 0.161 | 0.145 | 0.16 | 0.99 | **no** | 0.16 |
| Q1 | base | caliente | p95 | 0.217 | 0.195 | 0.261 | 1.2 | **no** | 0.197 |
| Q1 | base | caliente | p99 | 0.386 | 0.347 | 0.405 | 1.05 | **no** | 0.391 |
| Q2 | base | frio | p50 | 0.226 | 0.203 | 0.238 | 1.05 | **no** | 0.238 |
| Q2 | base | frio | p95 | 0.944 | 0.85 | 0.373 | 0.4 | sí | 0.403 |
| Q2 | base | frio | p99 | 1.605 | 1.445 | 0.453 | 0.28 | sí | 0.467 |
| Q2 | base | caliente | p50 | 0.312 | 0.281 | 0.27 | 0.87 | sí | 0.27 |
| Q2 | base | caliente | p95 | 1.97 | 1.773 | 1.009 | 0.51 | sí | 1.205 |
| Q2 | base | caliente | p99 | 10.389 | 9.35 | 1.344 | 0.13 | sí | 6.277 |
| Q3 | base | frio | p50 | 0.167 | 0.15 | 0.173 | 1.04 | **no** | 0.173 |
| Q3 | base | frio | p95 | 0.249 | 0.224 | 0.235 | 0.94 | **no** | 0.236 |
| Q3 | base | frio | p99 | 0.464 | 0.418 | 0.243 | 0.52 | sí | 0.308 |
| Q3 | base | caliente | p50 | 0.181 | 0.163 | 0.18 | 0.99 | **no** | 0.18 |
| Q3 | base | caliente | p95 | 0.336 | 0.302 | 0.249 | 0.74 | sí | 0.254 |
| Q3 | base | caliente | p99 | 0.927 | 0.834 | 0.277 | 0.3 | sí | 1.114 |
| Q4 | antes_indice | frio | p50 | 34.217 | — | 57.859 | 1.69 | — | 57.859 |
| Q4 | antes_indice | frio | p95 | 35.41 | — | 68.667 | 1.94 | — | 69.715 |
| Q4 | antes_indice | frio | p99 | 39.323 | — | 73.489 | 1.87 | — | 84.377 |
| Q4 | antes_indice | caliente | p50 | 36.413 | — | 60.961 | 1.67 | — | 60.961 |
| Q4 | antes_indice | caliente | p95 | 40.786 | — | 105.042 | 2.58 | — | 108.958 |
| Q4 | antes_indice | caliente | p99 | 74.687 | — | 181.888 | 2.44 | — | 557.405 |
| Q4 | despues_indice | frio | p50 | 0.358 | 0.322 | 0.362 | 1.01 | **no** | 0.362 |
| Q4 | despues_indice | frio | p95 | 0.419 | 0.377 | 0.418 | 1.0 | **no** | 0.422 |
| Q4 | despues_indice | frio | p99 | 0.435 | 0.392 | 0.464 | 1.07 | **no** | 0.484 |
| Q4 | despues_indice | caliente | p50 | 2.839 | 2.555 | 3.407 | 1.2 | **no** | 3.407 |
| Q4 | despues_indice | caliente | p95 | 9.334 | 8.401 | 10.315 | 1.11 | **no** | 11.748 |
| Q4 | despues_indice | caliente | p99 | 14.481 | 13.033 | 14.566 | 1.01 | **no** | 19.051 |
| Q5 | antes_indice | frio | p50 | 6.901 | — | 13.167 | 1.91 | — | 13.167 |
| Q5 | antes_indice | frio | p95 | 8.213 | — | 14.175 | 1.73 | — | 14.687 |
| Q5 | antes_indice | frio | p99 | 10.279 | — | 16.21 | 1.58 | — | 17.456 |
| Q5 | antes_indice | caliente | p50 | 6.994 | — | 11.038 | 1.58 | — | 11.038 |
| Q5 | antes_indice | caliente | p95 | 8.188 | — | 12.963 | 1.58 | — | 13.117 |
| Q5 | antes_indice | caliente | p99 | 9.346 | — | 13.87 | 1.48 | — | 14.16 |
| Q5 | despues_indice | frio | p50 | 0.156 | 0.14 | 0.193 | 1.24 | **no** | 0.193 |
| Q5 | despues_indice | frio | p95 | 0.181 | 0.163 | 0.252 | 1.39 | **no** | 0.255 |
| Q5 | despues_indice | frio | p99 | 0.191 | 0.172 | 0.273 | 1.43 | **no** | 0.29 |
| Q5 | despues_indice | caliente | p50 | 0.25 | 0.225 | 0.328 | 1.31 | **no** | 0.328 |
| Q5 | despues_indice | caliente | p95 | 0.327 | 0.294 | 0.487 | 1.49 | **no** | 0.515 |
| Q5 | despues_indice | caliente | p99 | 0.374 | 0.337 | 0.531 | 1.42 | **no** | 0.535 |

## Fase 4 (5.000 órdenes, ruta del modulith; req/s = exitosas / duración)

| | E2 | Objetivo E3 | E3 | Cumple |
|---|---|---|---|---|
| Duración (s) | 3.6815 | ≤ 3.3134 | 5.1380 | **no** |
| Throughput (req/s) | 413.69 | ≥ 459.66 | 296.42 | |
| Exitosas | 1523 | | 1523 | |
