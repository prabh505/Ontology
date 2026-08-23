# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src
RUN pip install --no-cache-dir -e /app/backend

COPY scripts /app/scripts

EXPOSE 8000
CMD ["uvicorn", "causalog.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
