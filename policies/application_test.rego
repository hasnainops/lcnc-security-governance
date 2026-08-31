package lcnc.governance_test

import data.lcnc.governance.decision


test_confidential_unapproved_external_is_denied if {
    result := decision with input as {
        "data_classification": "confidential",
        "external_integration": true,
        "integration_approved": false
    }

    result.allow == false
    result.action == "deny"
    count(result.reasons) == 1
}


test_restricted_unapproved_external_is_denied if {
    result := decision with input as {
        "data_classification": "restricted",
        "external_integration": true,
        "integration_approved": false
    }

    result.allow == false
    result.action == "deny"
}


test_internal_application_without_external_integration_is_allowed if {
    result := decision with input as {
        "data_classification": "internal",
        "external_integration": false,
        "integration_approved": null
    }

    result.allow == true
    result.action == "allow"
    count(result.reasons) == 0
}




test_count_telemetry_overrides_legacy_safe_booleans if {
    result := decision with input as {
        "data_classification": "confidential",
        "external_integration": false,
        "integration_approved": true,
        "external_integration_count": 3,
        "unapproved_integration_count": 1
    }

    result.allow == false
    result.action == "deny"
    count(result.reasons) == 1
}


test_zero_counts_override_legacy_risky_booleans if {
    result := decision with input as {
        "data_classification": "confidential",
        "external_integration": true,
        "integration_approved": false,
        "external_integration_count": 0,
        "unapproved_integration_count": 0
    }

    result.allow == true
    result.action == "allow"
    count(result.reasons) == 0
}
