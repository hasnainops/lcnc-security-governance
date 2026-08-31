import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split


DATASET = "ml-analytics/training/synthetic_lcnc_applications.csv"

FEATURES = [
    "owner_known",
    "business_purpose_known",
    "internet_exposed",
    "external_integration_count",
    "unapproved_integration_count",
    "uses_api_key",
    "connector_count",
    "external_domain_count",
    "changes_last_24h",
]

CONTAMINATION_VALUES = [
    0.01,
    0.02,
    0.03,
    0.05,
    0.08,
    0.10,
]


data = pd.read_csv(DATASET)

normal = data[data["expected_anomaly"] == 0]
anomaly = data[data["expected_anomaly"] == 1]

normal_train, normal_temp = train_test_split(
    normal,
    test_size=0.30,
    random_state=42,
)

normal_validation, normal_test = train_test_split(
    normal_temp,
    test_size=0.50,
    random_state=42,
)

anomaly_validation, anomaly_test = train_test_split(
    anomaly,
    test_size=0.50,
    random_state=42,
)

validation = pd.concat(
    [normal_validation, anomaly_validation],
    ignore_index=True,
)

test = pd.concat(
    [normal_test, anomaly_test],
    ignore_index=True,
)

print("Dataset split")
print("-------------")
print("Training normals:", len(normal_train))
print("Validation normals:", len(normal_validation))
print("Validation anomalies:", len(anomaly_validation))
print("Test normals:", len(normal_test))
print("Test anomalies:", len(anomaly_test))
print()

results = []

for contamination in CONTAMINATION_VALUES:
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
    )

    model.fit(normal_train[FEATURES])

    prediction = model.predict(validation[FEATURES])
    predicted_anomaly = (prediction == -1).astype(int)

    expected = validation["expected_anomaly"]

    false_positives = (
        (predicted_anomaly == 1)
        & (expected.to_numpy() == 0)
    ).sum()

    normal_count = (expected == 0).sum()
    false_positive_rate = false_positives / normal_count

    results.append(
        {
            "contamination": contamination,
            "precision": precision_score(
                expected,
                predicted_anomaly,
                zero_division=0,
            ),
            "recall": recall_score(
                expected,
                predicted_anomaly,
                zero_division=0,
            ),
            "f1": f1_score(
                expected,
                predicted_anomaly,
                zero_division=0,
            ),
            "false_positive_rate": false_positive_rate,
        }
    )


results = pd.DataFrame(results)

print("Validation results")
print("------------------")
print(
    results.round(4).to_string(index=False)
)

best = results.sort_values(
    ["f1", "recall", "false_positive_rate"],
    ascending=[False, False, True],
).iloc[0]

selected_contamination = float(best["contamination"])

print()
print(
    "Selected contamination:",
    selected_contamination,
)

final_model = IsolationForest(
    n_estimators=200,
    contamination=selected_contamination,
    random_state=42,
)

final_training = pd.concat(
    [normal_train, normal_validation],
    ignore_index=True,
)

final_model.fit(final_training[FEATURES])

test_prediction = final_model.predict(test[FEATURES])
test_anomaly = (test_prediction == -1).astype(int)

expected_test = test["expected_anomaly"]

false_positives = (
    (test_anomaly == 1)
    & (expected_test.to_numpy() == 0)
).sum()

test_normal_count = (expected_test == 0).sum()

print()
print("Held-out test results")
print("---------------------")
print(
    "precision:",
    round(
        precision_score(
            expected_test,
            test_anomaly,
            zero_division=0,
        ),
        4,
    ),
)
print(
    "recall:",
    round(
        recall_score(
            expected_test,
            test_anomaly,
            zero_division=0,
        ),
        4,
    ),
)
print(
    "f1:",
    round(
        f1_score(
            expected_test,
            test_anomaly,
            zero_division=0,
        ),
        4,
    ),
)
print(
    "accuracy:",
    round(
        accuracy_score(
            expected_test,
            test_anomaly,
        ),
        4,
    ),
)
print(
    "false_positive_rate:",
    round(
        false_positives / test_normal_count,
        4,
    ),
)
