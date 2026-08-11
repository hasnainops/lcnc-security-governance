# LCNC Security Governance Live Demo Runbook

## Objective

Demonstrate an end-to-end governance lifecycle for a low-code/no-code application:

Shadow application discovery
→ risk assessment
→ hard policy enforcement
→ governance decision
→ remediation
→ reassessment
→ audit evidence
→ observability
→ security validation

Target duration: 10–15 minutes.

## 1. Pre-Demo Preparation

### Browser Tabs

Open before the interview:

1. Governance Portal — http://localhost:3000
2. Appsmith — http://localhost:8080
3. Grafana — http://localhost:3001
4. Prometheus — http://localhost:9090
5. GitHub repository / Security Validation workflow

Keep the Governance Portal as the main demo tab.

## 2. Terminal Preparation

Project directory:

    cd ~/Projects/lcnc-security-governance

Activate environment if needed:

    source .venv/bin/activate

Verify services:

    docker compose ps

Required healthy services:

- Appsmith
- Governance API
- Governance Portal
- PostgreSQL
- Risk Engine

OPA, Prometheus, and Grafana should also be running.

## 3. Resolve Demo Application

Use Customer Data Export as the main scenario.

    APP_ID=$(
      curl -s http://localhost:8000/applications |
      jq -r '.[] | select(.name == "Customer Data Export") | .id'
    )

    echo "$APP_ID"
