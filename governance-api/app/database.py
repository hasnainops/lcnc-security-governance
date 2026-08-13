import os
import threading
import time

import httpx
import psycopg
from psycopg.rows import dict_row


VAULT_ADDR = os.getenv(
    "VAULT_ADDR",
    "http://vault:8200",
).rstrip("/")

VAULT_ROLE_ID = os.environ["VAULT_ROLE_ID"]
VAULT_SECRET_ID = os.environ["VAULT_SECRET_ID"]

VAULT_DB_ROLE = os.getenv(
    "VAULT_DB_ROLE",
    "governance-api",
)

POSTGRES_HOST = os.getenv(
    "POSTGRES_HOST",
    "postgres",
)

POSTGRES_PORT = int(
    os.getenv(
        "POSTGRES_PORT",
        "5432",
    )
)

POSTGRES_DB = os.environ["POSTGRES_DB"]

POSTGRES_SSLMODE = os.getenv(
    "POSTGRES_SSLMODE",
    "disable",
)


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


def _login_to_vault(force=False):
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
                f"{VAULT_ADDR}"
                "/v1/auth/approle/login"
            ),
            json={
                "role_id": VAULT_ROLE_ID,
                "secret_id": VAULT_SECRET_ID,
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


def _request_database_credentials(token):
    response = httpx.get(
        (
            f"{VAULT_ADDR}"
            f"/v1/database/creds/{VAULT_DB_ROLE}"
        ),
        headers={
            "X-Vault-Token": token,
        },
        timeout=5.0,
    )

    return response


def _get_database_credentials():
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

        token = _login_to_vault()

        response = _request_database_credentials(
            token
        )

        if response.status_code in {
            400,
            403,
        }:
            _cached_vault_token = None
            _vault_token_valid_until = 0.0

            token = _login_to_vault(
                force=True
            )

            response = (
                _request_database_credentials(
                    token
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


def get_connection():
    username, password = (
        _get_database_credentials()
    )

    return psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=username,
        password=password,
        sslmode=POSTGRES_SSLMODE,
        connect_timeout=5,
        row_factory=dict_row,
    )
