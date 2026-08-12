from ml_analytics_test_loader import analyzer


def test_risky_profile_is_anomalous():
    payload = {
        "owner_known": 0,
        "business_purpose_known": 1,
        "internet_exposed": 0,
        "external_integration_count": 3,
        "unapproved_integration_count": 1,
        "uses_api_key": 1,
        "connector_count": 5,
        "external_domain_count": 2,
        "changes_last_24h": 4,
    }

    result = analyzer.analyze_application(
        payload
    )

    assert result["anomalous"] is True
    assert result["raw_decision_score"] < 0
    assert (
        result["model_version"]
        == "isolation-forest-v1"
    )


def test_governed_profile_is_not_anomalous():
    payload = {
        "owner_known": 1,
        "business_purpose_known": 1,
        "internet_exposed": 0,
        "external_integration_count": 0,
        "unapproved_integration_count": 0,
        "uses_api_key": 0,
        "connector_count": 2,
        "external_domain_count": 0,
        "changes_last_24h": 0,
    }

    result = analyzer.analyze_application(
        payload
    )

    assert result["anomalous"] is False
