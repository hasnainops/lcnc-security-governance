FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --create-home app

COPY --chown=10001:10001 app ./app

USER 10001:10001

EXPOSE 8003

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8003"]
