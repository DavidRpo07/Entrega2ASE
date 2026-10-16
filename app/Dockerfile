FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/datos

COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Código del Entregable 2 (módulos del modulith y SQL de Q4/Q5), sin los CSV.
COPY datos/*.py datos/
COPY lab lab
COPY app app

EXPOSE 8000
CMD ["python", "-m", "app.servir", "app.api:app"]
