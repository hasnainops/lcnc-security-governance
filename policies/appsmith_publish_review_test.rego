package lcnc.appsmith_publish_review_test

reviewed_input := {
    "application": {
        "registration_status": "registered",
        "data_classification": "internal",
        "risk_status": "assessed",
        "risk_level": "low",
        "ml_anomaly_status": "assessed",
        "ml_anomalous": false,
        "ml_classification_status": "assessed",
        "ml_classification_review_required": true,
        "security_scan_status": "scanned",
        "security_scan_passed": true,
    },
    "evidence_ready": true,
    "governance_approval_current": true,
    "governance_policy_allowed": true,
    "training_complete": true,
    "security_review_resolved": true,
}

test_reviewed_classification_allowed if {
    result := data.lcnc.appsmith_publish.decision
        with input as reviewed_input
    result.allow == true
    count(result.reasons) == 0
}

test_unresolved_review_denied if {
    facts := object.union(reviewed_input, {
        "security_review_resolved": false,
    })
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
    "ml_classification_review_unresolved" in result.reasons
}

test_stale_approval_denied if {
    facts := object.union(reviewed_input, {
        "governance_approval_current": false,
    })
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
}

test_hard_policy_denial_not_overridden if {
    facts := object.union(reviewed_input, {
        "governance_policy_allowed": false,
    })
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
}

test_incomplete_training_denied if {
    facts := object.union(reviewed_input, {
        "training_complete": false,
    })
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
}

test_failed_security_scan_denied if {
    app := object.union(reviewed_input.application, {
        "security_scan_passed": false,
    })
    facts := object.union(reviewed_input, {"application": app})
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
}

test_ml_anomaly_not_overridden if {
    app := object.union(reviewed_input.application, {
        "ml_anomalous": true,
    })
    facts := object.union(reviewed_input, {"application": app})
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
}

test_missing_evidence_denied if {
    facts := object.union(reviewed_input, {
        "evidence_ready": false,
    })
    result := data.lcnc.appsmith_publish.decision
        with input as facts
    result.allow == false
}
