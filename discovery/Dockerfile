FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY appsmith_discovery.py .

CMD ["python", "appsmith_discovery.py"]
