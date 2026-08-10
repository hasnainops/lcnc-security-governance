package lcnc.governance

default allow := false

deny contains "Confidential data cannot use an unapproved external integration." if {
	lower(object.get(input, "data_classification", "unknown")) == "confidential"
	object.get(input, "external_integration", false) == true
	object.get(input, "integration_approved", null) != true
}

deny contains "Restricted data cannot use an unapproved external integration." if {
	lower(object.get(input, "data_classification", "unknown")) == "restricted"
	object.get(input, "external_integration", false) == true
	object.get(input, "integration_approved", null) != true
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
