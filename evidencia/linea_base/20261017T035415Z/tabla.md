# Línea base E3 vs. E2 — `20261017T035415Z`

Referencia: informe del E2 (`lab/momento1/referencia_e2.yaml`). Objetivo E3 = 0,90 × E2. Mismo método de percentil que el informe en cada fila (Q1 exclusive; Q2–Q5 inclusive); la columna «otro método» es la misma medición con el otro.

| Consulta | Fase | Escenario | Métrica | E2 (ms) | Objetivo E3 (ms) | E3 (ms) | E3/E2 | Cumple | Otro método (ms) |
|---|---|---|---|---|---|---|---|---|---|
| Q1 | base | frio | p50 | 0.177 | 0.159 | 0.142 | 0.8 | sí | 0.167 |
| Q1 | base | frio | p95 | 0.252 | 0.227 | 0.186 | 0.74 | sí | 0.237 |
| Q1 | base | frio | p99 | 3.575 | 3.218 | 0.43 | 0.12 | sí | 0.254 |
| Q1 | base | caliente | p50 | 0.161 | 0.145 | 0.141 | 0.88 | sí | 0.163 |
| Q1 | base | caliente | p95 | 0.217 | 0.195 | 0.18 | 0.83 | sí | 0.194 |
| Q1 | base | caliente | p99 | 0.386 | 0.347 | 0.194 | 0.5 | sí | 0.204 |
| Q2 | base | frio | p50 | 0.226 | 0.203 | 0.186 | 0.82 | sí | 0.205 |
| Q2 | base | frio | p95 | 0.944 | 0.85 | 0.207 | 0.22 | sí | 0.241 |
| Q2 | base | frio | p99 | 1.605 | 1.445 | 0.211 | 0.13 | sí | 0.301 |
| Q2 | base | caliente | p50 | 0.312 | 0.281 | 0.223 | 0.71 | sí | 0.275 |
| Q2 | base | caliente | p95 | 1.97 | 1.773 | 0.487 | 0.25 | sí | 0.687 |
| Q2 | base | caliente | p99 | 10.389 | 9.35 | 0.548 | 0.05 | sí | 3.698 |
| Q3 | base | frio | p50 | 0.167 | 0.15 | 0.146 | 0.87 | sí | 0.151 |
| Q3 | base | frio | p95 | 0.249 | 0.224 | 0.161 | 0.65 | sí | 0.198 |
| Q3 | base | frio | p99 | 0.464 | 0.418 | 0.168 | 0.36 | sí | 0.213 |
| Q3 | base | caliente | p50 | 0.181 | 0.163 | 0.14 | 0.77 | sí | 0.167 |
| Q3 | base | caliente | p95 | 0.336 | 0.302 | 0.157 | 0.47 | sí | 0.276 |
| Q3 | base | caliente | p99 | 0.927 | 0.834 | 0.168 | 0.18 | sí | 0.992 |
| Q4 | antes_indice | frio | p50 | 34.217 | — | 39.366 | 1.15 | — | 39.366 |
| Q4 | antes_indice | frio | p95 | 35.41 | — | 42.442 | 1.2 | — | 44.244 |
| Q4 | antes_indice | frio | p99 | 39.323 | — | 51.002 | 1.3 | — | 63.42 |
| Q4 | antes_indice | caliente | p50 | 36.413 | — | 42.588 | 1.17 | — | 42.588 |
| Q4 | antes_indice | caliente | p95 | 40.786 | — | 53.255 | 1.31 | — | 54.665 |
| Q4 | antes_indice | caliente | p99 | 74.687 | — | 65.888 | 0.88 | — | 66.899 |
| Q4 | despues_indice | frio | p50 | 0.358 | 0.322 | 0.342 | 0.96 | **no** | 0.342 |
| Q4 | despues_indice | frio | p95 | 0.419 | 0.377 | 0.437 | 1.04 | **no** | 0.441 |
| Q4 | despues_indice | frio | p99 | 0.435 | 0.392 | 0.472 | 1.09 | **no** | 0.507 |
| Q4 | despues_indice | caliente | p50 | 2.839 | 2.555 | 2.721 | 0.96 | **no** | 2.721 |
| Q4 | despues_indice | caliente | p95 | 9.334 | 8.401 | 8.141 | 0.87 | sí | 9.203 |
| Q4 | despues_indice | caliente | p99 | 14.481 | 13.033 | 11.466 | 0.79 | sí | 21.191 |
| Q5 | antes_indice | frio | p50 | 6.901 | — | 7.479 | 1.08 | — | 7.479 |
| Q5 | antes_indice | frio | p95 | 8.213 | — | 8.899 | 1.08 | — | 9.025 |
| Q5 | antes_indice | frio | p99 | 10.279 | — | 14.81 | 1.44 | — | 17.424 |
| Q5 | antes_indice | caliente | p50 | 6.994 | — | 7.49 | 1.07 | — | 7.49 |
| Q5 | antes_indice | caliente | p95 | 8.188 | — | 9.781 | 1.19 | — | 9.945 |
| Q5 | antes_indice | caliente | p99 | 9.346 | — | 11.512 | 1.23 | — | 14.046 |
| Q5 | despues_indice | frio | p50 | 0.156 | 0.14 | 0.154 | 0.99 | **no** | 0.154 |
| Q5 | despues_indice | frio | p95 | 0.181 | 0.163 | 0.195 | 1.08 | **no** | 0.195 |
| Q5 | despues_indice | frio | p99 | 0.191 | 0.172 | 0.199 | 1.04 | **no** | 0.2 |
| Q5 | despues_indice | caliente | p50 | 0.25 | 0.225 | 0.282 | 1.13 | **no** | 0.282 |
| Q5 | despues_indice | caliente | p95 | 0.327 | 0.294 | 0.401 | 1.23 | **no** | 0.403 |
| Q5 | despues_indice | caliente | p99 | 0.374 | 0.337 | 0.43 | 1.15 | **no** | 0.567 |

## Fase 4 (5.000 órdenes, ruta del modulith; req/s = exitosas / duración)

| | E2 | Objetivo E3 | E3 | Cumple |
|---|---|---|---|---|
| Duración (s) | 3.6815 | ≤ 3.3134 | 1.4696 | sí |
| Throughput (req/s) | 413.69 | ≥ 459.66 | 1036.37 | |
| Exitosas | 1523 | | 1523 | |
