# Diagnóstico de la Fase 4 del E2 (2026-10-17)

Misma ruta (`datos/ejecutar_fase4_modulith.py`) y mismas 5.000 órdenes (`datos/csv/ordenes_fase4_5k.csv`),
con `lab/momento1/linea_base.py fase4`. Cada `<etiqueta>.json` resume la corrida y su estado antes/después.

| Etiqueta | Estado de la base | req/s |
| --- | --- | --- |
| `a_estado_lab_con_servicios` | base del lab tras las corridas de fallas (franjas casi llenas), servicios del lab arriba | 326,45 |
| `a2_repeticion_sin_restaurar` | igual, repetida sin restaurar franjas | 330,46 |
| `b_franjas_restauradas` | franjas devueltas al CSV, con desglose por módulo (`--desglose`, agrega instrumentación) | 290,21 |
| `b2_franjas_restauradas_sin_desglose` | franjas devueltas al CSV, sin desglose | 330,07 |

La línea base oficial (base recién cargada, lab apagado) está en `../20261017T034200Z/`: 296,42 req/s.
`*_desglose.csv`: tiempo de Q1, Q2, Q3 y del método completo por orden, y filas que toca el UPDATE de Q3.
