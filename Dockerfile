FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=church_system.settings

WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh scripts/*.sh \
    && mkdir -p logs var media backups staticfiles

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health/live/ || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD []
