# Dockerfile (usa python:3.10-slim)
FROM python:3.10-slim

# Evitar buffering en salida (logs en tiempo real)
ENV PYTHONUNBUFFERED=1

WORKDIR /mafiabot

# Instalación de dependencias del sistema necesarias para aiosqlite/compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential libsqlite3-dev libffi-dev \
  && rm -rf /var/lib/apt/lists/*

# Copiar y instalar requisitos (asegúrate de que requirements.txt exista)
COPY requirements.txt /mafiabot/requirements.txt
RUN pip install --no-cache-dir -r /mafiabot/requirements.txt

# Copiar todo el proyecto
COPY . /mafiabot

# Exponer puerto del dashboard (ajustable)
EXPOSE 8006

# Variables de entorno por defecto (puedes sobrescribirlas con -e)
ENV MAFIA_DASH_PORT=8006

ENV MAFIA_DB_FILE=/mafiabot/mafia_complete.db

# Nombre del script principal (ajusta si tu entrypoint es otro .py)
ENV MAIN_PY=main.py

# Comando por defecto
CMD ["sh", "-c", "exec python ${MAIN_PY}"]