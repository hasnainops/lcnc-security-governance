"""Supervised LO4.3 acceptance with administrative fixture cleanup.

Run from the repository on the Docker host.

The Governance API retains least-privilege DB access.
The PostgreSQL administrative account is used only for
exactly scoped test-fixture cleanup.
"""

import re
import subprocess
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]

TEST_SCRIPT = (
    ROOT / "scripts" / "verify-lo4-egress-prevention.py"
)

APP_NAME = "LO4 Isolated Egress Prevention Fixture"
PLATFORM = "isolated-acceptance"


CLEANUP_SQL = r"""
BEGIN;

SELECT set_config(
    'lo4.cleanup_external_id',
    :'fixture',
    true
);

DO $cleanup$
DECLARE
    target_id uuid;
    fixture_count integer;
    receipt_count integer;
    invalid_receipts integer;
    deleted_count integer;
BEGIN

    SELECT COUNT(*)
    INTO fixture_count
    FROM applications
    WHERE external_id = current_setting(
        'lo4.cleanup_external_id'
    )
      AND name = 'LO4 Isolated Egress Prevention Fixture'
      AND platform = 'isolated-acceptance';

    IF fixture_count > 1 THEN
        RAISE EXCEPTION
            'Ambiguous LO4 fixture; refusing cleanup';
    END IF;

    IF fixture_count = 0 THEN
        RAISE NOTICE
            'No test application was created; nothing to clean';
        RETURN;
    END IF;

    SELECT id
    INTO target_id
    FROM applications
    WHERE external_id = current_setting(
        'lo4.cleanup_external_id'
    )
      AND name = 'LO4 Isolated Egress Prevention Fixture'
      AND platform = 'isolated-acceptance'
    FOR UPDATE;

    IF target_id IS NULL THEN
        RAISE EXCEPTION
            'Fixture disappeared during cleanup';
    END IF;

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE decision <> 'block'
               OR allowed IS DISTINCT FROM FALSE
               OR upstream_status_code IS NOT NULL
               OR enforcement_outcome IS DISTINCT FROM 'blocked_before_send'
        )
    INTO receipt_count, invalid_receipts
    FROM integration_transfer_events
    WHERE application_id = target_id;

    IF receipt_count > 1 OR invalid_receipts > 0 THEN
        RAISE EXCEPTION
            'Unexpected LO4 transfer evidence; refusing cleanup';
    END IF;

    DELETE FROM applications
    WHERE id = target_id
      AND external_id = current_setting(
          'lo4.cleanup_external_id'
      )
      AND name = 'LO4 Isolated Egress Prevention Fixture'
      AND platform = 'isolated-acceptance';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    IF deleted_count <> 1 THEN
        RAISE EXCEPTION
            'Unexpected fixture deletion count';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM integration_transfer_events
        WHERE application_id = target_id
    ) THEN
        RAISE EXCEPTION
            'Fixture transfer records remain';
    END IF;

    RAISE NOTICE
        'PASS: Exactly one scoped LO4 test application deleted';

    RAISE NOTICE
        'PASS: Associated test audit evidence cleaned';

END
$cleanup$;

COMMIT;

SELECT
    'Remaining matching fixtures: ' || COUNT(*)
FROM applications
WHERE external_id = :'fixture'
  AND name = 'LO4 Isolated Egress Prevention Fixture'
  AND platform = 'isolated-acceptance';
"""


def compose(*args, input_text=None):
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=input_text,
        text=True,
        check=True,
    )


def cleanup(external_id):
    assert re.fullmatch(
        r"lo4-egress-audit-[0-9a-f]{32}",
        external_id,
    )

    print(
        "\n===== ADMINISTRATIVE FIXTURE CLEANUP =====",
        flush=True,
    )

    # Credentials remain inside the PostgreSQL container.
    # Only the precisely generated fixture identifier is
    # passed to psql as a parameter.
    compose(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        (
            'set -eu; '
            ': "${POSTGRES_USER:?}"; '
            'DB="${POSTGRES_DB:-$POSTGRES_USER}"; '
            'exec psql -X -v ON_ERROR_STOP=1 '
            '-U "$POSTGRES_USER" -d "$DB" '
            '-v "fixture=$1"'
        ),
        "lo4-admin",
        external_id,
        input_text=CLEANUP_SQL,
    )


def main():
    assert TEST_SCRIPT.is_file()

    suffix = uuid4().hex
    external_id = "lo4-egress-audit-" + suffix

    print(
        "===== LO4.3 SUPERVISED ENFORCEMENT ACCEPTANCE =====",
        flush=True,
    )

    print(
        "Normal API credentials are not granted "
        "administrative DELETE privileges.",
        flush=True,
    )

    try:
        compose(
            "exec",
            "-T",
            "-e",
            "LO4_EGRESS_SUPERVISED=1",
            "-e",
            f"LO4_EGRESS_SUFFIX={suffix}",
            "governance-api-a",
            "python",
            "-",
            input_text=TEST_SCRIPT.read_text(),
        )
    finally:
        # Runs even if the container acceptance fails.
        # SQL refuses ambiguous or unexpected evidence.
        cleanup(external_id)

    print(
        "\nPASS: Supervised acceptance and cleanup completed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
