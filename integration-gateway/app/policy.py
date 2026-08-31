SENSITIVITY_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


def effective_sensitivity(
    declared_classification,
    detected_sensitivity,
):
    declared = (
        declared_classification
        if declared_classification
        in SENSITIVITY_RANK
        else "public"
    )

    detected = (
        detected_sensitivity
        if detected_sensitivity
        in SENSITIVITY_RANK
        else "public"
    )

    return max(
        (declared, detected),
        key=lambda value: SENSITIVITY_RANK[value],
    )


def evaluate_transfer(
    destination_url,
    destination_trust,
    declared_classification,
    dlp_result,
):
    reasons = []

    external = destination_trust != "internal"

    effective = effective_sensitivity(
        declared_classification,
        dlp_result.get("highest_sensitivity"),
    )

    if (
        external
        and declared_classification == "unknown"
    ):
        reasons.append(
            "classification_unknown_external_transfer"
        )

    if destination_trust == "unapproved_external":
        reasons.append(
            "destination_not_approved"
        )

    if (
        external
        and destination_url.lower().startswith(
            "http://"
        )
    ):
        reasons.append(
            "unencrypted_external_destination"
        )

    if (
        external
        and effective == "restricted"
    ):
        reasons.append(
            "restricted_data_external_transfer"
        )

    if reasons:
        return {
            "decision": "block",
            "allowed": False,
            "effective_sensitivity": effective,
            "reasons": reasons,
        }

    return {
        "decision": "allow",
        "allowed": True,
        "effective_sensitivity": effective,
        "reasons": [
            "policy_requirements_satisfied"
        ],
    }
