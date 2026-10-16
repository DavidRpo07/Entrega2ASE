# Entregable 3 — Resiliencia y observabilidad (requisitos)

Transcripción a texto de las diapositivas del profesor (Entregable3.pdf), curso
Aplicaciones y Sistemas Escalables, EAFIT. Usar este archivo como fuente de requisitos.

## Objetivo

Construir un laboratorio de fallas configurable y reproducible **sobre el sistema
desarrollado**, para entender qué ocurre cuando falla, cómo detectarlo con
observabilidad y qué decisiones de diseño tomar.

Principio: "La falla no es el resultado. El resultado es lo que aprendemos al
observar la respuesta del sistema."

Flujo: configurar las fallas → experimentar (4–8 experimentos) → observar y
explicar (qué pasa, cómo detectarlo, por qué ocurre, qué decisión tomar).

## Falla configurable: cinco condiciones obligatorias

1. **Sin redespliegue**: se activa por archivo, variable o endpoint administrativo.
2. **Parametrizada**: intensidad, probabilidad, alcance, duración.
3. **Focalizable**: endpoint, módulo/componente o % del tráfico, cuando aplique.
4. **Reversible en segundos**: kill switch durante la demostración.
5. **Reproducible**: misma configuración + misma semilla → comportamiento comparable.

Una falla que solo lanza una excepción NO cumple la definición.

## Cuatro familias de fallas

No se compensa la ausencia de una familia con más fallas de otra. Las diapositivas
dicen "1–2 fallas por familia"; la infografía dice "mínimo dos por familia".
Diseño del equipo: 2 por familia (8 experimentos).

- **A · Latencia inducida**: latencia fija en dependencia, jitter (distribución
  lognormal), solo en parte del tráfico, pérdida/timeout controlado.
- **B · Falla de base de datos**: caída temporal de PostgreSQL, pool de conexiones
  agotado, bloqueo sobre un recurso, failover o disco lleno simulado.
- **C · Degradación de tiempos**: saturación de CPU, presión de memoria y GC,
  inanición del pool de hilos, consumidor pausado / lag.
- **D · Riesgo de disponibilidad**: caída de una instancia, partición de red
  servicio ↔ base, DNS que no resuelve, respuestas 5xx externas, desfase de reloj.

## Método experimental (por cada falla)

La predicción se documenta ANTES de conocer el resultado.

1. **Estado base**: métricas de referencia sin falla.
2. **Predicción (antes)**: qué se espera que ocurra y por qué.
3. **Activar falla** con una configuración específica.
4. **Observar y medir**: métricas, logs y/o trazas.
5. **Explicar**: comparar predicción vs. realidad y analizar diferencias.
6. **Corregir y repetir**: ajustar configuración y reejecutar para validar el efecto.

## Observabilidad

Se evalúa la utilidad de las señales, no tener muchas herramientas.

- **Métricas**: p50/p95/p99, throughput, errores, CPU, memoria, GC, colas,
  circuit breakers.
- **Logs**: reconstruir qué ocurrió, cuándo y en qué componente.
- **Trazas**: seguir una solicitud a través de componentes y dependencias.

El equipo debe poder responder por experimento:
1. ¿Qué ocurrió? 2. ¿Dónde está la falla? 3. ¿Qué la está causando?
4. ¿Qué señales fueron útiles? 5. ¿Cuáles no lo fueron?

Deben descubrir sobre observabilidad: ventajas (detectar degradación, localizar
problemas, comparar antes/después), desventajas (costo, ruido, overhead, falsos
positivos) y usos posibles (explicar incidentes, mejorar SLO/SLA, orientar decisiones).

## Rúbrica (100 puntos)

| Criterio | Peso |
| --- | --- |
| Fallas configurables | 20 % |
| Diseño experimental y predicciones | 20 % |
| Ejecución, reproducibilidad y reversibilidad | 15 % |
| Observabilidad y evidencia | 25 % (mayor peso) |
| Análisis de resultados y aprendizaje | 10 % |
| Corrección, reexperimentación y comunicación | 10 % |

## Qué debe quedar en el repositorio

- **Configuración**: catálogo, parámetros, targets y switches.
- **Código**: base → falla → medición → corrección → repetición; scripts e instrucciones.
- **Evidencia organizada** en carpetas: `baseline/`, `experiments/`, `predictions/`,
  `results/`, `logs/`, `metrics/`, `traces/`.
- **Informe técnico**: máximo 10 páginas + anexos técnicos, con tabla de
  experimentos, resultados, análisis y aprendizajes.

### Tabla obligatoria

Columnas: ID · familia · falla · configuración · predicción · resultado · evidencia · aprendizaje.

Ejemplos del profesor:

| ID | Familia | Falla | Configuración | Predicción | Resultado | Evidencia | Aprendizaje |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | Latencia | Tributaria lenta | +800 ms, 30 % | p95 +800 ms | p99 = 12 s | métricas + logs | timeout impedía abrir breaker |
| B1 | BD | Pool agotado | max 10 conn, 5 min | aumento de errores | 503 y timeouts | métricas + trazas | ajustar pool y retry |

## Condiciones mínimas de aprobación (todas, además de la nota)

- Entre 4 y 8 experimentos (1–2 por familia).
- Cuatro familias con fallas configurables y sin redespliegue.
- Kill switch funcional.
- Predicción previa documentada.
- Evidencia observable suficiente por experimento.
- Procedimiento reproducible.
- Análisis y aprendizaje de cada experimento.

## Lo que NO se premia

- Solo "la aplicación se cayó" como resultado.
- Un `throw Exception` como falla.
- Gráficas sin hipótesis ni contexto.
- Solo promedios como medición de latencia.
- Muchos dashboards sin interpretación.
- Una predicción siempre acertada (su valor está en el aprendizaje).

"La diferencia entre la predicción y el resultado es la nota."

## Material de clase relacionado

**Patrones de resiliencia** (para las correcciones):
- Circuit breaker: estados cerrado / abierto / semiabierto; abre tras N fallas
  consecutivas (ej. 5), prueba tras un tiempo (ej. 30 s). Buenas prácticas:
  umbrales adecuados, tiempos de espera razonables, registrar y monitorear estados,
  fallback, usar junto con timeouts y reintentos, configuración por servicio.
- Try-catch: capturar excepciones específicas, registrar con contexto, no ocultar
  errores, finally para liberar recursos.
- Bulkhead: aislar recursos (hilos, conexiones, memoria, pools) por cliente o
  servicio para que una saturación no afecte al resto.
- Retry: solo fallas transitorias, máximo de intentos (3–5), backoff exponencial
  (100, 200, 400 ms) + jitter para evitar thundering herd, combinado con circuit breaker.
- Caché y procesamiento asíncrono con colas.

**Ejemplo de informe del profesor (pruebas de carga/estrés de un validador SAP)**,
como referencia de estilo: alcance y prerrequisitos, criterios de aceptación y SLA
(p90/p95/p99, tasa de error por ventana de 60 s, throughput, CPU/memoria),
resultados por escenario con tablas y gráficas, punto de quiebre, análisis de
recursos (CPU, memoria, red, disco con su interpretación), causa raíz por capa,
impacto en rendimiento y negocio, tipos de errores (429/500/504), recomendaciones
(timeouts alineados por nivel, rate limiting progresivo, colas) y patrones de resiliencia.
