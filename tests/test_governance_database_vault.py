import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

MODULE_PATH = (
    ROOT
    / "governance-api"
    / "app"
    / "database.py"
)

SPEC = importlib.util.spec_from_file_location(
    "governance_database_vault_test",
    MODULE_PATH,
)

database = importlib.util.module_from_spec(
    SPEC
)

SPEC.loader.exec_module(database)


class FakeResponse:
    def __init__(
        self,
        status_code,
        payload,
    ):
        self.status_code = status_code
        self._payload = payload
        self.raise_called = False

    def json(self):
        return self._payload

    def raise_for_status(self):
        self.raise_called = True

        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )


@pytest.fixture(autouse=True)
def reset_database_caches(monkeypatch):
    monkeypatch.setattr(
        database,
        "_cached_vault_token",
        None,
    )
    monkeypatch.setattr(
        database,
        "_vault_token_valid_until",
        0.0,
    )
    monkeypatch.setattr(
        database,
        "_cached_db_username",
        None,
    )
    monkeypatch.setattr(
        database,
        "_cached_db_password",
        None,
    )
    monkeypatch.setattr(
        database,
        "_db_credentials_valid_until",
        0.0,
    )


def test_cache_deadline_uses_ttl_safety_margin(
    monkeypatch,
):
    monkeypatch.setattr(
        database.time,
        "monotonic",
        lambda: 100.0,
    )

    assert (
        database._cache_deadline(100)
        == 190.0
    )

    assert (
        database._cache_deadline(10)
        == 105.0
    )


def test_vault_config_requires_runtime_settings(
    monkeypatch,
):
    for key in (
        "VAULT_ROLE_ID",
        "VAULT_SECRET_ID_FILE",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(
            key,
            raising=False,
        )

    with pytest.raises(RuntimeError) as exc:
        database._vault_config()

    detail = str(exc.value)

    assert "VAULT_ROLE_ID" in detail
    assert "VAULT_SECRET_ID_FILE" in detail
    assert "POSTGRES_DB" in detail


def test_vault_config_reads_secret_id(
    monkeypatch,
    tmp_path,
):
    secret_file = tmp_path / "secret-id"
    secret_file.write_text(
        "secret-value\n"
    )

    monkeypatch.setenv(
        "VAULT_ROLE_ID",
        "role-test",
    )
    monkeypatch.setenv(
        "VAULT_SECRET_ID_FILE",
        str(secret_file),
    )
    monkeypatch.setenv(
        "POSTGRES_DB",
        "lcnc",
    )
    monkeypatch.setenv(
        "VAULT_ADDR",
        "http://vault-test:8200/",
    )
    monkeypatch.setenv(
        "VAULT_DB_ROLE",
        "governance-test",
    )

    config = database._vault_config()

    assert (
        config["vault_addr"]
        == "http://vault-test:8200"
    )
    assert config["role_id"] == "role-test"
    assert (
        config["secret_id"]
        == "secret-value"
    )
    assert (
        config["vault_db_role"]
        == "governance-test"
    )
    assert config["postgres_db"] == "lcnc"


def test_login_to_vault_uses_and_reuses_cached_token(
    monkeypatch,
):
    calls = []

    def fake_post(
        url,
        *,
        json,
        timeout,
    ):
        calls.append(
            {
                "url": url,
                "json": json,
                "timeout": timeout,
            }
        )

        return FakeResponse(
            200,
            {
                "auth": {
                    "client_token": (
                        "vault-token"
                    ),
                    "lease_duration": 120,
                },
            },
        )

    monkeypatch.setattr(
        database.httpx,
        "post",
        fake_post,
    )

    monkeypatch.setattr(
        database.time,
        "monotonic",
        lambda: 100.0,
    )

    config = {
        "vault_addr": (
            "http://vault:8200"
        ),
        "role_id": "role-test",
        "secret_id": "secret-test",
    }

    first = database._login_to_vault(
        config
    )

    second = database._login_to_vault(
        config
    )

    assert first == "vault-token"
    assert second == "vault-token"
    assert len(calls) == 1
    assert calls[0]["url"].endswith(
        "/v1/auth/approle/login"
    )
    assert calls[0]["json"] == {
        "role_id": "role-test",
        "secret_id": "secret-test",
    }


def test_get_database_credentials_reauthenticates_after_403(
    monkeypatch,
):
    login_calls = []

    def fake_login(
        config,
        force=False,
    ):
        login_calls.append(force)

        if force:
            return "fresh-token"

        return "old-token"

    responses = [
        FakeResponse(
            403,
            {},
        ),
        FakeResponse(
            200,
            {
                "lease_duration": 900,
                "data": {
                    "username": (
                        "dynamic-user"
                    ),
                    "password": (
                        "dynamic-pass"
                    ),
                },
            },
        ),
    ]

    request_tokens = []

    def fake_request(
        config,
        token,
    ):
        request_tokens.append(token)
        return responses.pop(0)

    monkeypatch.setattr(
        database,
        "_login_to_vault",
        fake_login,
    )

    monkeypatch.setattr(
        database,
        "_request_database_credentials",
        fake_request,
    )

    monkeypatch.setattr(
        database,
        "_cache_deadline",
        lambda ttl: 999.0,
    )

    credentials = (
        database
        ._get_database_credentials(
            {
                "vault_addr": (
                    "http://vault:8200"
                ),
                "vault_db_role": (
                    "governance-api"
                ),
            }
        )
    )

    assert credentials == (
        "dynamic-user",
        "dynamic-pass",
    )

    assert login_calls == [
        False,
        True,
    ]

    assert request_tokens == [
        "old-token",
        "fresh-token",
    ]

    assert (
        database._cached_db_username
        == "dynamic-user"
    )
    assert (
        database._cached_db_password
        == "dynamic-pass"
    )


def test_get_database_credentials_rejects_invalid_secret(
    monkeypatch,
):
    monkeypatch.setattr(
        database,
        "_login_to_vault",
        lambda config: "vault-token",
    )

    monkeypatch.setattr(
        database,
        "_request_database_credentials",
        lambda config, token: FakeResponse(
            200,
            {
                "lease_duration": 0,
                "data": {},
            },
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Vault database secrets engine "
            "returned invalid credentials"
        ),
    ):
        database._get_database_credentials(
            {
                "vault_addr": (
                    "http://vault:8200"
                ),
                "vault_db_role": (
                    "governance-api"
                ),
            }
        )


def test_invalidate_database_credentials():
    database._cached_db_username = (
        "old-user"
    )
    database._cached_db_password = (
        "old-password"
    )
    database._db_credentials_valid_until = (
        999.0
    )

    database._invalidate_database_credentials()

    assert (
        database._cached_db_username
        is None
    )
    assert (
        database._cached_db_password
        is None
    )
    assert (
        database._db_credentials_valid_until
        == 0.0
    )


def test_connect_with_dynamic_credentials(
    monkeypatch,
):
    monkeypatch.setattr(
        database,
        "_get_database_credentials",
        lambda config: (
            "dynamic-user",
            "dynamic-pass",
        ),
    )

    captured = {}
    connection = object()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(
        database.psycopg,
        "connect",
        fake_connect,
    )

    config = {
        "postgres_host": "postgres",
        "postgres_port": 5432,
        "postgres_db": "lcnc",
        "postgres_sslmode": "disable",
    }

    result = (
        database
        ._connect_with_dynamic_credentials(
            config
        )
    )

    assert result is connection
    assert captured["host"] == "postgres"
    assert captured["port"] == 5432
    assert captured["dbname"] == "lcnc"
    assert captured["user"] == (
        "dynamic-user"
    )
    assert captured["password"] == (
        "dynamic-pass"
    )
    assert captured["connect_timeout"] == 5
    assert (
        captured["row_factory"]
        is database.dict_row
    )


def test_get_connection_uses_database_url_compatibility_path(
    monkeypatch,
):
    database_url = (
        "postgresql://test:test@localhost:5432/test"
    )

    monkeypatch.setenv(
        "DATABASE_URL",
        database_url,
    )

    captured = {}
    connection = object()

    def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return connection

    monkeypatch.setattr(
        database.psycopg,
        "connect",
        fake_connect,
    )

    result = database.get_connection()

    assert result is connection
    assert captured["args"] == (
        database_url,
    )
    assert (
        captured["kwargs"]["row_factory"]
        is database.dict_row
    )


def test_get_connection_uses_vault_dynamic_credentials_path(
    monkeypatch,
):
    monkeypatch.delenv(
        "DATABASE_URL",
        raising=False,
    )

    monkeypatch.setattr(
        database,
        "DATABASE_URL",
        None,
    )

    config = {
        "vault_addr": "http://vault:8200",
        "role_id": "role-test",
        "secret_id": "secret-test",
        "vault_db_role": "governance-api",
        "postgres_host": "postgres",
        "postgres_port": 5432,
        "postgres_db": "lcnc",
        "postgres_sslmode": "disable",
    }

    monkeypatch.setattr(
        database,
        "_vault_config",
        lambda: config,
    )

    connection = object()
    calls = []

    def fake_dynamic_connect(current_config):
        calls.append(current_config)
        return connection

    monkeypatch.setattr(
        database,
        "_connect_with_dynamic_credentials",
        fake_dynamic_connect,
    )

    result = database.get_connection()

    assert result is connection
    assert calls == [config]
