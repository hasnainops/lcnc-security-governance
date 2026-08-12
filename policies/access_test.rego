package lcnc.access_test

import data.lcnc.access.decision


test_viewer_can_read_registered_internal_app if {
    result := decision with input as {
        "role": "viewer",
        "action": "read",
        "registration_status": "registered",
        "data_classification": "internal"
    }

    result.allow == true
    result.action == "allow"
}


test_viewer_cannot_export_confidential_data if {
    result := decision with input as {
        "role": "viewer",
        "action": "export",
        "registration_status": "registered",
        "data_classification": "confidential"
    }

    result.allow == false
    result.action == "deny"
}


test_developer_can_modify_registered_internal_app if {
    result := decision with input as {
        "role": "developer",
        "action": "modify",
        "registration_status": "registered",
        "data_classification": "internal"
    }

    result.allow == true
}


test_developer_cannot_modify_restricted_app if {
    result := decision with input as {
        "role": "developer",
        "action": "modify",
        "registration_status": "registered",
        "data_classification": "restricted"
    }

    result.allow == false
}


test_security_admin_can_review_restricted_app if {
    result := decision with input as {
        "role": "security_admin",
        "action": "review",
        "registration_status": "registered",
        "data_classification": "restricted"
    }

    result.allow == true
}


test_unregistered_app_blocks_privileged_action if {
    result := decision with input as {
        "role": "security_admin",
        "action": "approve",
        "registration_status": "unregistered",
        "data_classification": "confidential"
    }

    result.allow == false

    "Privileged actions require a registered application." in result.reasons
}


test_developer_cannot_export_restricted_app if {
    result := decision with input as {
        "role": "developer",
        "action": "export",
        "registration_status": "registered",
        "data_classification": "restricted"
    }

    result.allow == false
}
