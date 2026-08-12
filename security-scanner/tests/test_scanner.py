from security_scanner_test_loader import scanner


def test_risky_citizen_app_has_findings():
    payload = {
        "registration_status": "unregistered",
        "owner_known": False,
        "data_classification": "confidential",
        "internet_exposed": False,
        "external_integration_count": 3,
        "unapproved_integration_count": 1,
        "credential_type": "api_key",
        "connector_metadata": (
            "http://external.example "
            "api_key=ABCDEF1234567890"
        ),
    }

    result = scanner.scan_application(
        payload
    )

    rule_ids = {
        item["rule_id"]
        for item in result["findings"]
    }

    assert result["passed"] is False
    assert "SEC-001" in rule_ids
    assert "SEC-004" in rule_ids
    assert "SEC-005" in rule_ids
    assert "SEC-006" in rule_ids
    assert "SEC-007" in rule_ids
    assert "SEC-008" in rule_ids


def test_governed_internal_app_passes():
    payload = {
        "registration_status": "registered",
        "owner_known": True,
        "data_classification": "internal",
        "internet_exposed": False,
        "external_integration_count": 0,
        "unapproved_integration_count": 0,
        "credential_type": None,
        "connector_metadata": (
            "internal database"
        ),
    }

    result = scanner.scan_application(
        payload
    )

    assert result["passed"] is True
    assert result["finding_count"] == 0
    assert result["findings"] == []
