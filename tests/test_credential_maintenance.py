import contextlib
import importlib.util
import io
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / "scripts/maintain-vault-credentials.py"
spec = importlib.util.spec_from_file_location("maintenance", script)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


class ReportTests(unittest.TestCase):
    def run_report(self, uses=48, hours=24, locked=False, fail_lookup=False):
        expiry = datetime.now(timezone.utc) + timedelta(hours=hours)

        def fake_vault(*args, payload=None):
            endpoint = args[2]
            if endpoint == "sys/locked-users":
                return {"aliases": ["test-role"] if locked else []}
            if endpoint.endswith("/role-id"):
                return {"role_id": "test-role"}
            if endpoint.endswith("/secret-id/lookup"):
                self.assertEqual(args, (
                    "write", "-format=json",
                    "auth/approle/role/governance-api/secret-id/lookup", "-"
                ))
                self.assertEqual(payload, {"secret_id": "test-secret"})
                if fail_lookup:
                    raise RuntimeError("sensitive diagnostic test-secret")
                return {
                    "secret_id_ttl": 86400,
                    "secret_id_num_uses": uses,
                    "expiration_time": expiry.isoformat(),
                }
            self.fail("Unexpected Vault operation")

        output = io.StringIO()
        with patch.object(maintenance, "vault", side_effect=fake_vault), \
             patch.object(Path, "read_text", return_value="test-secret\n"), \
             patch("sys.argv", ["maintenance", "--role", "governance-api"]), \
             contextlib.redirect_stdout(output):
            code = maintenance.main()

        text = output.getvalue()
        self.assertNotIn("test-secret", text)
        self.assertNotIn("test-role", text)
        return code, text

    def test_valid_credentials(self):
        self.assertEqual(self.run_report()[0], 0)

    def test_low_uses(self):
        code, text = self.run_report(uses=10)
        self.assertEqual(code, 1)
        self.assertIn("Rotation: due", text)

    def test_near_expiry(self):
        self.assertEqual(self.run_report(hours=1)[0], 1)

    def test_lockout(self):
        code, text = self.run_report(locked=True)
        self.assertEqual(code, 1)
        self.assertIn("operator review required", text)

    def test_lookup_failure_is_unknown(self):
        code, text = self.run_report(fail_lookup=True)
        self.assertEqual(code, 1)
        self.assertIn("Status: UNKNOWN", text)

    def test_zero_uses_means_unlimited(self):
        code, text = self.run_report(uses=0)
        self.assertEqual(code, 0)
        self.assertIn("Uses remaining: unlimited", text)


if __name__ == "__main__":
    unittest.main()
