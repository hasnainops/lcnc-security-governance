package lcnc.access

default allow := false

role := lower(object.get(input, "role", "unknown"))
requested_action := lower(object.get(input, "action", "unknown"))
classification := lower(object.get(input, "data_classification", "unknown"))
registration := lower(object.get(input, "registration_status", "unknown"))


privileged_action if {
    requested_action == "modify"
}

privileged_action if {
    requested_action == "export"
}

privileged_action if {
    requested_action == "approve"
}


role_permits if {
    role == "viewer"
    requested_action == "read"
}

role_permits if {
    role == "developer"
    requested_action == "read"
}

role_permits if {
    role == "developer"
    requested_action == "modify"
}

role_permits if {
    role == "developer"
    requested_action == "export"
}

role_permits if {
    role == "security_admin"
    requested_action == "read"
}

role_permits if {
    role == "security_admin"
    requested_action == "review"
}

role_permits if {
    role == "security_admin"
    requested_action == "modify"
}

role_permits if {
    role == "security_admin"
    requested_action == "approve"
}

role_permits if {
    role == "security_admin"
    requested_action == "export"
}


deny contains "Role is not permitted to perform this action." if {
    not role_permits
}

deny contains "Privileged actions require a registered application." if {
    registration != "registered"
    privileged_action
}

deny contains "Developers cannot modify restricted applications." if {
    role == "developer"
    requested_action == "modify"
    classification == "restricted"
}

deny contains "Developers cannot export restricted applications." if {
    role == "developer"
    requested_action == "export"
    classification == "restricted"
}


allow if {
    role_permits
    count(deny) == 0
}


decision_action := "allow" if {
    allow
}

decision_action := "deny" if {
    not allow
}


decision := {
    "allow": allow,
    "action": decision_action,
    "reasons": sort([reason | deny[reason]]),
    "role": role,
    "requested_action": requested_action,
}
