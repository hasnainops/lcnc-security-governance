FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN cp /etc/apt/sources.list.d/debian.sources /tmp/debian.sources \
    && printf '%s\n' \
        'Types: deb' \
        'URIs: https://deb.debian.org/debian-security' \
        'Suites: trixie-security' \
        'Components: main' \
        'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' \
        > /etc/apt/sources.list.d/debian.sources \
    && apt-get \
        -o Acquire::ForceIPv4=true \
        -o Acquire::Retries=1 \
        -o Acquire::https::Timeout=20 \
        update \
    && apt-get \
        -o Acquire::ForceIPv4=true \
        -o Acquire::Retries=1 \
        -o Acquire::https::Timeout=20 \
        install --only-upgrade -y --no-install-recommends \
        openssl \
        libssl3t64 \
        openssl-provider-legacy \
    && mv /tmp/debian.sources /etc/apt/sources.list.d/debian.sources \
    && python -m pip install --no-cache-dir --only-binary :all: -r requirements.txt \
    && python -m pip uninstall -y pip setuptools \
    && rm -rf \
        /usr/local/lib/python3.13/site-packages/pip* \
        /usr/local/lib/python3.13/site-packages/setuptools* \
        /usr/local/lib/python3.13/ensurepip \
        /var/lib/apt/lists/*

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home app

COPY --chown=10001:10001 app ./app

USER 10001:10001

EXPOSE 8003

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8003"]
