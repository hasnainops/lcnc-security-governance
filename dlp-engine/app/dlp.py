import re


EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
)

SSN_PATTERN = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)

CARD_CANDIDATE_PATTERN = re.compile(
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"
)

RESTRICTED_FIELD_NAMES = {
    "ssn",
    "social_security_number",
    "card_number",
    "credit_card",
    "cvv",
    "bank_account",
    "bank_account_number",
    "routing_number",
}

CONFIDENTIAL_FIELD_NAMES = {
    "email",
    "email_address",
    "phone",
    "phone_number",
    "billing_address",
    "home_address",
}


def luhn_valid(value):
    digits = [
        int(char)
        for char in value
        if char.isdigit()
    ]

    if not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    parity = len(digits) % 2

    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2

            if digit > 9:
                digit -= 9

        checksum += digit

    return checksum % 10 == 0


def finding(
    rule_id,
    data_type,
    sensitivity,
    count,
    evidence,
):
    return {
        "rule_id": rule_id,
        "data_type": data_type,
        "sensitivity": sensitivity,
        "count": count,
        "evidence": evidence,
    }


def inspect_content(content, field_names=None):
    content = content or ""
    field_names = field_names or []

    findings = []

    email_matches = EMAIL_PATTERN.findall(content)

    if email_matches:
        findings.append(
            finding(
                "DLP-001",
                "email_address",
                "confidential",
                len(email_matches),
                (
                    f"{len(email_matches)} "
                    "email-like value(s) detected"
                ),
            )
        )

    ssn_matches = SSN_PATTERN.findall(content)

    if ssn_matches:
        findings.append(
            finding(
                "DLP-002",
                "social_security_number",
                "restricted",
                len(ssn_matches),
                (
                    f"{len(ssn_matches)} "
                    "SSN-like value(s) detected"
                ),
            )
        )

    valid_cards = [
        candidate
        for candidate
        in CARD_CANDIDATE_PATTERN.findall(content)
        if luhn_valid(candidate)
    ]

    if valid_cards:
        findings.append(
            finding(
                "DLP-003",
                "payment_card",
                "restricted",
                len(valid_cards),
                (
                    f"{len(valid_cards)} "
                    "Luhn-valid payment card "
                    "value(s) detected"
                ),
            )
        )

    phone_matches = [
        value
        for value in PHONE_PATTERN.findall(content)
        if 8 <= len(
            [
                char
                for char in value
                if char.isdigit()
            ]
        ) <= 15
    ]

    if phone_matches:
        findings.append(
            finding(
                "DLP-004",
                "phone_number",
                "confidential",
                len(phone_matches),
                (
                    f"{len(phone_matches)} "
                    "phone-like value(s) detected"
                ),
            )
        )

    normalized_fields = {
        str(field).strip().lower()
        for field in field_names
        if str(field).strip()
    }

    restricted_fields = sorted(
        normalized_fields
        & RESTRICTED_FIELD_NAMES
    )

    if restricted_fields:
        findings.append(
            finding(
                "DLP-005",
                "restricted_field_schema",
                "restricted",
                len(restricted_fields),
                (
                    "Restricted field name(s) "
                    "present in schema: "
                    + ", ".join(restricted_fields)
                ),
            )
        )

    confidential_fields = sorted(
        normalized_fields
        & CONFIDENTIAL_FIELD_NAMES
    )

    if confidential_fields:
        findings.append(
            finding(
                "DLP-006",
                "confidential_field_schema",
                "confidential",
                len(confidential_fields),
                (
                    "Confidential field name(s) "
                    "present in schema: "
                    + ", ".join(confidential_fields)
                ),
            )
        )

    sensitivity_rank = {
        "public": 0,
        "internal": 1,
        "confidential": 2,
        "restricted": 3,
    }

    highest_sensitivity = None

    if findings:
        highest_sensitivity = max(
            (
                item["sensitivity"]
                for item in findings
            ),
            key=lambda value: (
                sensitivity_rank[value]
            ),
        )

    return {
        "engine_version": "dlp-v1",
        "sensitive_data_detected": bool(findings),
        "finding_count": len(findings),
        "highest_sensitivity": highest_sensitivity,
        "detected_types": sorted(
            {
                item["data_type"]
                for item in findings
            }
        ),
        "findings": findings,
    }
