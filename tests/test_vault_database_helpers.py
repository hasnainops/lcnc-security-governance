import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

DATABASE_MODULES = [
    (
        "governance_automation_database",
        ROOT
        / "governance-automation"
        / "app"
        / "database.py",
    ),
    (
        "enterprise_discovery_database",
        ROOT
        / "enterprise-discovery"
        / "app"
        / "database.py",
    ),
]


def load_database_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


@pytest.fixture(
    params=DATABASE_MODULES,
    ids=[
        "governance-automation",
        "enterprise-discovery",
    ],
)
def database_module(request):
    name, path = request.param

    return load_database_module(
        name,
        path,
    )


def configure_environment(
    monkeypatch,
    secret_file,
):
    monkeypatch.setenv(
        "VAULT_ROLE_ID",
        "role-test",
    )
    monkeypatch.setenv(
        "VAULT_SECRET_ID_FILE",
        str(secret_file),
    )
    monkeypatch.setenv(
        "VAULT_DB_ROLE",
        "database-role-test",
    )
    monkeypatch.setenv(
        "POSTGRES_DB",
        "lcnc",
    )


def test_config_requires_vault_database_settings(
    database_module,
    monkeypatch,
):
    for key in (
        "VAULT_ROLE_ID",
        "VAULT_SECRET_ID_FILE",
        "VAULT_DB_ROLE",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(
            key,
            raising=False,
        )

    with pytest.raises(RuntimeError) as exc:
        database_module._config()

    detail = str(exc.value)

    assert "VAULT_ROLE_ID" in detail
    assert "VAULT_SECRET_ID_FILE" in detail
    assert "VAULT_DB_ROLE" in detail
    assert "POSTGRES_DB" in detail


def test_config_returns_expected_runtime_settings(
    database_module,
    monkeypatch,
    tmp_path,
):
    secret_file = (
        tmp_path
        / "secret-id"
    )

    configure_environment(
        monkeypatch,
        secret_file,
    )

    monkeypatch.setenv(
        "VAULT_ADDR",
        "http://vault-test:8200/",
    )
    monkeypatch.setenv(
        "POSTGRES_HOST",
        "postgres-test",
    )
    monkeypatch.setenv(
        "POSTGRES_PORT",
        "6543",
    )
    monkeypatch.setenv(
        "POSTGRES_SSLMODE",
        "require",
    )

    config = database_module._config()

    assert (
        config["vault_addr"]
        == "http://vault-test:8200"
    )
    assert config["role_id"] == "role-test"
    assert (
        config["db_role"]
        == "database-role-test"
    )
    assert (
        config["postgres_host"]
        == "postgres-test"
    )
    assert config["postgres_port"] == 6543
    assert config["postgres_db"] == "lcnc"
    assert (
        config["postgres_sslmode"]
        == "require"
    )


def test_read_secret_id(
    database_module,
    tmp_path,
):
    secret_file = (
        tmp_path
        / "secret-id"
    )

    secret_file.write_text(
        "secret-value\n"
    )

    assert (
        database_module._read_secret_id(
            secret_file
        )
        == "secret-value"
    )


def test_read_secret_id_rejects_missing_file(
    database_module,
    tmp_path,
):
    missing = (
        tmp_path
        / "missing-secret-id"
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Unable to read Vault "
            "AppRole SecretID file"
        ),
    ):
        database_module._read_secret_id(
            missing
        )


def test_read_secret_id_rejects_empty_file(
    database_module,
    tmp_path,
):
    secret_file = (
        tmp_path
        / "secret-id"
    )

    secret_file.write_text(" \n")

    with pytest.raises(
        RuntimeError,
        match=(
            "Vault AppRole SecretID "
            "file is empty"
        ),
    ):
        database_module._read_secret_id(
            secret_file
        )


def test_vault_request_sends_payload_and_token(
    database_module,
    monkeypatch,
):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def read(self):
            return json.dumps(
                {
                    "ok": True,
                }
            ).encode()

    def fake_urlopen(
        request,
        timeout,
    ):
        captured["request"] = request
        captured["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setattr(
        database_module.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    result = database_module._vault_request(
        "POST",
        "http://vault:8200/v1/test",
        token="token-value",
        payload={
            "role_id": "role-test",
        },
    )

    request = captured["request"]

    assert result == {"ok": True}
    assert captured["timeout"] == 5
    assert request.get_method() == "POST"
    assert json.loads(
        request.data.decode()
    ) == {
        "role_id": "role-test",
    }
    assert (
        request.headers["X-vault-token"]
        == "token-value"
    )


def test_login_uses_secret_id_and_caches_token(
    database_module,
    monkeypatch,
    tmp_path,
):
    secret_file = (
        tmp_path
        / "secret-id"
    )

    secret_file.write_text(
        "secret-value"
    )

    captured = {}

    def fake_vault_request(
        method,
        url,
        *,
        token=None,
        payload=None,
    ):
        captured.update(
            {
                "method": method,
                "url": url,
                "token": token,
                "payload": payload,
            }
        )

        return {
            "auth": {
                "client_token": (
                    "runtime-token"
                ),
            },
        }

    monkeypatch.setattr(
        database_module,
        "_vault_request",
        fake_vault_request,
    )

    config = {
        "vault_addr": (
            "http://vault:8200"
        ),
        "role_id": "role-test",
        "secret_id_file": str(
            secret_file
        ),
    }

    token = database_module._login(
        config
    )

    assert token == "runtime-token"
    assert (
        database_module._vault_token
        == "runtime-token"
    )
    assert captured["method"] == "POST"
    assert captured["url"].endswith(
        "/v1/auth/approle/login"
    )
    assert captured["payload"] == {
        "role_id": "role-test",
        "secret_id": "secret-value",
    }


def test_login_rejects_missing_client_token(
    database_module,
    monkeypatch,
    tmp_path,
):
    secret_file = (
        tmp_path
        / "secret-id"
    )

    secret_file.write_text(
        "secret-value"
    )

    monkeypatch.setattr(
        database_module,
        "_vault_request",
        lambda *args, **kwargs: {
            "auth": {},
        },
    )

    config = {
        "vault_addr": (
            "http://vault:8200"
        ),
        "role_id": "role-test",
        "secret_id_file": str(
            secret_file
        ),
    }

    with pytest.raises(
        RuntimeError,
        match=(
            "Vault AppRole "
            "authentication failed"
        ),
    ):
        database_module._login(
            config
        )


def test_runtime_token_renews_existing_token(
    database_module,
    monkeypatch,
):
    database_module._vault_token = (
        "old-token"
    )

    captured = {}

    def fake_vault_request(
        method,
        url,
        *,
        token=None,
        payload=None,
    ):
        captured["token"] = token
        captured["url"] = url

        return {
            "auth": {
                "client_token": (
                    "renewed-token"
                ),
            },
        }

    monkeypatch.setattr(
        database_module,
        "_vault_request",
        fake_vault_request,
    )

    token = database_module._runtime_token(
        {
            "vault_addr": (
                "http://vault:8200"
            ),
        }
    )

    assert token == "renewed-token"
    assert (
        database_module._vault_token
        == "renewed-token"
    )
    assert captured["token"] == "old-token"
    assert captured["url"].endswith(
        "/v1/auth/token/renew-self"
    )


def test_runtime_token_reauthenticates_after_renew_failure(
    database_module,
    monkeypatch,
):
    database_module._vault_token = (
        "expired-token"
    )

    monkeypatch.setattr(
        database_module,
        "_vault_request",
        lambda *args, **kwargs: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "renew failed"
                )
            )
        ),
    )

    monkeypatch.setattr(
        database_module,
        "_login",
        lambda config: "fresh-token",
    )

    token = database_module._runtime_token(
        {
            "vault_addr": (
                "http://vault:8200"
            ),
        }
    )

    assert token == "fresh-token"
    assert (
        database_module._vault_token
        is None
    )


def test_database_credentials_fetch_and_cache(
    database_module,
    monkeypatch,
):
    database_module._db_username = None
    database_module._db_password = None
    database_module._db_valid_until = 0.0

    times = iter(
        [
            100.0,
            100.0,
            100.0,
            101.0,
        ]
    )

    monkeypatch.setattr(
        database_module.time,
        "monotonic",
        lambda: next(times),
    )

    monkeypatch.setattr(
        database_module,
        "_runtime_token",
        lambda config: "runtime-token",
    )

    calls = []

    def fake_vault_request(
        method,
        url,
        *,
        token=None,
        payload=None,
    ):
        calls.append(
            {
                "method": method,
                "url": url,
                "token": token,
            }
        )

        return {
            "lease_duration": 900,
            "data": {
                "username": "dynamic-user",
                "password": "dynamic-pass",
            },
        }

    monkeypatch.setattr(
        database_module,
        "_vault_request",
        fake_vault_request,
    )

    config = {
        "vault_addr": (
            "http://vault:8200"
        ),
        "db_role": "database-role-test",
    }

    first = (
        database_module
        ._database_credentials(
            config
        )
    )

    second = (
        database_module
        ._database_credentials(
            config
        )
    )

    assert first == (
        "dynamic-user",
        "dynamic-pass",
    )
    assert second == first
    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["token"] == (
        "runtime-token"
    )
    assert calls[0]["url"].endswith(
        "/v1/database/creds/"
        "database-role-test"
    )


def test_database_credentials_reject_invalid_vault_response(
    database_module,
    monkeypatch,
):
    database_module._db_username = None
    database_module._db_password = None
    database_module._db_valid_until = 0.0

    monkeypatch.setattr(
        database_module,
        "_runtime_token",
        lambda config: "runtime-token",
    )

    monkeypatch.setattr(
        database_module,
        "_vault_request",
        lambda *args, **kwargs: {
            "lease_duration": 0,
            "data": {},
        },
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Vault returned invalid "
            "database credentials"
        ),
    ):
        database_module._database_credentials(
            {
                "vault_addr": (
                    "http://vault:8200"
                ),
                "db_role": (
                    "database-role-test"
                ),
            }
        )


def test_get_connection_uses_dynamic_credentials(
    database_module,
    monkeypatch,
):
    config = {
        "vault_addr": (
            "http://vault:8200"
        ),
        "role_id": "role-test",
        "secret_id_file": (
            "/runtime/secret-id"
        ),
        "db_role": "database-role-test",
        "postgres_host": "postgres",
        "postgres_port": 5432,
        "postgres_db": "lcnc",
        "postgres_sslmode": "disable",
    }

    monkeypatch.setattr(
        database_module,
        "_config",
        lambda: config,
    )

    monkeypatch.setattr(
        database_module,
        "_database_credentials",
        lambda current_config: (
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
        database_module.psycopg,
        "connect",
        fake_connect,
    )

    result = database_module.get_connection()

    assert result is connection
    assert captured["host"] == "postgres"
    assert captured["port"] == 5432
    assert captured["dbname"] == "lcnc"
    assert captured["user"] == "dynamic-user"
    assert (
        captured["password"]
        == "dynamic-pass"
    )
    assert captured["sslmode"] == "disable"
    assert (
        captured["row_factory"]
        is database_module.dict_row
    )
