from prometheus_client import Counter, Histogram


RISK_ASSESSMENTS_TOTAL = Counter(
    "lcnc_risk_assessments_total",
    "Total LCNC risk assessments performed",
    ["level"],
)

RISK_SCORE = Histogram(
    "lcnc_risk_score",
    "Distribution of LCNC application risk scores",
    buckets=(0, 10, 20, 25, 50, 75, 90, 100),
)

POLICY_DECISIONS_TOTAL = Counter(
    "lcnc_policy_decisions_total",
    "Total OPA governance policy decisions",
    ["action"],
)

GOVERNANCE_OUTCOMES_TOTAL = Counter(
    "lcnc_governance_outcomes_total",
    "Total final governance workflow outcomes",
    ["outcome", "status"],
)

GOVERNANCE_WORKFLOW_DURATION = Histogram(
    "lcnc_governance_workflow_duration_seconds",
    "Time spent running the complete governance workflow",
)
