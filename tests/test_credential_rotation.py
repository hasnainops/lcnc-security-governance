import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / "scripts/vault_credential_rotation.py"
spec = importlib.util.spec_from_file_location("rotation", script)
rotation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotation)


class RotationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        directory = self.root / ".runtime-secrets"
        directory.mkdir()
        self.path = directory / "governance-api-secret-id"
        self.path.write_text("old-test-secret\n")
        self.calls = []
        self.locked = False
        self.failure = None
        self.output = io.StringIO()

    def vault(self, *args, payload=None):
        endpoint = args[-1] if args[-1] != "-" else args[-2]
        if endpoint.endswith("/role-id"):
            return {"role_id": "test-role"}
        if endpoint == "sys/locked-users":
            if self.failure == "lockout-read":
                raise RuntimeError("Unavailable")
            return {"locked": self.locked}
        if endpoint.endswith("/secret-id/lookup"):
            if self.failure == "lookup":
                raise RuntimeError("Unavailable")
            return {"secret_id_num_uses": 20}
        if endpoint.endswith("/secret-id"):
            if self.failure == "issue":
                raise RuntimeError("Issuance failed")
            return {"secret_id": "new-test-secret"}
        self.fail("Unexpected Vault operation")

    def compose(self, root, *args, payload=None):
        self.calls.append(args)
        if args[0] == "exec" and self.failure == "probe":
            raise RuntimeError("Probe failed")

    def run_rotation(self):
        running = SimpleNamespace(
            returncode=0,
            stdout="governance-api-a\ngovernance-api-b\n",
        )
        with patch.object(rotation, "compose", side_effect=self.compose), \
             patch.object(rotation.subprocess, "run", return_value=running), \
             contextlib.redirect_stdout(self.output):
            rotation.rotate(
                self.root, "governance-api", self.vault,
                lambda value, target: value["locked"],
            )

    def test_success_preserves_inode_and_checks_both_replicas(self):
        inode = self.path.stat().st_ino
        self.run_rotation()
        self.assertEqual(self.path.stat().st_ino, inode)
        self.assertEqual(self.path.read_text(), "new-test-secret\n")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            [call[0] for call in self.calls],
            ["stop", "start", "exec", "exec"],
        )
        self.assertEqual(self.calls[2][2], "governance-api-a")
        self.assertEqual(self.calls[3][2], "governance-api-b")
        self.assertNotIn("new-test-secret", self.output.getvalue())
        self.assertNotIn("old-test-secret", self.output.getvalue())

    def test_locked_role_refused_before_stopping(self):
        self.locked = True
        with self.assertRaises(RuntimeError):
            self.run_rotation()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.path.read_text(), "old-test-secret\n")

    def test_unknown_lockout_state_refused(self):
        self.failure = "lockout-read"
        with self.assertRaises(RuntimeError):
            self.run_rotation()
        self.assertEqual(self.calls, [])

    def test_missing_metadata_refused(self):
        self.failure = "lookup"
        with self.assertRaises(RuntimeError):
            self.run_rotation()
        self.assertEqual(self.calls, [])

    def test_issuance_failure_restarts_with_original_file(self):
        self.failure = "issue"
        with self.assertRaises(RuntimeError):
            self.run_rotation()
        self.assertEqual([call[0] for call in self.calls], ["stop", "start"])
        self.assertEqual(self.path.read_text(), "old-test-secret\n")

    def test_probe_failure_does_not_claim_success(self):
        self.failure = "probe"
        with self.assertRaises(RuntimeError):
            self.run_rotation()
        self.assertEqual(self.path.read_text(), "new-test-secret\n")
        self.assertNotIn("Rotation verified.", self.output.getvalue())

    def test_write_failure_leaves_workloads_stopped(self):
        original_open = Path.open

        def controlled_open(path, *args, **kwargs):
            if path == self.path and args and args[0] == "r+":
                raise OSError("Simulated write failure")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", controlled_open):
            with self.assertRaises(OSError):
                self.run_rotation()
        self.assertEqual([call[0] for call in self.calls], ["stop"])
        self.assertNotIn("Rotation verified.", self.output.getvalue())



class RestartHelperTests(unittest.TestCase):
    def test_starts_only_selected_container_ids(self):
        responses = [
            SimpleNamespace(returncode=0, stdout="container-a\n"),
            SimpleNamespace(returncode=0, stdout="container-b\n"),
            SimpleNamespace(returncode=0, stdout=""),
        ]
        with patch.object(rotation.subprocess, "run", side_effect=responses) as run:
            rotation.compose(
                Path("/project"), "start",
                "governance-api-a", "governance-api-b",
            )
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands, [
            ["docker", "compose", "ps", "--all", "--quiet", "governance-api-a"],
            ["docker", "compose", "ps", "--all", "--quiet", "governance-api-b"],
            ["docker", "start", "container-a", "container-b"],
        ])

    def test_invalid_lookup_never_starts_containers(self):
        for code, output in ((0, ""), (0, "id-a\nid-b\n"), (1, "")):
            with self.subTest(code=code, output=output):
                response = SimpleNamespace(returncode=code, stdout=output)
                with patch.object(rotation.subprocess, "run", return_value=response) as run:
                    with self.assertRaises(RuntimeError):
                        rotation.compose(Path("/project"), "start", "enterprise-discovery")
                self.assertEqual(run.call_count, 1)

    def test_start_failure_is_reported_without_raw_output(self):
        responses = [
            SimpleNamespace(returncode=0, stdout="container-a\n"),
            SimpleNamespace(returncode=1, stdout="sensitive-output"),
        ]
        with patch.object(rotation.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "start failed with exit code 1") as error:
                rotation.compose(Path("/project"), "start", "enterprise-discovery")
        self.assertNotIn("sensitive-output", str(error.exception))


if __name__ == "__main__":
    unittest.main()
