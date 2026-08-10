FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home app

COPY --chown=10001:10001 appsmith_discovery.py .

USER 10001:10001

CMD ["python", "appsmith_discovery.py"]
