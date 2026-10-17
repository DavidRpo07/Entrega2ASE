"""Configuración del laboratorio por variables de entorno."""
import os

INSTANCIA = os.environ.get("INSTANCIA", "local")

# TRAZAS=off apaga OpenTelemetry por completo (sin spans, sin instrumentación de
# FastAPI/httpx): experimento de overhead de observabilidad (trazas on vs off).
TRAZAS = os.environ.get("TRAZAS", "on").lower() not in ("off", "0", "false", "no")

DB_DSN = os.environ.get(
    "DB_DSN",
    "host={h} port={p} dbname=escalables user=postgres password=postgres".format(
        h=os.environ.get("DB_HOST", "localhost"), p=os.environ.get("DB_PORT", "5432")),
)
POOL_MIN = int(os.environ.get("POOL_MIN", "1"))
POOL_MAX = int(os.environ.get("POOL_MAX", "5"))          # B1 asume pool max 5 por réplica
POOL_TIMEOUT_S = float(os.environ.get("POOL_TIMEOUT_S", "5"))

FAULTS_FILE = os.environ.get("FAULTS_FILE")              # faults.yaml compartido por todos los contenedores
CATALOGO_FALLAS = os.environ.get("CATALOGO_FALLAS", "lab/fallas/catalogo.yaml")

# Correcciones de la fase 4: archivo en caliente (lo lee lab.resiliencia.config) y su plantilla.
CORRECCIONES_FILE = os.environ.get("CORRECCIONES_FILE")
CORRECCIONES_BASE = os.environ.get("CORRECCIONES_BASE", "lab/correcciones.yaml")

EXT_SAP_URL = os.environ.get("EXT_SAP_URL", "http://ext-sap:8000")
SAP_TIMEOUT_S = float(os.environ.get("SAP_TIMEOUT_S", "30"))   # sin corrección: timeout holgado
SAP_LATENCIA_MS = float(os.environ.get("SAP_LATENCIA_MS", "20"))

WORKER_LOTE = int(os.environ.get("WORKER_LOTE", "50"))
WORKER_INTERVALO_S = float(os.environ.get("WORKER_INTERVALO_S", "0.5"))
