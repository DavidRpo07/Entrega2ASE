"""Arranca uvicorn sin su configuración de logging (log_config=None), para que
todos los logs salgan en JSON con trace_id (app/telemetria.py).

    python -m app.servir app.api:app
"""
import sys

import uvicorn

if __name__ == "__main__":
    uvicorn.run(sys.argv[1], host="0.0.0.0", port=8000, log_config=None, access_log=False)
