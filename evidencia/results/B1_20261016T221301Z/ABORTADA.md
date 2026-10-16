# B1_20261016T221301Z — ABORTADA: k6 bloqueado por el runner

Error del runner, no del sistema: tras el cambio a un bucle de `poll()` (detector de reposo) nadie
leía el pipe de salida de k6; las fallas de B1 generan >150 KB de avisos de k6, el pipe (64 KB) se
llenó y k6 quedó bloqueado al terminar. El runner abortó a los 240 s del kill switch
("k6 no terminó a tiempo") sin analizar. Arreglo: k6 escribe directo a `logs/<RUN>/k6.log`.

