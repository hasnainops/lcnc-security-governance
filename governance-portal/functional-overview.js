/* Functional evidence has its own timestamps, independent of Docker health. */
(() => {
  "use strict";

  const services = [
    "governance-api-a", "governance-api-b",
    "governance-api", "governance-portal"
  ];
  const reasons = new Set([
    "http_error", "response_too_large", "timeout",
    "connection_error", "invalid_inventory", "probe_error"
  ]);

  function validate(data) {
    if (!data || data.schema_version !== 1 ||
        data.source !== "internal_http_probes" ||
        data.stale_after_seconds !== 30 ||
        !Array.isArray(data.checks) ||
        data.checks.length !== services.length) {
      throw new Error("Invalid functional report");
    }

    const served = Date.parse(data.served_at);
    if (!Number.isFinite(served)) throw new Error("Invalid report time");

    const seen = new Set();
    for (const item of data.checks) {
      if (!item || !services.includes(item.service) || seen.has(item.service) ||
          item.check !== "inventory_read" ||
          !["passed", "failed"].includes(item.status)) {
        throw new Error("Invalid functional check");
      }
      seen.add(item.service);

      const observed = Date.parse(item.observed_at);
      if (!Number.isFinite(observed) || observed > served ||
          typeof item.duration_ms !== "number" ||
          !Number.isFinite(item.duration_ms) || item.duration_ms < 0) {
        throw new Error("Invalid check timing");
      }
      if (item.http_status !== null &&
          (!Number.isInteger(item.http_status) ||
           item.http_status < 100 || item.http_status > 599)) {
        throw new Error("Invalid HTTP status");
      }

      if (item.status === "passed") {
        if (item.http_status !== 200 || item.reason !== null ||
            !Number.isSafeInteger(item.application_count) ||
            item.application_count < 0) {
          throw new Error("Inconsistent successful check");
        }
      } else if (!reasons.has(item.reason) || item.application_count !== null) {
        throw new Error("Inconsistent failed check");
      }
    }
    return data;
  }

  function view(data, elapsedSeconds = 0) {
    const elapsed = Number.isFinite(elapsedSeconds)
      ? Math.max(0, elapsedSeconds) : Infinity;

    return services.map(service => {
      const item = data?.checks.find(check => check.service === service);
      if (!item) {
        return {
          service, status: "unavailable", observed_at: null,
          age_seconds: null, application_count: null,
          http_status: null, reason: "report_unavailable"
        };
      }

      const age = (Date.parse(data.served_at) -
        Date.parse(item.observed_at)) / 1000 + elapsed;
      const stale = age > 30;

      return {
        service,
        status: stale ? "stale" : item.status,
        observed_at: item.observed_at,
        age_seconds: age,
        application_count: stale ? null : item.application_count,
        http_status: stale ? null : item.http_status,
        reason: stale ? "check_stale" : item.reason
      };
    });
  }

  const api = {services, validate, view};
  if (typeof module !== "undefined") module.exports = api;
  if (typeof window !== "undefined") window.FunctionalOverview = api;
})();
