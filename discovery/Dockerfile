FROM python:3.15-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home app

COPY --chown=10001:10001 appsmith_discovery.py discovery_health.py ./

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 CMD ["python", "/app/discovery_health.py"]

CMD ["python", "appsmith_discovery.py"]
