FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=8
WORKDIR /app

COPY apps/server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 8 -r /app/requirements.txt
COPY apps/server/app /app/app
COPY apps/server/alembic.ini /app/alembic.ini
COPY apps/server/alembic /app/alembic
COPY scripts /app/scripts
COPY .env.example /app/.env.example
COPY apps/server/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
