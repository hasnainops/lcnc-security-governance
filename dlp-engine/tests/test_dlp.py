import importlib.util
from pathlib import Path


MODULE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "dlp.py"
)

spec = importlib.util.spec_from_file_location(
    "dlp_module",
    MODULE,
)

dlp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dlp)


def test_sensitive_customer_export():
    result = dlp.inspect_content(
        (
            "Customer email alice@example.com "
            "phone +1 202 555 0123 "
            "card 4111 1111 1111 1111"
        ),
        [
            "customer_id",
            "email",
            "phone",
            "card_number",
        ],
    )

    types = set(result["detected_types"])

    assert result[
        "sensitive_data_detected"
    ] is True

    assert result[
        "highest_sensitivity"
    ] == "restricted"

    assert "email_address" in types
    assert "payment_card" in types
    assert "restricted_field_schema" in types


def test_non_sensitive_payload():
    result = dlp.inspect_content(
        "Quarterly product announcement",
        [
            "title",
            "description",
        ],
    )

    assert result[
        "sensitive_data_detected"
    ] is False

    assert result["finding_count"] == 0
    assert result[
        "highest_sensitivity"
    ] is None


def test_raw_sensitive_value_not_in_evidence():
    email = "secret.person@example.com"

    result = dlp.inspect_content(
        email,
        [],
    )

    serialized = str(
        result["findings"]
    )

    assert email not in serialized
