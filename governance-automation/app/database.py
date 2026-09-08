import json
import os
import threading
import time
import urllib.request

from pathlib import Path

import psycopg
from psycopg.rows import dict_row


_lock = threading.Lock()

_vault_token = None
_db_username = None
_db_password = None
_db_valid_until = 0.0


def _config():
    role_id = os.getenv("VAULT_ROLE_ID")
    secret_id_file = os.getenv("VAULT_SECRET_ID_FILE")
    db_role = os.getenv("VAULT_DB_ROLE")
    postgres_db = os.getenv("POSTGRES_DB")

    missing = []

    if not role_id:
        missing.append("VAULT_ROLE_ID")

    if not secret_id_file:
        missing.append("VAULT_SECRET_ID_FILE")

    if not db_role:
        missing.append("VAULT_DB_ROLE")

    if not postgres_db:
        missing.append("POSTGRES_DB")

    if missing:
        raise RuntimeError(
            "Missing Vault database configuration: "
            + ", ".join(missing)
        )

    return {
        "vault_addr": os.getenv(
            "VAULT_ADDR",
            "http://vault:8200",  # NOSONAR - local Docker-internal Vault transport; production requires TLS/mTLS
        ).rstrip("/"),
        "role_id": role_id,
        "secret_id_file": secret_id_file,
        "db_role": db_role,
        "postgres_host": os.getenv(
            "POSTGRES_HOST",
            "postgres",
        ),
        "postgres_port": int(
            os.getenv(
                "POSTGRES_PORT",
                "5432",
            )
        ),
        "postgres_db": postgres_db,
        "postgres_sslmode": os.getenv(
            "POSTGRES_SSLMODE",
            "disable",
        ),
    }


def _read_secret_id(path):
    try:
        secret_id = Path(path).read_text().strip()
    except OSError as exc:
        raise RuntimeError(
            "Unable to read Vault AppRole SecretID file."
        ) from exc

    if not secret_id:
        raise RuntimeError(
            "Vault AppRole SecretID file is empty."
        )

    return secret_id


def _vault_request(
    method,
    url,
    *,
    token=None,
    payload=None,
):
    data = None

    if payload is not None:
        data = json.dumps(payload).encode()

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            **(
                {"X-Vault-Token": token}
                if token
                else {}
            ),
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=5,
    ) as response:
        return json.loads(response.read())


def _login(config):
    global _vault_token

    secret_id = _read_secret_id(
        config["secret_id_file"]
    )

    result = _vault_request(
        "POST",
        (
            f"{config['vault_addr']}"
            "/v1/auth/approle/login"
        ),
        payload={
            "role_id": config["role_id"],
            "secret_id": secret_id,
        },
    )

    token = (
        result
        .get("auth", {})
        .get("client_token")
    )

    if not token:
        raise RuntimeError(
            "Vault AppRole authentication failed."
        )

    _vault_token = token
    return token


def _runtime_token(config):
    global _vault_token

    if not _vault_token:
        return _login(config)

    try:
        result = _vault_request(
            "POST",
            (
                f"{config['vault_addr']}"
                "/v1/auth/token/renew-self"
            ),
            token=_vault_token,
            payload={},
        )

        renewed = (
            result
            .get("auth", {})
            .get("client_token")
        )

        if renewed:
            _vault_token = renewed

        return _vault_token

    except Exception:
        _vault_token = None
        return _login(config)


def _database_credentials(config):
    global _db_username
    global _db_password
    global _db_valid_until

    now = time.monotonic()

    if (
        _db_username
        and _db_password
        and now < _db_valid_until
    ):
        return _db_username, _db_password

    with _lock:
        now = time.monotonic()

        if (
            _db_username
            and _db_password
            and now < _db_valid_until
        ):
            return _db_username, _db_password

        token = _runtime_token(config)

        result = _vault_request(
            "GET",
            (
                f"{config['vault_addr']}"
                f"/v1/database/creds/"
                f"{config['db_role']}"
            ),
            token=token,
        )

        data = result.get("data", {})

        username = data.get("username")
        password = data.get("password")

        lease_duration = int(
            result.get("lease_duration") or 0
        )

        if (
            not username
            or not password
            or lease_duration <= 0
        ):
            raise RuntimeError(
                "Vault returned invalid database credentials."
            )

        _db_username = username
        _db_password = password

        # Refresh before the Vault lease expires.
        _db_valid_until = (
            time.monotonic()
            + max(30, lease_duration - 60)
        )

        return username, password


def get_connection():
    config = _config()

    username, password = (
        _database_credentials(config)
    )

    return psycopg.connect(
        host=config["postgres_host"],
        port=config["postgres_port"],
        dbname=config["postgres_db"],
        user=username,
        password=password,
        sslmode=config["postgres_sslmode"],
        row_factory=dict_row,
    )
