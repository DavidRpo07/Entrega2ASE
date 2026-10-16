"""Logs JSON con trace_id y trazas OpenTelemetry (OTLP → Jaeger).

configurar(servicio) se llama una vez por proceso, antes de crear la app.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app import config
from lab.fallas.inyector import INYECTOR

_ATRIBUTOS_ESTANDAR = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class FormatoJSON(logging.Formatter):
    """Una línea JSON por evento; trace_id/span_id del span activo (si hay)."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = trace.get_current_span().get_span_context()
        evento = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "instancia": config.INSTANCIA,
            "msg": record.getMessage(),
            "trace_id": format(ctx.trace_id, "032x") if ctx.is_valid else None,
            "span_id": format(ctx.span_id, "016x") if ctx.is_valid else None,
        }
        # campos extra: log.info("...", extra={"ruta": ..., "ms": ...})
        evento.update({k: v for k, v in vars(record).items() if k not in _ATRIBUTOS_ESTANDAR})
        if record.exc_info:
            evento["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def _configurar_logs() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(FormatoJSON())
    raiz = logging.getLogger()
    raiz.handlers[:] = [handler]
    raiz.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    # uvicorn se arranca con log_config=None (app/servir.py): sus logs pasan por aquí.
    # El access log lo escribe nuestro middleware, con trace_id y ruta.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _observar_fallas(evento: str, falla) -> None:
    """Cada inyección queda como evento del span activo (visible en Jaeger)."""
    if evento == "inyectada":
        span = trace.get_current_span()
        span.add_event("falla_inyectada", {"falla.id": falla.id, "falla.tipo": falla.tipo,
                                           "falla.target": falla.target})
        span.set_attribute("falla.id", falla.id)


def instrumentar_fastapi(app) -> None:
    if config.TRAZAS:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")


def instrumentar_httpx() -> None:
    if config.TRAZAS:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()


def configurar(servicio: str) -> trace.Tracer:
    _configurar_logs()
    if not config.TRAZAS:
        # Sin TracerProvider: la API de OTel queda en no-op (spans vacíos, trace_id nulo).
        logging.getLogger("telemetria").warning("trazas desactivadas (TRAZAS=off)")
        return trace.get_tracer(servicio)
    recurso = Resource.create({"service.name": servicio, "service.instance.id": config.INSTANCIA})
    proveedor = TracerProvider(resource=recurso)
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        proveedor.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(proveedor)
    if _observar_fallas not in INYECTOR.observadores:
        INYECTOR.observadores.append(_observar_fallas)
    return trace.get_tracer(servicio)


TRACER = trace.get_tracer("escalables-lab")
