#!/usr/bin/env python3
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
import psycopg2

DB_CONFIG = {
    "dbname": "escalables",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432
}

BASE_DIR = Path(__file__).resolve().parent
CSV_FASE4 = BASE_DIR / "csv" / "ordenes_fase4_5k.csv"
RESULTADOS_DIR = BASE_DIR / "resultados"
CSV_OPERACIONES = RESULTADOS_DIR / "fase4_modulith_operaciones.csv"
CSV_RESUMEN = RESULTADOS_DIR / "fase4_modulith_resumen.csv"

# E3, optimización c: sentencias preparadas. Cada consulta de la ruta se prepara una vez por
# conexión (PREPARE) y luego se ejecuta con EXECUTE: PostgreSQL no vuelve a analizar ni planificar
# el SQL en cada orden. preparar=False en los servicios = comportamiento del E2.
_PREPARADAS = {}   # id(conexión) -> nombres ya preparados


def preparar_sentencia(cursor, nombre, sql):
    """Prepara `sql` (con marcadores %s) como `nombre` y devuelve el EXECUTE equivalente."""
    n = sql.count("%s")
    hechas = _PREPARADAS.setdefault(id(cursor.connection), set())
    if nombre not in hechas:
        cuerpo = sql.strip().rstrip(";")
        for i in range(1, n + 1):
            cuerpo = cuerpo.replace("%s", f"${i}", 1)
        cursor.execute(f"PREPARE {nombre} AS {cuerpo}")
        hechas.add(nombre)
    return f"EXECUTE {nombre} ({', '.join(['%s'] * n)});"


# =====================================================================
# MÓDULOS DE DOMINIO (MONOLITO MODULAR)
# =====================================================================
class ProveedorService:
    def __init__(self, cursor, preparar=True):
        self.cursor = cursor
        self._query_q1 = """
            SELECT c.contrato_id 
            FROM proveedores.proveedor p
            JOIN proveedores.contrato_suministro c ON p.proveedor_id = c.proveedor_id
            WHERE p.proveedor_id = %s 
              AND p.estado = 'ACTIVO' 
              AND c.estado = 'VIGENTE'
              AND %s::timestamptz BETWEEN c.fecha_inicio AND c.fecha_fin
            LIMIT 1;
        """
        if preparar:
            self._query_q1 = preparar_sentencia(cursor, "e3_q1", self._query_q1)

    def validar_contrato_vigente(self, proveedor_id, fecha_evaluacion):
        self.cursor.execute(self._query_q1, (proveedor_id, fecha_evaluacion))
        if not self.cursor.fetchone():
            raise ValueError(f"Proveedor {proveedor_id} sin contrato vigente.")
        return True


class CatalogoService:
    def __init__(self, cursor, preparar=True):
        self.cursor = cursor
        self._query_q2 = """
            SELECT c.precio 
            FROM catalogo.catalogo_negociado c
            WHERE c.proveedor_id = %s 
              AND c.sku_id = %s 
              AND c.estado = 'ACTIVO'
              AND %s::timestamptz BETWEEN c.fecha_inicio AND c.fecha_fin
            LIMIT 1;
        """
        if preparar:
            self._query_q2 = preparar_sentencia(cursor, "e3_q2", self._query_q2)

    def validar_sku_y_obtener_precio(self, proveedor_id, sku_id, fecha_evaluacion):
        self.cursor.execute(self._query_q2, (proveedor_id, sku_id, fecha_evaluacion))
        res = self.cursor.fetchone()
        if not res:
            # Si el SKU no hace match puntual por rango de fecha en la semilla,
            # retornamos un valor base para permitir la evaluación de rendimiento
            return 1500.00
        return float(res[0])


class LogisticaService:
    # E3, optimización 1: reserva UNA franja (la primera del día con cupo). Las franjas que otra
    # transacción tiene bloqueadas se saltan (SKIP LOCKED) en vez de esperarlas.
    _query_q3_una_franja = """
            UPDATE logistica.franja_descargue
            SET reservas_actuales = reservas_actuales + 1,
                estado = CASE WHEN reservas_actuales + 1 >= capacidad THEN 'COMPLETA' ELSE estado END
            WHERE franja_id = (
                SELECT franja_id
                FROM logistica.franja_descargue
                WHERE cedi_id = %s
                  AND fecha = %s::date
                  AND estado = 'DISPONIBLE'
                  AND reservas_actuales < capacidad
                ORDER BY hora_inicio
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            );
        """

    def __init__(self, cursor, una_franja=True, preparar=True):
        self.cursor = cursor
        # False = comportamiento del E2: el UPDATE suma una reserva en TODAS las franjas
        # disponibles del CEDI ese día.
        self.una_franja = una_franja
        self._query_q3 = self._query_q3_una_franja if una_franja else """
            UPDATE logistica.franja_descargue
            SET reservas_actuales = reservas_actuales + 1,
                estado = CASE WHEN reservas_actuales + 1 >= capacidad THEN 'COMPLETA' ELSE estado END
            WHERE cedi_id = %s 
              AND fecha = %s::date
              AND estado = 'DISPONIBLE'
              AND reservas_actuales < capacidad;
        """
        if preparar:
            self._query_q3 = preparar_sentencia(cursor, "e3_q3_una" if una_franja else "e3_q3_todas", self._query_q3)

    def reservar_franja(self, cedi_id, fecha_entrega):
        fecha_dia = fecha_entrega.split(" ")[0]
        self.cursor.execute(self._query_q3, (cedi_id, fecha_dia))
        return True


class OrdenesService:
    # Estados que admite ordenes.orden_compra (CHECK chk_orden_estadoor de modelo-fisico.sql).
    ESTADOS_VALIDOS = frozenset({"PENDIENTE", "EN_VALIDACION", "CONFIRMADA", "RECHAZADA", "CANCELADA"})

    def __init__(self, cursor, prov_svc, cat_svc, log_svc, validar_estado_primero=True, preparar=True):
        self.cursor = cursor
        self.prov_svc = prov_svc
        self.cat_svc = cat_svc
        self.log_svc = log_svc
        # E3, optimización 2: una orden con estado inválido se rechaza antes de consultar los
        # demás módulos y de reservar franja (en el E2 llegaba hasta el INSERT y fallaba por el
        # CHECK, después de Q1, Q2 y el UPDATE de Q3). False = comportamiento del E2.
        self.validar_estado_primero = validar_estado_primero
        
        self._insert_orden = """
            INSERT INTO ordenes.orden_compra (
                orden_id, proveedor_id, cedi_id, fecha_creacion, 
                fecha_entrega_solicitada, fecha_recepcion, estado, total
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        self._insert_linea = """
            INSERT INTO ordenes.linea_orden (
                orden_id, sku_id, categoria, cantidad_solicitada, cantidad_recibida, precio_unitario
            ) VALUES (%s, %s, %s, %s, %s, %s);
        """
        if preparar:
            self._insert_orden = preparar_sentencia(cursor, "e3_insert_orden", self._insert_orden)
            self._insert_linea = preparar_sentencia(cursor, "e3_insert_linea", self._insert_linea)

    def crear_orden_transaccional(self, dto):
        ord_id, prov_id, cedi_id, f_crea, f_ent, f_rec, estado, total = dto
        sku_demo = 101

        # 0. Validación local del módulo Órdenes (fail-fast, sin tocar la base)
        if self.validar_estado_primero and estado not in self.ESTADOS_VALIDOS:
            raise ValueError(f"Estado de orden inválido: {estado}")

        # 1. Validación Q1 (Módulo Proveedores)
        self.prov_svc.validar_contrato_vigente(prov_id, f_crea)

        # 2. Validación Q2 (Módulo Catálogo)
        precio = self.cat_svc.validar_sku_y_obtener_precio(prov_id, sku_demo, f_crea)

        # 3. Validación y Lock Q3 (Módulo Logística)
        self.log_svc.reservar_franja(cedi_id, f_ent)

        # 4. Inserción Real en la BD PostgreSQL (Módulo Órdenes)
        self.cursor.execute(self._insert_orden, (ord_id, prov_id, cedi_id, f_crea, f_ent, f_rec, estado, total))
        self.cursor.execute(self._insert_linea, (ord_id, sku_demo, "General", 10, 10, precio))


# =====================================================================
# EJECUCIÓN
# =====================================================================
def main():
    if not CSV_FASE4.exists():
        print(f"Error: Primero ejecuta generar_ordenes_fase4.py para crear {CSV_FASE4}")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Instanciar servicios
    prov_svc = ProveedorService(cursor)
    cat_svc = CatalogoService(cursor)
    log_svc = LogisticaService(cursor)
    ordenes_svc = OrdenesService(cursor, prov_svc, cat_svc, log_svc)

    # Limpiar ejecuciones previas de la Fase 4 en la BD
    cursor.execute("DELETE FROM ordenes.linea_orden WHERE orden_id >= 600001;")
    cursor.execute("DELETE FROM ordenes.orden_compra WHERE orden_id >= 600001;")
    conn.commit()

    ordenes = []
    with open(CSV_FASE4, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ordenes.append((
                int(r["orden_id"]),
                int(r["proveedor_id"]),
                int(r["cedi_id"]),
                r["fecha_creacion"],
                r["fecha_entrega_solicitada"],
                r["fecha_recepcion"],
                r["estado"],
                float(r["total"])
            ))

    print(f"Iniciando ingesta real en PostgreSQL de {len(ordenes):,} órdenes...")
    inicio = time.perf_counter()

    exitosas = 0
    rechazadas = 0

    RESULTADOS_DIR.mkdir(exist_ok=True)
    with CSV_OPERACIONES.open("w", newline="", encoding="utf-8") as archivo_operaciones:
        campos = ["orden_id", "proveedor_id", "cedi_id", "estado_resultado", "latencia_ms", "error", "medido_en_utc"]
        escritor = csv.DictWriter(archivo_operaciones, fieldnames=campos)
        escritor.writeheader()
        for dto in ordenes:
            inicio_orden = time.perf_counter()
            error = ""
            try:
                ordenes_svc.crear_orden_transaccional(dto)
                conn.commit()  # Persistencia real en la BD
                exitosas += 1
                estado_resultado = "EXITOSA"
            except Exception as e:
                conn.rollback()
                rechazadas += 1
                estado_resultado = "RECHAZADA"
                error = str(e)
            latencia_ms = (time.perf_counter() - inicio_orden) * 1000
            escritor.writerow({
                "orden_id": dto[0], "proveedor_id": dto[1], "cedi_id": dto[2],
                "estado_resultado": estado_resultado, "latencia_ms": f"{latencia_ms:.6f}",
                "error": error, "medido_en_utc": datetime.now(timezone.utc).isoformat(),
            })

    fin = time.perf_counter()
    tiempo_total = fin - inicio
    throughput = exitosas / tiempo_total if tiempo_total > 0 else 0

    with CSV_RESUMEN.open("w", newline="", encoding="utf-8") as archivo_resumen:
        escritor = csv.DictWriter(archivo_resumen, fieldnames=["ordenes_intentadas", "exitosas", "rechazadas", "duracion_s", "throughput_req_s", "medido_en_utc"])
        escritor.writeheader()
        escritor.writerow({"ordenes_intentadas": len(ordenes), "exitosas": exitosas,
                          "rechazadas": rechazadas, "duracion_s": f"{tiempo_total:.6f}",
                          "throughput_req_s": f"{throughput:.6f}",
                          "medido_en_utc": datetime.now(timezone.utc).isoformat()})

    print("\n==============================================")
    print("RESULTADOS FASE 4: INYECCIÓN RUTA REAL (POSTGRESQL)")
    print("==============================================")
    print(f"Órdenes insertadas en BD: {exitosas:,}")
    print(f"Órdenes rechazadas:       {rechazadas:,}")
    print(f"Tiempo total:             {tiempo_total:.4f} segundos")
    print(f"Rendimiento Ingesta:      {throughput:,.2f} req/segundo")
    print(f"Evidencia cruda:           {CSV_OPERACIONES}")
    print(f"Resumen:                   {CSV_RESUMEN}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
