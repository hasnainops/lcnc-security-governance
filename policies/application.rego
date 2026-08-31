package lcnc.governance

default allow := false


external_integration_present if {
    object.get(input, "external_integration_count", null) != null
    object.get(input, "external_integration_count", 0) > 0
}

external_integration_present if {
    object.get(input, "external_integration_count", null) == null
    object.get(input, "external_integration", false) == true
}


unapproved_integration_present if {
    object.get(input, "unapproved_integration_count", null) != null
    object.get(input, "unapproved_integration_count", 0) > 0
}

unapproved_integration_present if {
    object.get(input, "unapproved_integration_count", null) == null
    external_integration_present
    object.get(input, "integration_approved", null) != true
}


deny contains "Confidential data cannot use an unapproved external integration." if {
    lower(object.get(input, "data_classification", "unknown")) == "confidential"
    unapproved_integration_present
}

deny contains "Restricted data cannot use an unapproved external integration." if {
    lower(object.get(input, "data_classification", "unknown")) == "restricted"
    unapproved_integration_present
}


allow if {
    count(deny) == 0
}


action := "allow" if {
    allow
}

action := "deny" if {
    not allow
}


decision := {
    "allow": allow,
    "action": action,
    "reasons": sort([reason | deny[reason]]),
}
