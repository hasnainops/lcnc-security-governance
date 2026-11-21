#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

policies=(
  lcnc-access-viewer
  lcnc-access-developer
  lcnc-security-reviewer
  lcnc-senior-security-reviewer
)

echo "Checking existing development Vault..."

docker compose exec -T vault sh -lc '
  set -eu
  test -n "${VAULT_DEV_ROOT_TOKEN_ID:-}"

  export VAULT_ADDR=http://127.0.0.1:8200
  export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

  vault status >/dev/null
  vault policy list >/dev/null
'

echo "Vault available. Installing missing policies only."

for policy in "${policies[@]}"; do
  source_file="vault/policies/${policy}.hcl"

  test -f "$source_file"

  docker compose cp \
    "$source_file" \
    "vault:/tmp/${policy}.hcl" >/dev/null

  docker compose exec -T vault sh -lc '
    set -eu

    policy="$1"

    export VAULT_ADDR=http://127.0.0.1:8200
    export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

    if vault policy read "$policy" >/dev/null 2>&1; then
      echo "EXISTING — unchanged: $policy"
    else
      vault policy write \
        "$policy" \
        "/tmp/${policy}.hcl"

      echo "INSTALLED: $policy"
    fi
  ' sh "$policy"
done

echo
echo "===== LIVE VAULT POLICY NAMES ====="

docker compose exec -T vault sh -lc '
  set -eu

  export VAULT_ADDR=http://127.0.0.1:8200
  export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

  vault policy list
'

echo
echo "===== ENABLED AUTHENTICATION METHODS ====="

docker compose exec -T vault sh -lc '
  set -eu

  export VAULT_ADDR=http://127.0.0.1:8200
  export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"

  vault auth list
'

echo
echo "PASS: Missing LO4 policies provisioned."
echo "Existing policies were not overwritten."
echo "No tokens or user identities were created."
