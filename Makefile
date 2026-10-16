.PHONY: datos db-up db-down db-reset cargar verificar estrategias fase4 modulith medir limpiar-resultados test-lab

# Flujo obligatorio del entregable: genera → carga → verifica.
datos: db-up
	@python3 datos/generar_datos.py --seed 42
	@./datos/cargar_datos.sh
	@python3 datos/verificar_datos.py

db-up:
	@if docker container inspect postgres-escalables >/dev/null 2>&1; then \
		docker start postgres-escalables >/dev/null 2>&1 || true; \
	else \
		docker compose up -d postgres; \
	fi
	@until docker exec postgres-escalables pg_isready -U postgres -d escalables >/dev/null 2>&1; do sleep 1; done

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
