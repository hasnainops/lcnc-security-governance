#!/usr/bin/env python3
"""Issue/revoke an application-scoped MVP credential using the local DB operator.

No raw credential is printed or placed in process arguments. Issuance records
the operator's assignment of a named subject; it does not claim SSO identity.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
from uuid import UUID, uuid4


ROOT = Path(__file__).resolve().parents[1]


def database_json(statement):
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "sh", "-eu", "-c",
         'exec psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        cwd=ROOT, input=statement, capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Database operation failed; raw SQL and credentials withheld")
    return json.loads(result.stdout.strip())


def sql_document(document):
    encoded = base64.b64encode(json.dumps(document).encode()).decode("ascii")
    return f"SELECT convert_from(decode('{encoded}', 'base64'), 'UTF8')::jsonb AS value"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-id", type=UUID)
    parser.add_argument("--subject-id")
    parser.add_argument("--owner-name")
    parser.add_argument("--owner-email")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--revoke", type=UUID)
    args = parser.parse_args()
    if args.revoke:
        result = database_json(
            "BEGIN; SELECT pg_advisory_xact_lock(hashtextextended(token_sha256, 0)) "
            f"FROM application_owner_credentials WHERE id = '{args.revoke}'::uuid; "
            "WITH changed AS (UPDATE application_owner_credentials SET revoked_at = NOW() "
            f"WHERE id = '{args.revoke}'::uuid AND revoked_at IS NULL RETURNING id) "
            "SELECT json_build_object('revoked', COUNT(*)) FROM changed; COMMIT;"
        )
        print("Credentials revoked:", result["revoked"])
        return
    if not all((args.application_id, args.subject_id, args.owner_name, args.owner_email)):
        parser.error("application-id, subject-id, owner-name and owner-email are required")
    if not 1 <= args.days <= 30:
        parser.error("days must be between 1 and 30")
    for value in (args.subject_id, args.owner_name, args.owner_email):
        if not value.strip() or len(value) > 255 or any(ord(c) < 32 for c in value):
            parser.error("Identity fields must be nonempty text up to 255 characters")
    if "@" not in args.owner_email:
        parser.error("Supply the assigned owner's email address")
    credential_id = uuid4()
    token = "lo1_" + secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=args.days)
    document = {
        "id": str(credential_id), "application_id": str(args.application_id),
        "subject_id": args.subject_id.strip(), "owner_name": args.owner_name.strip(),
        "owner_email": args.owner_email.strip(), "issued_by": getpass.getuser(),
        "expires_at": expires.isoformat(), "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }
    output = args.output or ROOT / ".runtime-secrets/owner-context" / f"{credential_id}.json"
    output = output.expanduser().absolute()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump({"application_id": str(args.application_id), "credential_id": str(credential_id),
                       "token": token, "expires_at": expires.isoformat()}, handle)
            handle.write("\n")
        result = database_json(
            "WITH d AS (" + sql_document(document) + "), inserted AS ("
            "INSERT INTO application_owner_credentials "
            "(id, application_id, token_sha256, subject_id, owner_name, owner_email, issued_by, expires_at) "
            "SELECT (value->>'id')::uuid, a.id, value->>'token_sha256', value->>'subject_id', "
            "value->>'owner_name', value->>'owner_email', value->>'issued_by', (value->>'expires_at')::timestamptz "
            "FROM d JOIN applications a ON a.id=(value->>'application_id')::uuid "
            "WHERE a.platform='appsmith' RETURNING id) "
            "SELECT json_build_object('issued', COUNT(*)) FROM inserted;"
        )
        if result["issued"] != 1:
            raise RuntimeError("An existing Appsmith inventory application is required")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    print("Issued owner-context credential for:", args.application_id)
    print("Credential ID (for revocation):", credential_id)
    print("Expires:", expires.isoformat())
    print("Private credential file:", output)
    print("Load this file in the portal's Owner context page. Do not share its contents.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print("STOP: owner credential operation failed (" + type(exc).__name__ + ").")
        raise SystemExit(1)
