import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCANNER_PATH = (
    ROOT
    / "security-scanner"
    / "app"
    / "scanner.py"
)

spec = importlib.util.spec_from_file_location(
    "workflow_security_scanner_module",
    SCANNER_PATH,
)

scanner_module = (
    importlib.util.module_from_spec(spec)
)

spec.loader.exec_module(scanner_module)

scan_application = (
    scanner_module.scan_application
)


def base_payload():
    return {
        "registration_status": "registered",
        "owner_known": True,
        "data_classification": "internal",
        "internet_exposed": False,
        "external_integration_count": 0,
        "unapproved_integration_count": 0,
        "credential_type": None,
        "connector_metadata": "HTTPS integration",
    }


def test_workflow_http_actions_are_detected():
    payload = base_payload()

    payload["workflow_security_metadata"] = {
        "page_count": 1,
        "widget_count": 23,
        "action_count": 9,
        "api_action_count": 9,
        "dynamic_binding_count": 8,
        "invalid_action_count": 0,
        "http_action_count": 7,
        "https_action_count": 0,
        "sensitive_header_action_count": 0,
    }

    result = scan_application(payload)

    rule_ids = {
        item["rule_id"]
        for item in result["findings"]
    }

    assert "SEC-009" in rule_ids
    assert result["passed"] is False


def test_invalid_workflow_actions_are_detected():
    payload = base_payload()

    payload["workflow_security_metadata"] = {
        "page_count": 1,
        "widget_count": 5,
        "action_count": 2,
        "api_action_count": 2,
        "dynamic_binding_count": 1,
        "invalid_action_count": 1,
        "http_action_count": 0,
        "https_action_count": 2,
        "sensitive_header_action_count": 0,
    }

    result = scan_application(payload)

    rule_ids = {
        item["rule_id"]
        for item in result["findings"]
    }

    assert "SEC-010" in rule_ids


def test_sensitive_header_usage_is_detected_without_values():
    payload = base_payload()

    payload["workflow_security_metadata"] = {
        "page_count": 1,
        "widget_count": 5,
        "action_count": 1,
        "api_action_count": 1,
        "dynamic_binding_count": 0,
        "invalid_action_count": 0,
        "http_action_count": 0,
        "https_action_count": 1,
        "sensitive_header_action_count": 1,
    }

    result = scan_application(payload)

    rule_ids = {
        item["rule_id"]
        for item in result["findings"]
    }

    assert "SEC-011" in rule_ids


def test_workflow_findings_do_not_require_integration_counts():
    result = scan_application(
        {
            "registration_status": "registered",
            "owner_known": True,
            "data_classification": "internal",
            "internet_exposed": False,
            "external_integration_count": None,
            "unapproved_integration_count": None,
            "credential_type": None,
            "connector_metadata": None,
            "workflow_security_metadata": {
                "page_count": 1,
                "widget_count": 23,
                "action_count": 9,
                "api_action_count": 9,
                "dynamic_binding_count": 8,
                "invalid_action_count": 0,
                "http_action_count": 7,
                "https_action_count": 0,
                "sensitive_header_action_count": 0,
            },
        }
    )

    rule_ids = {
        item["rule_id"]
        for item in result["findings"]
    }

    assert "SEC-009" in rule_ids
    assert "SEC-004" not in rule_ids
    assert "SEC-008" not in rule_ids

    sec_009 = next(
        item
        for item in result["findings"]
        if item["rule_id"] == "SEC-009"
    )

    assert sec_009["severity"] == "high"
    assert sec_009["evidence"] == (
        "http_action_count=7"
    )
