import os
import threading
import time

import httpx
import psycopg
from psycopg.rows import dict_row


# Optional compatibility value.
# Safe at import time; production does not need DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL")

_lock = threading.RLock()

_cached_vault_token = None
_vault_token_valid_until = 0.0

_cached_db_username = None
_cached_db_password = None
_db_credentials_valid_until = 0.0


def _cache_deadline(ttl_seconds: int):
    safety_margin = min(
        60,
        max(5, ttl_seconds // 10),
    )

    return (
        time.monotonic()
        + max(
            1,
            ttl_seconds - safety_margin,
        )
    )


def _vault_config():
    role_id = os.getenv("VAULT_ROLE_ID")
    secret_id = os.getenv("VAULT_SECRET_ID")
    postgres_db = os.getenv("POSTGRES_DB")

    missing = []

    if not role_id:
        missing.append("VAULT_ROLE_ID")

    if not secret_id:
        missing.append("VAULT_SECRET_ID")

    if not postgres_db:
        missing.append("POSTGRES_DB")

    if missing:
        raise RuntimeError(
            "Missing runtime database configuration: "
            + ", ".join(missing)
        )

    return {
        "vault_addr": os.getenv(
            "VAULT_ADDR",
            "http://vault:8200",
        ).rstrip("/"),
        "role_id": role_id,
        "secret_id": secret_id,
        "vault_db_role": os.getenv(
            "VAULT_DB_ROLE",
            "governance-api",
        ),
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


def _login_to_vault(config, force=False):
    global _cached_vault_token
    global _vault_token_valid_until

    with _lock:
        now = time.monotonic()

        if (
            not force
            and _cached_vault_token
            and now < _vault_token_valid_until
        ):
            return _cached_vault_token

        response = httpx.post(
            (
                f"{config['vault_addr']}"
                "/v1/auth/approle/login"
            ),
            json={
                "role_id": config["role_id"],
                "secret_id": config["secret_id"],
            },
            timeout=5.0,
        )

        response.raise_for_status()

        payload = response.json()
        auth = payload.get("auth") or {}

        token = auth.get("client_token")
        ttl = int(
            auth.get("lease_duration") or 0
        )

        if not token or ttl <= 0:
            raise RuntimeError(
                "Vault AppRole authentication "
                "returned an invalid token or TTL."
            )

        _cached_vault_token = token
        _vault_token_valid_until = (
            _cache_deadline(ttl)
        )

        return token


def _request_database_credentials(
    config,
    token,
):
    return httpx.get(
        (
            f"{config['vault_addr']}"
            "/v1/database/creds/"
            f"{config['vault_db_role']}"
        ),
        headers={
            "X-Vault-Token": token,
        },
        timeout=5.0,
    )


def _get_database_credentials(config):
    global _cached_db_username
    global _cached_db_password
    global _db_credentials_valid_until
    global _cached_vault_token
    global _vault_token_valid_until

    with _lock:
        now = time.monotonic()

        if (
            _cached_db_username
            and _cached_db_password
            and now < _db_credentials_valid_until
        ):
            return (
                _cached_db_username,
                _cached_db_password,
            )

        token = _login_to_vault(
            config
        )

        response = (
            _request_database_credentials(
                config,
                token,
            )
        )

        if response.status_code in {
            400,
            403,
        }:
            _cached_vault_token = None
            _vault_token_valid_until = 0.0

            token = _login_to_vault(
                config,
                force=True,
            )

            response = (
                _request_database_credentials(
                    config,
                    token,
                )
            )

        response.raise_for_status()

        payload = response.json()
        data = payload.get("data") or {}

        username = data.get("username")
        password = data.get("password")

        ttl = int(
            payload.get("lease_duration") or 0
        )

        if (
            not username
            or not password
            or ttl <= 0
        ):
            raise RuntimeError(
                "Vault database secrets engine "
                "returned invalid credentials."
            )

        _cached_db_username = username
        _cached_db_password = password

        _db_credentials_valid_until = (
            _cache_deadline(ttl)
        )

        return (
            username,
            password,
        )


def _invalidate_database_credentials():
    global _cached_db_username
    global _cached_db_password
    global _db_credentials_valid_until

    with _lock:
        _cached_db_username = None
        _cached_db_password = None
        _db_credentials_valid_until = 0.0


def _connect_with_dynamic_credentials(
    config,
):
    username, password = (
        _get_database_credentials(
            config
        )
    )

    return psycopg.connect(
        host=config["postgres_host"],
        port=config["postgres_port"],
        dbname=config["postgres_db"],
        user=username,
        password=password,
        sslmode=config[
            "postgres_sslmode"
        ],
        connect_timeout=5,
        row_factory=dict_row,
    )


def get_connection():
    # Optional compatibility/testing path.
    database_url = (
        os.getenv("DATABASE_URL")
        or DATABASE_URL
    )

    if database_url:
        return psycopg.connect(
            database_url,
            row_factory=dict_row,
        )

    # Production path:
    # AppRole + dynamic Vault DB credentials.
    config = _vault_config()

    try:
        return (
            _connect_with_dynamic_credentials(
                config
            )
        )

    except psycopg.OperationalError as exc:
        sqlstate = getattr(
            exc,
            "sqlstate",
            None,
        )

        message = str(exc).lower()

        auth_failure = (
            (
                sqlstate is not None
                and sqlstate.startswith("28")
            )
            or (
                "password authentication failed"
                in message
            )
            or (
                "role" in message
                and "does not exist" in message
            )
        )

        if not auth_failure:
            raise

        _invalidate_database_credentials()

        return (
            _connect_with_dynamic_credentials(
                config
            )
        )
