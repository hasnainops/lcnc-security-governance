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
  allowed_roles="governance-api,enterprise-discovery,governance-automation" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/${POSTGRES_DB}?sslmode=disable" \
  username="$POSTGRES_USER" \
  password="$POSTGRES_PASSWORD"

vault write database/roles/governance-api \
  db_name=lcnc-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\''; GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT SELECT, INSERT ON TABLE public.access_decisions, public.classification_assessments, public.dynamic_compliance_assessments, public.governance_decisions, public.integration_transfer_events, public.ml_assessments, public.policy_decisions, public.risk_assessments, public.security_findings, public.security_scans TO \"{{name}}\"; GRANT SELECT, INSERT, UPDATE ON TABLE public.applications, public.training_assignments, public.training_completions TO \"{{name}}\"; GRANT INSERT ON TABLE public.training_events TO \"{{name}}\";" \
  default_ttl=15m \
  max_ttl=1h

vault write database/roles/enterprise-discovery \
  db_name=lcnc-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\''; GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT SELECT, INSERT, UPDATE ON TABLE public.enterprise_discoveries TO \"{{name}}\";" \
  default_ttl=15m \
  max_ttl=1h

vault write database/roles/governance-automation \
  db_name=lcnc-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\''; GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT SELECT ON TABLE public.applications, public.governance_decisions, public.risk_assessments, public.training_assignments TO \"{{name}}\"; GRANT SELECT, INSERT, UPDATE ON TABLE public.approval_requests, public.privilege_requests, public.privilege_grants TO \"{{name}}\"; GRANT INSERT ON TABLE public.approval_events, public.privilege_events TO \"{{name}}\";" \
  default_ttl=15m \
  max_ttl=1h
'

echo "==> Configuring managed Appsmith integration credential..."

if [[ -n "${APPSMITH_USER:-}" && -n "${APPSMITH_PASSWORD:-}" ]]; then
  docker compose exec -T \
    -e APPSMITH_USER="$APPSMITH_USER" \
    -e APPSMITH_PASSWORD="$APPSMITH_PASSWORD" \
    vault sh -lc '
set -e

export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

if ! vault secrets list -format=json \
  | grep -q "\"secret/\""; then
  vault secrets enable \
    -path=secret \
    -version=2 \
    kv >/dev/null
fi

vault kv put \
  secret/integrations/appsmith \
  username="$APPSMITH_USER" \
  password="$APPSMITH_PASSWORD" \
  >/dev/null
'
else
  if ! docker compose exec -T vault sh -lc '
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

vault kv get \
  secret/integrations/appsmith \
  >/dev/null
'; then
    echo "ERROR: Appsmith credential is not present in Vault."
    echo "Provide APPSMITH_USER and APPSMITH_PASSWORD once for bootstrap."
    exit 1
  fi
fi

echo "==> Configuring Vault policy and AppRole..."

for policy in \
  governance-api \
  enterprise-discovery \
  governance-automation \
  appsmith-discovery
do
  docker compose cp \
    "vault/${policy}.hcl" \
    "vault:/tmp/${policy}.hcl" >/dev/null
done

docker compose exec -T vault sh -lc '
set -e

export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

vault policy write \
  governance-api \
  /tmp/governance-api.hcl

vault policy write \
  enterprise-discovery \
  /tmp/enterprise-discovery.hcl

vault policy write \
  governance-automation \
  /tmp/governance-automation.hcl

vault policy write \
  appsmith-discovery \
  /tmp/appsmith-discovery.hcl

if ! vault auth list -format=json \
  | grep -q "\"approle/\""; then
  vault auth enable approle
fi

for role in \
  governance-api \
  enterprise-discovery \
  governance-automation \
  appsmith-discovery
do
  vault write "auth/approle/role/${role}" \
    token_policies="${role}" \
    token_type=service \
    secret_id_ttl=24h \
    secret_id_num_uses=50 \
    token_ttl=20m \
    token_max_ttl=1h
done
'

echo "==> Generating fresh workload AppRole credentials..."

SECRETS_DIR=".runtime-secrets"

umask 077
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

vault_role_id() {
  role="$1"

  docker compose exec -T vault sh -lc \
    "export VAULT_ADDR=http://127.0.0.1:8200; \
     export VAULT_TOKEN=\"\$VAULT_DEV_ROOT_TOKEN_ID\"; \
     vault read -field=role_id \
       auth/approle/role/${role}/role-id"
}

write_secret_id() {
  role="$1"
  destination="$2"

  secret_id="$(
    docker compose exec -T vault sh -lc \
      "export VAULT_ADDR=http://127.0.0.1:8200; \
       export VAULT_TOKEN=\"\$VAULT_DEV_ROOT_TOKEN_ID\"; \
       vault write -field=secret_id -f \
         auth/approle/role/${role}/secret-id"
  )"

  printf '%s\n' "$secret_id" > "$destination"
  chmod 600 "$destination"

  unset secret_id
}

VAULT_ROLE_ID="$(vault_role_id governance-api)"

ENTERPRISE_DISCOVERY_VAULT_ROLE_ID="$(
  vault_role_id enterprise-discovery
)"

GOVERNANCE_AUTOMATION_VAULT_ROLE_ID="$(
  vault_role_id governance-automation
)"

APPSMITH_DISCOVERY_VAULT_ROLE_ID="$(
  vault_role_id appsmith-discovery
)"

write_secret_id \
  governance-api \
  "$SECRETS_DIR/governance-api-secret-id"

write_secret_id \
  enterprise-discovery \
  "$SECRETS_DIR/enterprise-discovery-secret-id"

write_secret_id \
  governance-automation \
  "$SECRETS_DIR/governance-automation-secret-id"

write_secret_id \
  appsmith-discovery \
  "$SECRETS_DIR/appsmith-discovery-secret-id"

export VAULT_ROLE_ID
export ENTERPRISE_DISCOVERY_VAULT_ROLE_ID
export GOVERNANCE_AUTOMATION_VAULT_ROLE_ID
export APPSMITH_DISCOVERY_VAULT_ROLE_ID

python3 - <<'PYENV'
import os
from pathlib import Path

path = Path(".env")

lines = path.read_text().splitlines()

updates = {
    "VAULT_ROLE_ID":
        os.environ["VAULT_ROLE_ID"],
    "ENTERPRISE_DISCOVERY_VAULT_ROLE_ID":
        os.environ[
            "ENTERPRISE_DISCOVERY_VAULT_ROLE_ID"
        ],
    "GOVERNANCE_AUTOMATION_VAULT_ROLE_ID":
        os.environ[
            "GOVERNANCE_AUTOMATION_VAULT_ROLE_ID"
        ],
    "APPSMITH_DISCOVERY_VAULT_ROLE_ID":
        os.environ[
            "APPSMITH_DISCOVERY_VAULT_ROLE_ID"
        ],
}

remove = {
    "VAULT_SECRET_ID",
    "APPSMITH_USER",
    "APPSMITH_PASSWORD",
}

result = []
seen = set()

for line in lines:
    if "=" in line:
        key = line.split("=", 1)[0]

        if key in remove:
            continue

        if key in updates:
            result.append(
                f"{key}={updates[key]}"
            )
            seen.add(key)
            continue

    result.append(line)

for key, value in updates.items():
    if key not in seen:
        result.append(f"{key}={value}")

path.write_text(
    "\n".join(result) + "\n"
)
PYENV

chmod 600 .env

unset VAULT_ROLE_ID
unset ENTERPRISE_DISCOVERY_VAULT_ROLE_ID
unset GOVERNANCE_AUTOMATION_VAULT_ROLE_ID
unset APPSMITH_DISCOVERY_VAULT_ROLE_ID

echo "==> Rebuilding and recreating Vault-managed database workloads..."

docker compose up -d \
  --build \
  --force-recreate \
  --no-deps \
  governance-api-a \
  governance-api-b \
  enterprise-discovery \
  governance-automation \
  discovery

echo
echo "Vault bootstrap completed."
echo "No Vault credentials were printed."
