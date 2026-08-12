let selectedApplicationId = null;

const rows = document.getElementById("applicationRows");
const detailPanel = document.getElementById("detailPanel");
const message = document.getElementById("message");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function badge(value) {
  const text = value ?? "unknown";
  const css = String(text).toLowerCase();

  return `<span class="badge ${escapeHtml(css)}">${escapeHtml(text)}</span>`;
}

function showMessage(text) {
  message.textContent = text;
  message.classList.remove("hidden");

  setTimeout(() => {
    message.classList.add("hidden");
  }, 3000);
}

async function loadApplications() {
  const response = await fetch("/api/applications");

  if (!response.ok) {
    throw new Error("Unable to retrieve applications");
  }

  const applications = await response.json();

  document.getElementById("applicationCount").textContent =
    applications.length;

  document.getElementById("criticalCount").textContent =
    applications.filter(app => app.risk_level === "critical").length;

  document.getElementById("blockedCount").textContent =
    applications.filter(app => app.governance_status === "blocked").length;

  document.getElementById("unregisteredCount").textContent =
    applications.filter(app => app.registration_status === "unregistered").length;

  rows.innerHTML = "";

  for (const app of applications) {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td><strong>${escapeHtml(app.name)}</strong></td>
      <td>${escapeHtml(app.platform)}</td>
      <td>${badge(app.registration_status)}</td>
      <td>${escapeHtml(app.owner_name || "Unknown")}</td>
      <td>
        ${badge(app.risk_level || "not assessed")}
        ${app.risk_score !== null ? ` ${escapeHtml(app.risk_score)}` : ""}
      </td>
      <td>${badge(app.governance_outcome || "not evaluated")}</td>
    `;

    row.addEventListener("click", () => loadHistory(app.id));
    rows.appendChild(row);
  }
}

function renderDetail(label, value) {
  return `
    <div class="detail-item">
      <strong>${escapeHtml(label)}</strong>
      ${escapeHtml(value ?? "Unknown")}
    </div>
  `;
}

async function loadComplianceEvidence(applicationId) {
  const response = await fetch(
    `/api/applications/${applicationId}/compliance-evidence`
  );

  if (!response.ok) {
    throw new Error("Unable to retrieve compliance evidence");
  }

  const data = await response.json();
  const container = document.getElementById("complianceEvidence");

  container.innerHTML = "";

  for (const control of data.controls) {
    const element = document.createElement("div");
    element.className = "history-entry";

    const nist = control.framework_mapping.nist_csf_2_0.join(", ");
    const iso = control.framework_mapping.iso_iec_27001.join(", ");
    const owasp =
      control.framework_mapping.owasp_citizen_development.join(", ");

    element.innerHTML = `
      <p>
        <strong>
          ${escapeHtml(control.id)}
          — ${escapeHtml(control.control_objective)}
        </strong>
      </p>

      <p>
        Evidence:
        ${badge(control.evidence_status)}
      </p>

      <p>
        ${escapeHtml(control.evidence_summary)}
      </p>

      <p>
        Responsible role:
        ${escapeHtml(control.responsible_role)}
      </p>

      <p>
        NIST CSF 2.0:
        ${escapeHtml(nist)}
      </p>

      <p>
        ISO/IEC 27001 alignment:
        ${escapeHtml(iso)}
      </p>

      <p>
        OWASP Citizen Development:
        ${escapeHtml(owasp || "Not specifically mapped")}
      </p>
    `;

    container.appendChild(element);
  }
}

async function loadHistory(applicationId) {
  selectedApplicationId = applicationId;

  const response = await fetch(
    `/api/applications/${applicationId}/history`
  );

  if (!response.ok) {
    throw new Error("Unable to retrieve application history");
  }

  const data = await response.json();
  const app = data.application;

  document.getElementById("detailName").textContent = app.name;
  document.getElementById("detailPlatform").textContent =
    `${app.platform} · ${app.external_id}`;

  document.getElementById("applicationDetails").innerHTML =
    renderDetail("Registration", app.registration_status) +
    renderDetail("Owner", app.owner_name || "Unknown") +
    renderDetail("Business Unit", app.business_unit || "Unknown") +
    renderDetail("Data Classification", app.data_classification) +
    renderDetail(
      "External Integration",
      app.external_integration === null
        ? "Unknown"
        : app.external_integration ? "Yes" : "No"
    ) +
    renderDetail("Risk", `${app.risk_score ?? "—"} / ${app.risk_level ?? "not assessed"}`) +
    renderDetail("Governance", app.governance_outcome || "Not evaluated") +
    renderDetail("Governance Status", app.governance_status) +
    renderDetail("Last Seen", app.last_seen_at);

  const riskHistory = document.getElementById("riskHistory");
  riskHistory.innerHTML = "";

  for (const risk of data.risk_assessments) {
    const element = document.createElement("div");
    element.className = "history-entry";

    element.innerHTML = `
      <p><strong>${escapeHtml(risk.score)} / ${escapeHtml(risk.level)}</strong></p>
      <p>Model: ${escapeHtml(risk.model_version)}</p>
      <p>${escapeHtml(risk.assessed_at)}</p>
    `;

    riskHistory.appendChild(element);
  }

  const policyHistory = document.getElementById("policyHistory");
  policyHistory.innerHTML = "";

  for (const policy of data.policy_decisions) {
    const element = document.createElement("div");
    element.className = "history-entry";

    element.innerHTML = `
      <p><strong>${escapeHtml(policy.action.toUpperCase())}</strong></p>
      <p>${escapeHtml(policy.reasons.join(" ") || "No policy violations")}</p>
      <p>Policy: ${escapeHtml(policy.policy_version)}</p>
      <p>${escapeHtml(policy.evaluated_at)}</p>
    `;

    policyHistory.appendChild(element);
  }

  const governanceHistory =
    document.getElementById("governanceHistory");

  governanceHistory.innerHTML = "";

  for (const governance of data.governance_decisions) {
    const element = document.createElement("div");
    element.className = "history-entry";

    element.innerHTML = `
      <p><strong>${escapeHtml(governance.outcome)}</strong></p>
      <p>Status: ${escapeHtml(governance.status)}</p>
      <p>Required role: ${escapeHtml(governance.required_role || "None")}</p>
      <p>${escapeHtml(governance.reasons.join(" "))}</p>
      <p>${escapeHtml(governance.created_at)}</p>
    `;

    governanceHistory.appendChild(element);
  }

  await loadComplianceEvidence(applicationId);

  await loadV2Evidence(
    applicationId,
    data
  );

  detailPanel.classList.remove("hidden");
}

async function runGovernanceEvaluation() {
  if (!selectedApplicationId) {
    return;
  }

  const button = document.getElementById("evaluateButton");
  button.disabled = true;
  button.textContent = "Evaluating...";

  try {
    const response = await fetch(
      `/api/applications/${selectedApplicationId}/governance-evaluate`,
      {
        method: "POST"
      }
    );

    if (!response.ok) {
      throw new Error("Governance evaluation failed");
    }

    const result = await response.json();

    showMessage(
      `${result.application_name}: ${result.governance.outcome}`
    );

    await loadApplications();
    await loadHistory(selectedApplicationId);

  } finally {
    button.disabled = false;
    button.textContent = "Run Governance Evaluation";
  }
}

document
  .getElementById("refreshButton")
  .addEventListener("click", async () => {
    await loadApplications();

    if (selectedApplicationId) {
      await loadHistory(selectedApplicationId);
    }
  });

document
  .getElementById("evaluateButton")
  .addEventListener("click", runGovernanceEvaluation);

loadApplications().catch(error => {
  showMessage(error.message);
});


async function fetchJsonOrNull(url) {
  try {
    const response = await fetch(url);

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch {
    return null;
  }
}


function latest(items) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }

  return items[0];
}


function displayPercent(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return "—";
  }

  return `${(Number(value) * 100).toFixed(1)}%`;
}


function renderEvidenceCard(label, primary, secondary = "") {
  return `
    <div class="evidence-card">
      <strong>${escapeHtml(label)}</strong>

      <div class="primary">
        ${escapeHtml(primary ?? "Not assessed")}
      </div>

      ${
        secondary
          ? `<div class="secondary">${escapeHtml(secondary)}</div>`
          : ""
      }
    </div>
  `;
}


function renderV2Summary(history, compliance, guidance) {
  const container =
    document.getElementById("v2Summary");

  if (!container) {
    return;
  }

  const anomaly =
    latest(history.ml_assessments);

  const classification =
    latest(history.classification_assessments);

  const scan =
    latest(history.security_scans);

  const transfer =
    latest(history.integration_transfer_events);

  const access =
    latest(history.access_decisions);

  let html = "";

  html += renderEvidenceCard(
    "AI Anomaly Detection",
    anomaly
      ? (
          anomaly.anomaly_detected === true
            ? "Anomaly detected"
            : "No anomaly detected"
        )
      : "Not assessed",
    anomaly
      ? `Model: ${
          anomaly.model_version ||
          anomaly.ml_model_version ||
          "isolation-forest-v1"
        }`
      : ""
  );

  html += renderEvidenceCard(
    "AI Classification",
    classification
      ? (
          classification.suggested_classification ||
          classification.predicted_classification ||
          "Not assessed"
        )
      : "Not assessed",
    classification
      ? `Confidence: ${displayPercent(
          classification.confidence
        )}`
      : ""
  );

  html += renderEvidenceCard(
    "Security Scanner",
    scan
      ? `${scan.finding_count ?? "—"} finding(s)`
      : "Not assessed",
    scan
      ? `Highest: ${
          scan.highest_severity || "none"
        }`
      : ""
  );

  html += renderEvidenceCard(
    "Latest Transfer",
    transfer
      ? (
          transfer.decision ||
          (
            transfer.allowed === true
              ? "allow"
              : transfer.allowed === false
                ? "block"
                : "Not assessed"
          )
        )
      : "Not assessed",
    transfer
      ? `Sensitivity: ${
          transfer.effective_sensitivity ||
          transfer.highest_sensitivity ||
          "unknown"
        }`
      : ""
  );

  html += renderEvidenceCard(
    "OPA Access",
    access
      ? (
          access.decision ||
          (
            access.allowed === true
              ? "allow"
              : access.allowed === false
                ? "deny"
                : "Not assessed"
          )
        )
      : "Not assessed",
    access
      ? `${
          access.role || "unknown role"
        } / ${
          access.action ||
          access.requested_action ||
          "unknown action"
        }`
      : ""
  );

  html += renderEvidenceCard(
    "Dynamic Compliance",
    compliance
      ? compliance.overall_status
      : "Not assessed",
    compliance
      ? `Pass ${
          compliance.summary?.pass ?? 0
        } · Fail ${
          compliance.summary?.fail ?? 0
        } · Not assessed ${
          compliance.summary?.not_assessed ?? 0
        }`
      : ""
  );

  if (guidance) {
    html += `
      <div class="evidence-card">
        <strong>Citizen Security Score</strong>

        <div class="score-card">
          <span class="score-value">
            ${escapeHtml(
              guidance.security_score ?? "—"
            )}
          </span>

          <span class="badge security-badge ${escapeHtml(
            guidance.badge || "needs_attention"
          )}">
            ${escapeHtml(
              guidance.badge || "Not assessed"
            )}
          </span>
        </div>

        <div class="secondary">
          ${escapeHtml(
            guidance.recommended_training_count ?? 0
          )} targeted training recommendation(s)
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
}


function renderDynamicCompliance(compliance) {
  const container =
    document.getElementById(
      "dynamicCompliance"
    );

  if (!container) {
    return;
  }

  if (
    !compliance ||
    !Array.isArray(compliance.controls)
  ) {
    container.innerHTML = `
      <div class="empty-state">
        Dynamic compliance evidence unavailable.
      </div>
    `;
    return;
  }

  container.innerHTML = "";

  for (const control of compliance.controls) {
    const element =
      document.createElement("div");

    element.className =
      `control-card ${control.status}`;

    element.innerHTML = `
      <p>
        <strong>
          ${escapeHtml(control.control_id)}
        </strong>
        ${badge(control.status)}
      </p>

      <p>
        ${escapeHtml(
          control.control_name ||
          control.title ||
          ""
        )}
      </p>

      <p>
        ${escapeHtml(
          control.evidence ||
          control.evidence_summary ||
          ""
        )}
      </p>

      ${
        control.remediation
          ? `
            <p>
              <strong>Action:</strong>
              ${escapeHtml(control.remediation)}
            </p>
          `
          : ""
      }
    `;

    container.appendChild(element);
  }
}


function renderCitizenGuidance(guidance) {
  const container =
    document.getElementById(
      "citizenGuidance"
    );

  if (!container) {
    return;
  }

  if (!guidance) {
    container.innerHTML = `
      <div class="empty-state">
        Citizen-developer guidance unavailable.
      </div>
    `;
    return;
  }

  const recommendations =
    guidance.recommended_training || [];

  let html = `
    <div class="evidence-card">
      <strong>Security posture</strong>

      <div class="score-card">
        <span class="score-value">
          ${escapeHtml(
            guidance.security_score ?? "—"
          )}
        </span>

        <span class="badge security-badge ${escapeHtml(
          guidance.badge || "needs_attention"
        )}">
          ${escapeHtml(
            guidance.badge || "Not assessed"
          )}
        </span>
      </div>

      <div class="secondary">
        Guidance version:
        ${escapeHtml(
          guidance.guidance_version || "unknown"
        )}
      </div>
    </div>
  `;

  if (recommendations.length === 0) {
    html += `
      <div class="empty-state">
        No targeted training is currently required.
      </div>
    `;

    container.innerHTML = html;
    return;
  }

  for (const item of recommendations) {
    const guidanceItems =
      Array.isArray(item.guidance)
        ? item.guidance
        : [];

    html += `
      <div class="training-card">
        <p>
          <strong>
            ${escapeHtml(item.title)}
          </strong>

          ${badge(item.control_status)}
        </p>

        <p>
          Trigger:
          ${escapeHtml(item.trigger_control)}
        </p>

        <p>
          ${escapeHtml(item.reason || "")}
        </p>

        ${
          item.remediation
            ? `
              <p>
                <strong>Remediation:</strong>
                ${escapeHtml(item.remediation)}
              </p>
            `
            : ""
        }

        ${
          guidanceItems.length
            ? `
              <ul>
                ${guidanceItems
                  .map(
                    line =>
                      `<li>${escapeHtml(line)}</li>`
                  )
                  .join("")}
              </ul>
            `
            : ""
        }
      </div>
    `;
  }

  container.innerHTML = html;
}


async function loadV2Evidence(applicationId, history) {
  const [
    compliance,
    guidance
  ] = await Promise.all([
    fetchJsonOrNull(
      `/api/applications/${applicationId}/compliance/dynamic`
    ),
    fetchJsonOrNull(
      `/api/applications/${applicationId}/citizen-guidance`
    )
  ]);

  renderV2Summary(
    history,
    compliance,
    guidance
  );

  renderDynamicCompliance(
    compliance
  );

  renderCitizenGuidance(
    guidance
  );
}
