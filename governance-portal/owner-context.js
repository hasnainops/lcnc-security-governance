(function (root) {
  "use strict";
  function parseFields(text, scope) {
    if (scope === "no_data_fields") return [];
    const fields = text.split(/\r?\n/).filter(line => line.trim()).map(line => {
      const colon = line.indexOf(":");
      if (colon < 1) throw new Error("Use field_name: description on each line.");
      const name = line.slice(0, colon).trim();
      const description = line.slice(colon + 1).trim();
      if (!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(name) || !description || description.length > 255) {
        throw new Error("Use a valid field name and a description of 1–255 characters.");
      }
      return { name, description };
    });
    if (!fields.length || fields.length > 100) throw new Error("Describe between 1 and 100 fields, or select no data fields.");
    if (new Set(fields.map(field => field.name.toLowerCase())).size !== fields.length) throw new Error("Field names must be unique.");
    return fields;
  }
  function validateCredential(value, applicationId) {
    if (!value || value.application_id !== applicationId) throw new Error("This credential belongs to a different application.");
    if (!/^lo1_[A-Za-z0-9_-]{43}$/.test(value.token || "")) throw new Error("Invalid owner credential file.");
    if (!Number.isFinite(Date.parse(value.expires_at)) || Date.parse(value.expires_at) <= Date.now()) throw new Error("This credential has expired. Request a new file from your operator.");
    return value;
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { parseFields, validateCredential };
  if (!root.document) return;
  const doc = root.document, get = id => doc.getElementById(id);
  let credential = null, generation = 0, saving = false, polling = false;
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, { ...options, cache: "no-store", signal: controller.signal });
      if (!response.ok) {
        const messages = { 401: "Owner credential is missing, expired or revoked.", 403: "Owner credential does not cover this application.",
                           422: "Check the business purpose, field definitions and attestation.", 404: "Application is no longer in inventory." };
        throw new Error(messages[response.status] || `Service unavailable (HTTP ${response.status}). Your declaration may already be saved; refresh before retrying.`);
      }
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  function render(state) {
    get("classificationStatus").textContent = `Status: ${state.ml_classification_status || "unavailable"}`;
    get("classificationDetails").replaceChildren();
    const rows = [
      ["AI suggestion", state.ml_classification_status === "assessed" ? state.suggested_classification : "Awaiting current evidence"],
      ["Confidence", state.ml_classification_status === "assessed" && Number.isFinite(state.confidence) ? `${(state.confidence * 100).toFixed(1)}%` : "—"],
      ["Human review", state.review_required === true ? "Required" : state.review_required === false ? "No additional model review flagged" : "Pending assessment"],
      ["Governed classification", state.authoritative_classification || "unknown"],
      ["Assessed at", state.ml_classification_status === "assessed" ? state.classified_at : "—"]
    ];
    for (const [label, value] of rows) {
      const term = doc.createElement("dt"), description = doc.createElement("dd");
      term.textContent = label; description.textContent = value || "—";
      get("classificationDetails").append(term, description);
    }
    get("classificationEvidence").textContent = JSON.stringify({ pending_reasons: state.pending_reasons || [], provenance: state.provenance || null }, null, 2);
  }
  async function refreshState() {
    const id = get("ownerApplication").value, version = generation;
    if (!id || polling) return;
    polling = true;
    try {
      const state = await request(`/api/applications/${id}/classification-state`);
      if (version === generation) render(state);
    } catch (error) {
      if (version === generation) { render({ ml_classification_status: "unavailable" }); get("classificationStatus").textContent = error.message; }
    } finally { polling = false; }
  }
  function selectionChanged() {
    generation += 1; credential = null; get("ownerCredential").value = "";
    get("credentialStatus").textContent = "Load the private owner credential for the selected application.";
    get("ownerMessage").textContent = "";
    get("businessPurpose").value = ""; get("fieldDefinitions").value = ""; get("attested").checked = false;
    render({ ml_classification_status: "loading" }); refreshState();
  }
  async function loadApplications() {
    try {
      const applications = await request("/api/applications");
      if (!Array.isArray(applications)) throw new Error("Invalid inventory response.");
      const selected = get("ownerApplication").value;
      get("ownerApplication").replaceChildren(new Option("Choose an application", ""));
      for (const app of applications.filter(item => item.platform === "appsmith")) {
        get("ownerApplication").append(new Option(`${app.name} · ${app.id}`, app.id));
      }
      get("ownerApplication").value = selected;
      if (!get("ownerApplication").value) selectionChanged();
    } catch (error) { get("ownerMessage").textContent = error.message; }
  }
  get("ownerApplication").addEventListener("change", selectionChanged);
  get("reloadApplications").addEventListener("click", loadApplications);
  get("ownerCredential").addEventListener("change", async () => {
    credential = null;
    const version = generation, file = get("ownerCredential").files[0];
    try {
      if (!file || file.size > 4096) throw new Error("Select the small JSON credential file issued by your operator.");
      const parsed = JSON.parse(await file.text());
      if (version !== generation) return;
      credential = validateCredential(parsed, get("ownerApplication").value);
      get("credentialStatus").textContent = "Credential loaded for this application. It will be verified when you save.";
    } catch (error) { get("credentialStatus").textContent = error instanceof SyntaxError ? "Invalid credential file." : error.message; }
  });
  get("fieldScope").addEventListener("change", () => {
    const enabled = get("fieldScope").value === "declared_schema";
    get("fieldDefinitions").disabled = !enabled; get("fieldDefinitions").required = enabled;
  });
  get("ownerForm").addEventListener("submit", async event => {
    event.preventDefault();
    if (saving) return;
    const id = get("ownerApplication").value, version = generation;
    try {
      validateCredential(credential, id);
      const body = { contract_version: "owner-context-v1", business_purpose: get("businessPurpose").value.trim(),
                     field_scope: get("fieldScope").value, data_fields: parseFields(get("fieldDefinitions").value, get("fieldScope").value),
                     attested: get("attested").checked };
      saving = true; get("saveContext").disabled = true;
      get("ownerMessage").textContent = "Saving declaration and requesting assessment…";
      const result = await request(`/api/applications/${id}/owner-context`, { method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${credential.token}` }, body: JSON.stringify(body) });
      if (version !== generation) return;
      render(result.classification);
      get("ownerMessage").textContent = result.classification.action === "assessed" || result.classification.ml_classification_status === "assessed"
        ? "Declaration saved. Automatic classification is available." : "Declaration saved. Classification is pending; scheduled discovery will retry automatically.";
    } catch (error) { if (version === generation) get("ownerMessage").textContent = error.message; }
    finally { saving = false; get("saveContext").disabled = false; }
  });
  setInterval(() => { if (!doc.hidden) refreshState(); }, 5000);
  loadApplications();
})(typeof globalThis !== "undefined" ? globalThis : this);
