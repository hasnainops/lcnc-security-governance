/* Platform observations only: no workflow actions or Docker access from the browser. */
(() => {
  "use strict";
  const functionalApi = typeof module !== "undefined"
    ? require("./functional-overview.js") : window.FunctionalOverview;
  const catalog = [
    ["governance-portal", "Exam interface"],
    ["appsmith", "Low-code applications"],
    ["appsmith-proxy", "Appsmith browser entry"],
    ["discovery", "Appsmith inventory collection"],
    ["enterprise-discovery", "Enterprise inventory"],
    ["governance-api", "Caddy API entry"],
    ["governance-api-a", "Governance orchestration · replica A"],
    ["governance-api-b", "Governance orchestration · replica B"],
    ["risk-engine", "Risk analysis"],
    ["ml-analytics", "ML anomaly and classification analysis"],
    ["security-scanner", "Security analysis"],
    ["opa", "Governance and access policy"],
    ["governance-automation", "Approval and JIT lifecycle"],
    ["integration-gateway", "Transfer evaluation"],
    ["dlp-engine", "Sensitive content inspection"],
    ["postgres", "Persistent records"],
    ["vault", "Secrets and workload credentials"],
    ["prometheus", "Metrics collection"],
    ["grafana", "Metrics dashboards"],
    ["sonarqube", "Code quality tooling"]
  ];
  const states = new Set(["created", "running", "paused", "restarting", "removing", "exited", "dead", "missing", "multiple", "unknown"]);
  const health = new Set(["healthy", "unhealthy", "starting", "not_configured", "unknown"]);
  const esc = value => String(value ?? "—").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);

  function validate(data) {
    if (!data || data.schema_version !== 1 || data.source !== "docker_compose" ||
        !["current", "stale", "unavailable"].includes(data.observation_status) ||
        data.stale_after_seconds !== 30 || !Array.isArray(data.services) ||
        data.services.length !== catalog.length) throw new Error("Invalid status response");
    const names = new Set(data.services.map(item => item.service));
    if (names.size !== catalog.length || catalog.some(([name]) => !names.has(name))) {
      throw new Error("Unexpected service catalog");
    }
    if (data.observation_status !== "unavailable" &&
        (!Number.isFinite(Date.parse(data.observed_at)) ||
         typeof data.age_seconds !== "number" || !Number.isFinite(data.age_seconds) || data.age_seconds < 0)) {
      throw new Error("Invalid observation time");
    }
    for (const item of data.services) {
      if (!states.has(item.container_state) || !health.has(item.docker_health) ||
          item.observation_status !== data.observation_status ||
          (item.container_count !== null && (!Number.isInteger(item.container_count) || item.container_count < 0))) {
        throw new Error("Invalid service observation");
      }
      if (data.observation_status !== "unavailable" && item.container_count === null) {
        throw new Error("Missing container count");
      }
    }
    return data;
  }

  function view(data, elapsedSeconds = 0) {
    const age = data && typeof data.age_seconds === "number" ? data.age_seconds + Math.max(0, elapsedSeconds) : null;
    let status = data?.observation_status || "unavailable";
    if (status === "current" && age > 30) status = "stale";
    const current = status === "current";
    const services = catalog.map(([name, role]) => {
      const item = data?.services.find(row => row.service === name);
      return { name, role, count: status === "unavailable" ? null : item?.container_count,
        state: status === "unavailable" ? "unknown" : item?.container_state,
        health: status === "unavailable" ? "unknown" : item?.docker_health };
    });
    return { status, age, services,
      counts: current ? [services.filter(s => s.state === "running").length,
        services.filter(s => s.state === "running" && s.health === "healthy").length,
        services.filter(s => s.health === "not_configured").length,
        services.filter(s => s.state === "missing" || s.state === "multiple").length] : [null, null, null, null] };
  }

  function mount(doc, fetcher = fetch) {
    const get = id => doc.getElementById(id);
    let data = null;
    let received = 0;
    let receivedMono = 0;
    let requestDuration = 0;
    let failure = "Waiting for status response";
    let busy = false;
    let functionalData = null;
    let functionalBusy = false;
    let functionalReceived = 0;
    let functionalMono = 0;
    let functionalDuration = 0;

    function functionalCell(service) {
      if (!functionalApi.services.includes(service)) {
        return "<td>Not configured</td>";
      }
      const elapsed = Math.max(
        0, (Date.now() - functionalReceived) / 1000,
        (performance.now() - functionalMono) / 1000
      ) + functionalDuration;
      const item = functionalApi.view(functionalData, elapsed)
        .find(check => check.service === service);
      const labels = {
        passed: "Passed", failed: "Failed",
        stale: "Stale", unavailable: "Unavailable"
      };
      const policy = item.check === "policy_decisions";
      const checkLabel = policy ? "Policy decisions" : "Inventory read";
      const detail = item.status === "passed"
        ? (policy
          ? `${item.cases_passed}/${item.cases_total} cases matched`
          : `${item.application_count} applications`)
        : item.reason;
      const timing = item.observed_at
        ? `Observed ${item.observed_at} · age ${Math.floor(item.age_seconds)}s`
        : "No usable observation";
      return `<td><strong>${esc(labels[item.status])}</strong>` +
        `<small>${esc(checkLabel)} · ${esc(detail)}</small>` +
        `<small>${esc(timing)}</small></td>`;
    }

    async function refreshFunctional() {
      if (functionalBusy) return;
      functionalBusy = true;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      const started = performance.now();
      try {
        const response = await fetcher("/api/exam/functional-status", {
          cache: "no-store", signal: controller.signal
        });
        if (!response.ok) throw new Error("Functional report unavailable");
        functionalData = functionalApi.validate(await response.json());
        functionalReceived = Date.now();
        functionalMono = performance.now();
        functionalDuration = (functionalMono - started) / 1000;
      } catch (error) {
        functionalData = null;
      } finally {
        clearTimeout(timer);
        functionalBusy = false;
        render();
      }
    }
    function render() {
      // Age locally even when polling fails or a background tab's timers are paused.
      const elapsed = Math.max(0, (Date.now() - received) / 1000, (performance.now() - receivedMono) / 1000) + requestDuration;
      const model = view(data, elapsed);
      const observation = get("platformObservation");
      observation.className = model.status;
      observation.textContent = model.status === "current"
        ? "Current observation · this does not certify every business workflow."
        : model.status === "stale"
          ? "Stale observation · last known values only; current counts withheld. Check the host collector."
          : `Observation unavailable · ${failure || data?.reason || "unknown reason"}. Container health cannot be inferred.`;
      get("platformTime").textContent = data?.observed_at
        ? `Source: Docker Compose · observed ${data.observed_at} · age ${model.age === null ? "unknown" : Math.floor(model.age) + "s"} · refresh every 10s`
        : "Source: Docker Compose · no usable observation timestamp";
      const labels = ["Running / 20 expected", "Docker healthy", "Health check not configured", "Missing or multiple"];
      get("platformSummary").innerHTML = labels.map((label, i) =>
        `<div class="metric"><span>${esc(model.counts[i])}</span><small>${label}</small></div>`).join("");
      get("platformRows").innerHTML = model.services.map(item =>
        `<tr class="${model.status}"><td><strong>${esc(item.name)}</strong><small>${esc(item.role)}</small></td>` +
        `<td>${esc(item.count)}</td><td>${esc(item.state)}</td>` +
        `<td class="${model.status === "current" ? esc(item.health) : model.status}">${esc(item.health === "not_configured" ? "Not configured" : item.health)}</td>` +
        `<td>${model.status}</td>` + functionalCell(item.name) + `</tr>`).join("");
    }
    async function refresh() {
      if (busy) return;
      busy = true;
      get("platformRefresh").disabled = true;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      const started = performance.now();
      try {
        const response = await fetcher("/api/exam/platform-status", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error(`API HTTP ${response.status}`);
        data = validate(await response.json());
        received = Date.now();
        receivedMono = performance.now();
        requestDuration = (receivedMono - started) / 1000;
        failure = "";
      } catch (error) {
        data = null; // Never preserve a green display after a failed read.
        failure = error.name === "AbortError" ? "API request timed out" : error.message;
      } finally {
        clearTimeout(timer);
        busy = false;
        get("platformRefresh").disabled = false;
        render();
      }
    }
    get("platformRefresh").addEventListener("click", refresh);
    get("platformRefresh").addEventListener("click", refreshFunctional);
    doc.addEventListener("visibilitychange", () => {
      if (!doc.hidden) { render(); refresh(); refreshFunctional(); }
    });
    setInterval(() => { if (!doc.hidden) refresh(); }, 10000);
    setInterval(() => { if (!doc.hidden) refreshFunctional(); }, 10000);
    setInterval(() => { if (!doc.hidden) render(); }, 1000);
    render();
    refresh();
    refreshFunctional();
    return { refresh, refreshFunctional, render };
  }
  if (typeof module !== "undefined") module.exports = { catalog, validate, view, mount };
  if (typeof document !== "undefined") mount(document);
})();
