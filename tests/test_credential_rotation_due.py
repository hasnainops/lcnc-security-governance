import contextlib
import importlib.util
import io
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

script = Path(__file__).resolve().parents[1] / "scripts/maintain-vault-credentials.py"
spec = importlib.util.spec_from_file_location("maintenance_due", script)
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


class DueTests(unittest.TestCase):
    def check(self, uses=48, hours=24, locked=False,
              failure=None, rotate_failure=False, apply=True):
        expiry = datetime.now(timezone.utc) + timedelta(hours=hours)

        def fake_vault(*args, payload=None):
            endpoint = args[2]
            if endpoint == "sys/locked-users":
                if failure == "lockout":
                    raise RuntimeError("Unavailable")
                return {"aliases": ["test-role"] if locked else []}
            if endpoint.endswith("/role-id"):
                return {"role_id": "test-role"}
            if endpoint.endswith("/secret-id/lookup"):
                if failure == "metadata":
                    raise RuntimeError("Unavailable")
                return {
                    "secret_id_ttl": 86400,
                    "secret_id_num_uses": uses,
                    "expiration_time": expiry.isoformat(),
                }
            self.fail("Unexpected Vault operation")

        module = ModuleType("vault_credential_rotation")
        module.rotate = Mock(
            side_effect=RuntimeError("Rotation failed") if rotate_failure else None
        )
        argv = ["maintenance", "--role", "governance-api"]
        if apply:
            argv.append("--rotate-due")

        with patch.object(maintenance, "vault", side_effect=fake_vault), \
             patch.object(Path, "read_text", return_value="test-secret\n"), \
             patch.object(sys, "argv", argv), \
             patch.dict(sys.modules, {"vault_credential_rotation": module}), \
             contextlib.redirect_stdout(io.StringIO()):
            code = maintenance.main()

        if module.rotate.called:
            self.assertEqual(module.rotate.call_count, 1)
            self.assertEqual(module.rotate.call_args.args[1], "governance-api")
        return code, module.rotate.call_count

    def test_not_due_skips_rotation(self):
        self.assertEqual(self.check(), (0, 0))

    def test_low_uses_rotates(self):
        self.assertEqual(self.check(uses=10), (0, 1))

    def test_near_expiry_rotates(self):
        self.assertEqual(self.check(hours=1), (0, 1))

    def test_locked_role_never_rotates(self):
        self.assertEqual(self.check(uses=4, locked=True), (1, 0))

    def test_unknown_lockout_never_rotates(self):
        self.assertEqual(self.check(uses=4, failure="lockout"), (1, 0))

    def test_unknown_metadata_never_rotates(self):
        self.assertEqual(self.check(failure="metadata"), (1, 0))

    def test_rotation_failure_requires_attention(self):
        self.assertEqual(self.check(uses=4, rotate_failure=True), (1, 1))

    def test_default_report_never_rotates_due_credentials(self):
        self.assertEqual(self.check(uses=4, apply=False), (1, 0))

    def test_unlimited_uses_do_not_trigger_rotation(self):
        self.assertEqual(self.check(uses=0), (0, 0))


if __name__ == "__main__":
    unittest.main()
