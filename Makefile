.PHONY: datos db-up db-down db-reset cargar verificar estrategias fase4 modulith medir limpiar-resultados test-lab \
	lab-up lab-down lab-ps lab-logs lab-smoke lab-carga-datos lab-reset lab-carga \
	experimento experimento-prueba limpiar-pruebas

# Flujo obligatorio del entregable: genera → carga → verifica.
datos: db-up
	@python3 datos/generar_datos.py --seed 42
	@./datos/cargar_datos.sh
	@python3 datos/verificar_datos.py

# Postgres lo gestiona compose (volumen pgdata). Si existe un postgres-escalables
# creado a mano con `docker run` (fuera de compose), se pide migrarlo.
db-up:
	@if docker container inspect postgres-escalables >/dev/null 2>&1 && \
		[ -z "$$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' postgres-escalables)" ]; then \
		echo "postgres-escalables existe pero no lo creó compose. Renómbrelo y recargue los datos:"; \
		echo "  docker stop postgres-escalables && docker rename postgres-escalables postgres-escalables-viejo"; \
		echo "  make datos"; \
		exit 1; \
	fi
	@docker compose up -d --wait postgres

db-down:
	@docker compose down

db-reset: db-up
	@./datos/cargar_datos.sh

cargar: db-up
	@./datos/cargar_datos.sh

verificar:
	@python3 datos/verificar_datos.py

estrategias: db-up
	@python3 datos/generar_ordenes_prueba_50k.py
	@python3 datos/estrategia_1_copy.py
	@python3 datos/estrategia_2_lotes.py
	@python3 datos/estrategia_3_autocommit.py
	@python3 datos/estrategia_4_ruta_transaccional.py

# Fase 4: inyección incremental a través de los módulos del modulith.
# Requiere que antes se haya cargado la base con `make datos`.
fase4: db-up
	@python3 datos/generar_ordenes_fase4.py
	@python3 datos/ejecutar_fase4_modulith.py

modulith: fase4

medir: db-up
	@env BENCHMARK_ETIQUETA=base python3 datos/medir_q1.py
	@env BENCHMARK_ETIQUETA=base python3 datos/medir_q2.py
	@env BENCHMARK_ETIQUETA=base python3 datos/medir_q3.py
	@env BENCHMARK_ETIQUETA=antes_indice python3 datos/medir_q4.py
	@python3 datos/crear_indice_q4.py
	@env BENCHMARK_ETIQUETA=despues_indice python3 datos/medir_q4.py
	@env BENCHMARK_ETIQUETA=antes_indice python3 datos/medir_q5.py
	@python3 datos/crear_indice_q5.py
	@env BENCHMARK_ETIQUETA=despues_indice python3 datos/medir_q5.py

limpiar-resultados:
	@rm -f datos/resultados/q*.csv datos/resultados/estrategias_inyeccion.csv datos/resultados/logs/*.log

# Entregable 3: tests del inyector de fallas (no requiere Docker).
test-lab:
	@python3 -m unittest discover -s lab/tests -t .

# Entregable 3, fase 1: API (2 réplicas tras nginx), worker del outbox y mock ext-sap.
# Requiere la base cargada (`make datos`). La API queda en http://localhost:8080
LAB_SERVICIOS = api-1 api-2 worker ext-sap fallas-ext nginx prometheus grafana jaeger postgres-exporter cadvisor

lab-up: db-up
	@mkdir -p lab/runtime
	@[ -f lab/runtime/faults.yaml ] || cp lab/faults.yaml lab/runtime/faults.yaml
	@docker compose build api-1
	@docker compose up -d --wait $(LAB_SERVICIOS)
	@echo "Laboratorio arriba: API http://localhost:8080/docs | Grafana http://localhost:3000 | Prometheus http://localhost:9090 | Jaeger http://localhost:16686"

# Detiene el laboratorio; postgres sigue arriba (lo usan los comandos del Entregable 2).
lab-down:
	@docker compose rm -sf $(LAB_SERVICIOS)

lab-ps:
	@docker compose ps $(LAB_SERVICIOS)

lab-logs:
	@docker compose logs -f --tail=100 $(LAB_SERVICIOS)

lab-smoke:
	@python3 lab/smoke.py

# Carga del laboratorio: secuencia válida con semilla fija (lab/carga/generar_carga.py),
# reset del estado de la base y ejecución con k6 (contenedor en la red del lab).
SEMILLA ?= 42
N ?= 30000
RATE ?= 20
DURACION ?= 2m
ETIQUETA ?= manual
CARGA = lab/carga/datos/carga_s$(SEMILLA)_n$(N).json
K6_IMAGEN = grafana/k6:0.55.0

$(CARGA):
	@python3 lab/carga/generar_carga.py --semilla $(SEMILLA) --n $(N)

lab-carga-datos: $(CARGA)

lab-reset:
	@docker cp datos/csv/franja_descargue.csv postgres-escalables:/tmp/franja_descargue.csv
	@docker exec -i postgres-escalables psql -q -U postgres -d escalables < lab/carga/reset.sql

lab-carga: $(CARGA)
	@mkdir -p lab/carga/salida/$(ETIQUETA)
	@docker run --rm --network escalables-lab -v "$(CURDIR)/lab/carga:/carga" $(K6_IMAGEN) run --quiet \
		-e BASE=http://nginx -e CARGA=/carga/datos/carga_s$(SEMILLA)_n$(N).json \
		-e RATE=$(RATE) -e DURACION=$(DURACION) -e ETIQUETA=$(ETIQUETA) \
		--summary-export /carga/salida/$(ETIQUETA)/resumen_k6.json /carga/k6/carga.js

# Fase 3: experimentos. Exige evidencia/predictions/$(ID).md en "Estado: LISTA" (y con commit).
# Protocolo y SLO en lab/slo.yaml; evidencia en evidencia/{experiments,baseline,metrics,logs,traces,results}/<ID>_<UTC>/
PY ?= $(if $(wildcard venv/bin/python),venv/bin/python,python3)

# En macOS el runner corre bajo `caffeinate -i` (sin reposo por inactividad, también con batería):
# en B1 el Mac se durmió en plena falla. El runner además aborta si detecta una suspensión.
CAFEINA := $(shell command -v caffeinate >/dev/null 2>&1 && echo caffeinate -i)

experimento:
	@test -n "$(ID)" || (echo "uso: make experimento ID=A1" && exit 1)
	@$(CAFEINA) $(PY) lab/experimentos/runner.py --id $(ID)

# Corrida corta de prueba del runner (30 s + 30 s + 25 s, prefijo PRUEBA-, ignorada por git).
experimento-prueba:
	@test -n "$(ID)" || (echo "uso: make experimento-prueba ID=A1" && exit 1)
	@$(CAFEINA) $(PY) lab/experimentos/runner.py --id $(ID) --prueba

limpiar-pruebas:
	@rm -rf evidencia/*/PRUEBA-*
