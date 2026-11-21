package lcnc.appsmith_publish_test

good := {
    "application": {
        "registration_status": "registered", "data_classification": "internal",
        "risk_status": "assessed", "risk_level": "low", "ml_anomaly_status": "assessed",
        "ml_anomalous": false, "ml_classification_status": "assessed",
        "ml_classification_review_required": false,
        "security_scan_status": "scanned", "security_scan_passed": true,
    },
    "evidence_ready": true, "governance_approval_current": true,
    "governance_policy_allowed": true, "training_complete": true,
}

with_application(app) := object.union(object.remove(good, ["application"]), {"application": app})

test_approved_current_clean_application_allowed if {
    result := data.lcnc.appsmith_publish.decision with input as good
    result.allow == true
    result.action == "allow"
    result.reasons == []
}

test_each_failed_precondition_denies if {
    every key in {"evidence_ready", "governance_approval_current", "governance_policy_allowed", "training_complete"} {
        changed := object.union(good, {key: false})
        result := data.lcnc.appsmith_publish.decision with input as changed
        result.allow == false
    }
}

test_missing_or_wrong_application_fields_deny if {
    every key, _ in good.application {
        incomplete := object.remove(good.application, [key])
        result := data.lcnc.appsmith_publish.decision with input as with_application(incomplete)
        result.allow == false
        wrong := object.union(good.application, {key: "unknown"})
        rejected := data.lcnc.appsmith_publish.decision with input as with_application(wrong)
        rejected.allow == false
    }
}

test_unknown_or_null_application_denied if {
    every shape in [null, [], "registered", 1] {
        result := data.lcnc.appsmith_publish.decision with input as with_application(shape)
        result.allow == false
    }
}

test_empty_input_denied if {
    result := data.lcnc.appsmith_publish.decision with input as {}
    result.allow == false
    count(result.reasons) > 0
}

test_lo1_probe_still_requires_review if {
    probe := object.union(good.application, {
        "registration_status": "unregistered", "data_classification": "unknown",
        "risk_level": "high", "ml_anomalous": true,
        "ml_classification_review_required": true, "security_scan_passed": false,
    })
    result := data.lcnc.appsmith_publish.decision with input as with_application(probe)
    result.allow == false
    "authoritative_classification_required" in result.reasons
}
