package lcnc.appsmith_publish

default allow := false

deny contains "application_facts_required" if {
    not is_object(input.application)
}

required_states := {
    "registration_status": "registered",
    "risk_status": "assessed",
    "risk_level": "low",
    "ml_anomaly_status": "assessed",
    "ml_classification_status": "assessed",
    "security_scan_status": "scanned",
}

required_booleans := {
    "ml_anomalous": false,
    "security_scan_passed": true,
}

deny contains sprintf("%s_requires_%s", [key, expected]) if {
    some key, expected in required_states
    object.get(object.get(input, "application", {}), key, null) != expected
}

deny contains sprintf("%s_requires_%v", [key, expected]) if {
    some key, expected in required_booleans
    object.get(object.get(input, "application", {}), key, null) != expected
}


deny contains "ml_classification_review_unresolved" if {
    application := object.get(input, "application", {})
    object.get(application, "ml_classification_review_required", null) != false
    object.get(input, "security_review_resolved", false) != true
}

deny contains "authoritative_classification_required" if {
    classification := object.get(object.get(input, "application", {}), "data_classification", "unknown")
    not classification in {"public", "internal", "confidential", "restricted"}
}

deny contains sprintf("%s_required", [key]) if {
    some key in {"evidence_ready", "governance_approval_current", "governance_policy_allowed", "training_complete"}
    object.get(input, key, false) != true
}

allow if count(deny) == 0
action := "allow" if allow
action := "deny" if not allow

decision := {
    "allow": allow,
    "action": action,
    "reasons": sort([reason | deny[reason]]),
    "version": "appsmith-publish-preflight-v1",
}
