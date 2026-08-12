from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 42
NORMAL_SAMPLES = 300
ANOMALY_SAMPLES = 50

rng = np.random.default_rng(RANDOM_SEED)


def generate_normal():
    rows = []

    for _ in range(NORMAL_SAMPLES):
        rows.append(
            {
                "owner_known": int(rng.random() < 0.96),
                "business_purpose_known": int(rng.random() < 0.94),
                "internet_exposed": int(rng.random() < 0.12),
                "external_integration_count": int(
                    rng.choice([0, 1, 2], p=[0.60, 0.32, 0.08])
                ),
                "unapproved_integration_count": 0,
                "uses_api_key": int(rng.random() < 0.15),
                "connector_count": int(
                    rng.choice([1, 2, 3, 4], p=[0.35, 0.40, 0.20, 0.05])
                ),
                "external_domain_count": int(
                    rng.choice([0, 1, 2], p=[0.65, 0.30, 0.05])
                ),
                "changes_last_24h": int(
                    rng.choice([0, 1, 2], p=[0.70, 0.25, 0.05])
                ),
                "expected_anomaly": 0,
            }
        )

    return rows


def generate_anomalies():
    rows = []

    for _ in range(ANOMALY_SAMPLES):
        external_count = int(rng.integers(2, 7))

        rows.append(
            {
                "owner_known": int(rng.random() < 0.25),
                "business_purpose_known": int(rng.random() < 0.30),
                "internet_exposed": int(rng.random() < 0.75),
                "external_integration_count": external_count,
                "unapproved_integration_count": int(
                    rng.integers(1, external_count + 1)
                ),
                "uses_api_key": int(rng.random() < 0.80),
                "connector_count": int(rng.integers(4, 10)),
                "external_domain_count": int(rng.integers(2, 7)),
                "changes_last_24h": int(rng.integers(3, 12)),
                "expected_anomaly": 1,
            }
        )

    return rows


def main():
    rows = generate_normal() + generate_anomalies()

    dataframe = pd.DataFrame(rows)
    dataframe = dataframe.sample(
        frac=1,
        random_state=RANDOM_SEED,
    ).reset_index(drop=True)

    output = Path(__file__).parent / "synthetic_lcnc_applications.csv"
    dataframe.to_csv(output, index=False)

    print(f"Dataset written: {output}")
    print(f"Rows: {len(dataframe)}")
    print(
        dataframe["expected_anomaly"]
        .value_counts()
        .sort_index()
        .rename(index={0: "normal", 1: "anomaly"})
    )


if __name__ == "__main__":
    main()
