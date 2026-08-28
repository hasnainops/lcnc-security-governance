#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/.." &&
  pwd
)"

cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found."
  exit 1
fi

set -a
source .env
set +a

echo "==> Checking Vault container..."

if ! docker compose ps vault --status running \
  --format '{{.Service}}' | grep -q '^vault$'; then
  echo "ERROR: Vault container is not running."
  echo "Start the platform first with: docker compose up -d"
  exit 1
fi

echo "==> Configuring Vault database secrets engine..."

docker compose exec -T \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB="$POSTGRES_DB" \
  vault sh -lc '
set -e

export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

if ! vault secrets list -format=json \
  | grep -q "\"database/\""; then
  vault secrets enable database
fi

vault write database/config/lcnc-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles=governance-api \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/${POSTGRES_DB}?sslmode=disable" \
  username="$POSTGRES_USER" \
  password="$POSTGRES_PASSWORD"

vault write database/roles/governance-api \
  db_name=lcnc-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\''; GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl=15m \
  max_ttl=1h
'

echo "==> Configuring Vault policy and AppRole..."

docker compose cp \
  vault/governance-api.hcl \
  vault:/tmp/governance-api.hcl >/dev/null

docker compose exec -T vault sh -lc '
set -e

export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

vault policy write \
  governance-api \
  /tmp/governance-api.hcl

if ! vault auth list -format=json \
  | grep -q "\"approle/\""; then
  vault auth enable approle
fi

vault write auth/approle/role/governance-api \
  token_policies="governance-api" \
  token_type=batch \
  secret_id_ttl=24h \
  secret_id_num_uses=50 \
  token_ttl=20m \
  token_max_ttl=30m
'

echo "==> Generating fresh AppRole credentials..."

VAULT_ROLE_ID="$(
  docker compose exec -T vault sh -lc '
    export VAULT_ADDR=http://127.0.0.1:8200
    export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

    vault read \
      -field=role_id \
      auth/approle/role/governance-api/role-id
  '
)"

VAULT_SECRET_ID="$(
  docker compose exec -T vault sh -lc '
    export VAULT_ADDR=http://127.0.0.1:8200
    export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

    vault write \
      -field=secret_id \
      -f auth/approle/role/governance-api/secret-id
  '
)"

export VAULT_ROLE_ID
export VAULT_SECRET_ID

python3 - <<'PY'
import os
from pathlib import Path

path = Path(".env")

lines = path.read_text().splitlines()

updates = {
    "VAULT_ROLE_ID": os.environ["VAULT_ROLE_ID"],
    "VAULT_SECRET_ID": os.environ["VAULT_SECRET_ID"],
}

result = []
seen = set()

for line in lines:
    if "=" in line:
        key = line.split("=", 1)[0]

        if key in updates:
            result.append(f"{key}={updates[key]}")
            seen.add(key)
            continue

    result.append(line)

for key, value in updates.items():
    if key not in seen:
        result.append(f"{key}={value}")

path.write_text("\n".join(result) + "\n")
PY

chmod 600 .env

unset VAULT_ROLE_ID
unset VAULT_SECRET_ID

echo "==> Recreating Governance API replicas with fresh AppRole credentials..."

docker compose up -d \
  --force-recreate \
  --no-deps \
  governance-api-a \
  governance-api-b

echo
echo "Vault bootstrap completed."
echo "No Vault credentials were printed."
