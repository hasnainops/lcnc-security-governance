import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import unittest
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / "governance-automation/app/reviewer_identity.py"
spec = importlib.util.spec_from_file_location("reviewer_identity", source)
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
entity = "b800f336-5105-4fc2-bd64-44418d568ab1"


cases = [
    (None, [], entity, None, False),
    ("Bearer sample", ["default"], entity, None, False),
    ("Bearer sample", ["lcnc-security-reviewer"], "", None, False),
    ("Bearer sample", ["lcnc-security-reviewer"], entity, "another-user", False),
    ("Bearer sample", ["lcnc-security-reviewer"], entity, None, True),
    ("Bearer sample", ["lcnc-security-reviewer"], entity, "vault:" + entity, True),
]
class ReviewerTests(unittest.TestCase):
    def test_reviewer_cases(self):
        for header, policies, entity_id, assignee, allowed in cases:
            with self.subTest(header=header, policies=policies, entity=entity_id, assignee=assignee):
                client = Mock()
                data = {"data": {"entity_id": entity_id, "policies": policies}}
                client.open.return_value = io.BytesIO(json.dumps(data).encode())
                with patch.object(identity, "build_opener", return_value=client):
                    if allowed:
                        self.assertEqual(identity.verified_reviewer(header, assignee), "vault:" + entity)
                    else:
                        with self.assertRaises(identity.ReviewerAccessError):
                            identity.verified_reviewer(header, assignee)


if __name__ == "__main__":
    unittest.main()
