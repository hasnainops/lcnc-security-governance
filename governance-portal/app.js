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
