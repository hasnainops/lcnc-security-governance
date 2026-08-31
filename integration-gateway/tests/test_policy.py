import importlib.util
from pathlib import Path


MODULE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "policy.py"
)

spec = importlib.util.spec_from_file_location(
    "gateway_policy",
    MODULE,
)

policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def test_restricted_external_transfer_blocked():
    result = policy.evaluate_transfer(
        "https://approved.example/api",
        "approved_external",
        "confidential",
        {
            "highest_sensitivity": "restricted"
        },
    )

    assert result["allowed"] is False
    assert result["decision"] == "block"

    assert (
        "restricted_data_external_transfer"
        in result["reasons"]
    )


def test_confidential_approved_https_allowed():
    result = policy.evaluate_transfer(
        "https://approved.example/api",
        "approved_external",
        "confidential",
        {
            "highest_sensitivity": (
                "confidential"
            )
        },
    )

    assert result["allowed"] is True
    assert result["decision"] == "allow"


def test_unapproved_external_blocked():
    result = policy.evaluate_transfer(
        "https://unknown.example/api",
        "unapproved_external",
        "public",
        {
            "highest_sensitivity": None
        },
    )

    assert result["allowed"] is False

    assert (
        "destination_not_approved"
        in result["reasons"]
    )


def test_external_http_blocked():
    result = policy.evaluate_transfer(
        "http://approved.example/api",
        "approved_external",
        "internal",
        {
            "highest_sensitivity": None
        },
    )

    assert result["allowed"] is False

    assert (
        "unencrypted_external_destination"
        in result["reasons"]
    )


def test_restricted_internal_allowed():
    result = policy.evaluate_transfer(
        "http://internal-service/api",
        "internal",
        "restricted",
        {
            "highest_sensitivity": (
                "restricted"
            )
        },
    )

    assert result["allowed"] is True


def test_unknown_classification_external_blocked():
    result = policy.evaluate_transfer(
        "https://approved.example/api",
        "approved_external",
        "unknown",
        {
            "highest_sensitivity": None
        },
    )

    assert result["allowed"] is False

    assert (
        "classification_unknown_external_transfer"
        in result["reasons"]
    )
