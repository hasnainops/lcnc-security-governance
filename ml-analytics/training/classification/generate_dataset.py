from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 42
SAMPLES_PER_CLASS = 120

rng = np.random.default_rng(RANDOM_SEED)


CLASS_DATA = {
    "public": {
        "names": [
            "Public Event Directory",
            "Marketing Campaign Page",
            "Public Product Catalog",
            "Community Information Portal",
            "Press Release Tracker",
        ],
        "purposes": [
            "Publish information intended for external audiences",
            "Provide public marketing and product information",
            "Share approved public content with customers",
            "Display public events and announcements",
        ],
        "fields": [
            "title description category public_url",
            "event_name event_date venue public_link",
            "product_name description public_price",
            "headline summary publication_date",
        ],
        "connectors": [
            "public website",
            "approved marketing API",
            "public content feed",
            "public CMS",
        ],
    },
    "internal": {
        "names": [
            "Internal Project Tracker",
            "Employee Equipment Request",
            "Operations Task Board",
            "Internal Knowledge Workflow",
            "Department Planning App",
        ],
        "purposes": [
            "Support internal business operations",
            "Coordinate employee workflow and project tasks",
            "Track internal requests and operational activities",
            "Manage internal department planning",
        ],
        "fields": [
            "employee_name department task_status",
            "project_code owner team deadline",
            "asset_type employee_id approval_status",
            "department cost_center internal_notes",
        ],
        "connectors": [
            "internal database",
            "corporate workflow API",
            "internal ticketing system",
            "enterprise directory",
        ],
    },
    "confidential": {
        "names": [
            "Customer Service Workspace",
            "Customer Data Export",
            "Account Support Dashboard",
            "Client Contact Manager",
            "Customer Operations Portal",
        ],
        "purposes": [
            "Process customer records for approved support operations",
            "Manage customer contact information",
            "Support customer account servicing",
            "Analyze customer operational records",
        ],
        "fields": [
            "customer_name email phone customer_id",
            "account_id email billing_address phone",
            "customer_id contact_email address",
            "client_name phone_number support_case",
        ],
        "connectors": [
            "CRM API",
            "customer database",
            "approved customer service API",
            "customer support platform",
        ],
    },
    "restricted": {
        "names": [
            "Payment Administration Tool",
            "Credential Operations Workflow",
            "Privileged Access Manager",
            "Financial Card Processing App",
            "Secrets Rotation Workflow",
        ],
        "purposes": [
            "Process highly sensitive payment information",
            "Manage privileged credentials and secrets",
            "Handle restricted financial transaction data",
            "Support privileged access administration",
        ],
        "fields": [
            "card_number expiry_date cvv account_holder",
            "password access_token secret_key",
            "api_secret privileged_account credential",
            "bank_account routing_number payment_token",
        ],
        "connectors": [
            "payment processor",
            "privileged access system",
            "secret management service",
            "restricted financial API",
        ],
    },
}


def generate_rows():
    rows = []

    for label, values in CLASS_DATA.items():
        for _ in range(SAMPLES_PER_CLASS):
            rows.append(
                {
                    "application_name": rng.choice(
                        values["names"]
                    ),
                    "business_purpose": rng.choice(
                        values["purposes"]
                    ),
                    "data_fields": rng.choice(
                        values["fields"]
                    ),
                    "connector_metadata": rng.choice(
                        values["connectors"]
                    ),
                    "expected_classification": label,
                }
            )

    return rows


def main():
    dataframe = pd.DataFrame(generate_rows())

    dataframe = dataframe.sample(
        frac=1,
        random_state=RANDOM_SEED,
    ).reset_index(drop=True)

    output = (
        Path(__file__).parent
        / "synthetic_classification_dataset.csv"
    )

    dataframe.to_csv(output, index=False)

    print(f"Dataset written: {output}")
    print(f"Rows: {len(dataframe)}")
    print(
        dataframe["expected_classification"]
        .value_counts()
        .sort_index()
    )


if __name__ == "__main__":
    main()
