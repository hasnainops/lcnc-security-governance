"""LO4.1: Fail-closed validation of DLP inspection evidence."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from app import main as gateway


class MockDLPResponse:
    def __init__(self, document):
        self.document = document

    def raise_for_status(self):
        return None

    def json(self):
        if isinstance(self.document, Exception):
            raise self.document
        return deepcopy(self.document)


def clean_result():
    return {
        "engine_version": "dlp-v1",
        "sensitive_data_detected": False,
        "finding_count": 0,
        "highest_sensitivity": None,
        "detected_types": [],
        "findings": [],
    }


def restricted_result():
    result = clean_result()

    result.update(
        {
            "sensitive_data_detected": True,
            "finding_count": 1,
            "highest_sensitivity": "restricted",
            "detected_types": [
                "restricted_field_schema"
            ],
            "findings": [
                {
                    "rule_id": "DLP-005",
                    "data_type": "restricted_field_schema",
                    "sensitivity": "restricted",
                    "count": 1,
                    "evidence": (
                        "Restricted schema field detected"
                    ),
                }
            ],
        }
    )

    return result


def evaluate(document, classification="public"):
    payload = gateway.TransferRequest(
        application_id="lo4-dlp-contract-fixture",
        application_name="Isolated DLP Contract Test",
        destination_url="https://approved.example.invalid/ingest",
        destination_trust="approved_external",
        declared_classification=classification,
        content="Synthetic test content",
        field_names=[],
    )

    with (
        patch.object(
            gateway.httpx,
            "post",
            return_value=MockDLPResponse(document),
        ) as mock_post,
        patch.object(
            gateway,
            "rate_limit_exceeded",
            return_value=False,
        ),
    ):
        try:
            result = gateway.evaluate(payload)
        finally:
            mock_post.assert_called_once()

    return result


def test_valid_clean_response_allows_public_transfer():
    result = evaluate(clean_result())

    assert result["decision"] == "allow"
    assert result["allowed"] is True


def test_valid_restricted_detection_blocks_external_transfer():
    result = evaluate(restricted_result())

    assert result["decision"] == "block"
    assert result["allowed"] is False
    assert result["effective_sensitivity"] == "restricted"


def test_unknown_authoritative_classification_blocks():
    result = evaluate(
        clean_result(),
        classification="unknown",
    )

    assert result["decision"] == "block"
    assert result["allowed"] is False


@pytest.mark.parametrize(
    "document",
    [
        pytest.param(
            {
                **restricted_result(),
                "highest_sensitivity": None,
            },
            id="sensitive-without-sensitivity",
        ),
        pytest.param(
            {
                **restricted_result(),
                "highest_sensitivity": "invalid",
            },
            id="unsupported-sensitivity",
        ),
        pytest.param(
            {
                **restricted_result(),
                "sensitive_data_detected": False,
            },
            id="false-negative-detection-flag",
        ),
        pytest.param(
            {
                **restricted_result(),
                "finding_count": 0,
            },
            id="incorrect-finding-count",
        ),
        pytest.param(
            {
                **restricted_result(),
                "detected_types": [],
            },
            id="missing-detected-types",
        ),
        pytest.param(
            {
                **restricted_result(),
                "findings": [],
            },
            id="missing-finding-evidence",
        ),
        pytest.param(
            {
                **restricted_result(),
                "findings": None,
            },
            id="invalid-finding-evidence",
        ),
        pytest.param(
            {
                **restricted_result(),
                "engine_version": None,
            },
            id="missing-engine-version",
        ),
        pytest.param(
            {
                **restricted_result(),
                "finding_count": True,
            },
            id="boolean-finding-count",
        ),
        pytest.param(
            {
                **restricted_result(),
                "findings": [
                    {
                        **restricted_result()["findings"][0],
                        "count": -1,
                    }
                ],
            },
            id="negative-occurrence-count",
        ),
        pytest.param(
            clean_result() | {
                "highest_sensitivity": "invalid"
            },
            id="invalid-clean-sensitivity",
        ),
        pytest.param(
            {"engine_version": "dlp-v1"},
            id="incomplete-dlp-response",
        ),
        pytest.param(
            [],
            id="non-object-dlp-response",
        ),
        pytest.param(
            ValueError("Malformed JSON"),
            id="unparseable-dlp-json",
        ),
    ],
)
def test_invalid_dlp_evidence_fails_closed(document):
    with pytest.raises(HTTPException) as error:
        evaluate(document)

    assert error.value.status_code == 502
    assert error.value.detail == {
        "decision": "block",
        "reason": "dlp_invalid_response",
    }
