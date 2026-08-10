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
