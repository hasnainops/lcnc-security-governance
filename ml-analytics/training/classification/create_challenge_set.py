from pathlib import Path

import pandas as pd


ROWS = [
    # PUBLIC
    {
        "application_name": "City Event Bulletin",
        "business_purpose": "Publish approved community schedules for external visitors",
        "data_fields": "event_title venue public_map_link organizer",
        "connector_metadata": "public calendar website",
        "expected_classification": "public",
    },
    {
        "application_name": "Product Feature Showcase",
        "business_purpose": "Present approved product information without customer records",
        "data_fields": "product_title feature_summary documentation_url",
        "connector_metadata": "marketing site documentation feed",
        "expected_classification": "public",
    },
    {
        "application_name": "Media Announcement Hub",
        "business_purpose": "Distribute approved company announcements to external audiences",
        "data_fields": "article_title spokesperson release_date media_url",
        "connector_metadata": "corporate website feed",
        "expected_classification": "public",
    },
    {
        "application_name": "Open Training Catalog",
        "business_purpose": "List learning courses available to external visitors",
        "data_fields": "course_title summary enrollment_link",
        "connector_metadata": "public learning portal",
        "expected_classification": "public",
    },
    {
        "application_name": "Supplier Expo Page",
        "business_purpose": "Publish approved exhibition information for public viewing",
        "data_fields": "supplier_name booth_number public_description",
        "connector_metadata": "external event website",
        "expected_classification": "public",
    },

    # INTERNAL
    {
        "application_name": "Shift Handover Board",
        "business_purpose": "Coordinate operational handovers between employee teams",
        "data_fields": "staff_name shift location handover_notes",
        "connector_metadata": "workforce system",
        "expected_classification": "internal",
    },
    {
        "application_name": "Procurement Request Tracker",
        "business_purpose": "Manage employee purchase requests and approvals",
        "data_fields": "requester department item approval_state",
        "connector_metadata": "procurement API",
        "expected_classification": "internal",
    },
    {
        "application_name": "Engineering Sprint Planner",
        "business_purpose": "Coordinate internal engineering work and task status",
        "data_fields": "assignee sprint ticket status",
        "connector_metadata": "internal issue tracker",
        "expected_classification": "internal",
    },
    {
        "application_name": "Facilities Maintenance Queue",
        "business_purpose": "Route workplace maintenance requests between internal teams",
        "data_fields": "employee_name office_area request_notes",
        "connector_metadata": "facilities management system",
        "expected_classification": "internal",
    },
    {
        "application_name": "Budget Planning Worksheet",
        "business_purpose": "Prepare departmental forecasts for internal planning",
        "data_fields": "department cost_center forecast_notes",
        "connector_metadata": "finance planning database",
        "expected_classification": "internal",
    },

    # CONFIDENTIAL
    {
        "application_name": "Client Renewal Workspace",
        "business_purpose": "Manage client contacts and account renewal activity",
        "data_fields": "client_name contact_email phone contract_id",
        "connector_metadata": "CRM account API",
        "expected_classification": "confidential",
    },
    {
        "application_name": "Support Escalation Console",
        "business_purpose": "Investigate customer service cases and associated contact records",
        "data_fields": "customer_id email case_notes address",
        "connector_metadata": "customer support database",
        "expected_classification": "confidential",
    },
    {
        "application_name": "Delivery Exception Manager",
        "business_purpose": "Resolve delivery issues using recipient contact information",
        "data_fields": "recipient_name phone street_address tracking_id",
        "connector_metadata": "logistics customer API",
        "expected_classification": "confidential",
    },
    {
        "application_name": "Customer Feedback Casebook",
        "business_purpose": "Analyze customer complaints linked to customer accounts",
        "data_fields": "customer_email customer_id complaint_notes",
        "connector_metadata": "CRM service",
        "expected_classification": "confidential",
    },
    {
        "application_name": "Subscriber Service Tool",
        "business_purpose": "Administer subscriber accounts and contact information",
        "data_fields": "subscriber_id email mobile account_status",
        "connector_metadata": "subscription database",
        "expected_classification": "confidential",
    },

    # RESTRICTED
    {
        "application_name": "Privileged Token Rotation",
        "business_purpose": "Rotate administrative credentials for privileged services",
        "data_fields": "privileged_username access_token private_key secret_value",
        "connector_metadata": "secret vault",
        "expected_classification": "restricted",
    },
    {
        "application_name": "Bank Transfer Approval",
        "business_purpose": "Authorize sensitive bank payment instructions",
        "data_fields": "bank_account routing_number transfer_amount auth_token",
        "connector_metadata": "banking gateway",
        "expected_classification": "restricted",
    },
    {
        "application_name": "Card Settlement Console",
        "business_purpose": "Reconcile sensitive payment card transactions",
        "data_fields": "card_number expiry security_code merchant_id",
        "connector_metadata": "payment network",
        "expected_classification": "restricted",
    },
    {
        "application_name": "Production Credential Recovery",
        "business_purpose": "Recover protected credentials used by production services",
        "data_fields": "root_password api_secret client_secret",
        "connector_metadata": "privileged access vault",
        "expected_classification": "restricted",
    },
    {
        "application_name": "Payroll Deposit Setup",
        "business_purpose": "Maintain employee bank details for direct deposit",
        "data_fields": "employee_id bank_account routing_number",
        "connector_metadata": "payroll banking API",
        "expected_classification": "restricted",
    },
]


def main():
    dataframe = pd.DataFrame(ROWS)

    output = (
        Path(__file__).parent
        / "classification_challenge_set.csv"
    )

    dataframe.to_csv(output, index=False)

    print(f"Challenge set written: {output}")
    print(f"Rows: {len(dataframe)}")

    print(
        dataframe["expected_classification"]
        .value_counts()
        .sort_index()
    )


if __name__ == "__main__":
    main()
