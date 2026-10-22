const test = require("node:test");
const assert = require("node:assert/strict");
const {services, validate, view} =
  require("../governance-portal/functional-overview.js");

function fixture() {
  return {
    schema_version: 1,
    source: "internal_http_probes",
    served_at: "2026-10-21T10:00:01Z",
    stale_after_seconds: 30,
    checks: services.map(service => ({
      service,
      check: service === "opa" ? "policy_decisions" : "inventory_read",
      status: "passed",
      observed_at: "2026-10-21T10:00:00Z",
      duration_ms: 12,
      http_status: 200,
      application_count: service === "opa" ? null : 14,
      ...(service === "opa" ? {cases_passed: 6, cases_total: 6} : {}),
      reason: null
    }))
  };
}

test("fresh successful checks expose counts", () => {
  const rows = view(validate(fixture()));
  assert.equal(rows.length, 5);
  const inventory = rows.filter(row => row.service !== "opa");
  assert.equal(inventory.length, 4);
  assert.ok(inventory.every(row =>
    row.status === "passed" && row.application_count === 14));
  const opa = rows.find(row => row.service === "opa");
  assert.equal(opa.status, "passed");
  assert.equal(opa.check, "policy_decisions");
  assert.equal(opa.application_count, null);
  assert.equal(opa.cases_passed, 6);
  assert.equal(opa.cases_total, 6);
});

test("failed inventory remains failed independently of Docker health", () => {
  const data = fixture();
  Object.assign(data.checks[0], {
    status: "failed", http_status: 500,
    application_count: null, reason: "http_error",
    docker_health: "healthy"
  });
  const row = view(validate(data))[0];
  assert.equal(row.status, "failed");
  assert.equal(row.http_status, 500);
  assert.equal(row.application_count, null);
});

test("browser aging makes old results stale and withholds counts", () => {
  const data = validate(fixture());
  assert.equal(view(data, 29)[0].status, "passed");
  const row = view(data, 30)[0];
  assert.equal(row.status, "stale");
  assert.equal(row.application_count, null);
  assert.equal(row.http_status, null);
});

test("missing report produces unavailable results", () => {
  const rows = view(null);
  assert.ok(rows.every(row =>
    row.status === "unavailable" && row.application_count === null));
});

test("empty inventory is a valid successful result", () => {
  const data = fixture();
  data.checks[0].application_count = 0;
  assert.equal(view(validate(data))[0].application_count, 0);
});

test("each check ages from its own observation timestamp", () => {
  const data = fixture();
  data.checks[0].observed_at = "2026-10-21T09:59:00Z";
  const rows = view(validate(data));
  assert.equal(rows[0].status, "stale");
  assert.equal(rows[1].status, "passed");
});

test("invalid catalogs, timing and contradictory results are rejected", () => {
  for (const mutate of [
    d => d.checks.pop(),
    d => d.checks[0].service = d.checks[1].service,
    d => d.checks[0].service = "unexpected",
    d => d.served_at = "invalid",
    d => d.checks[0].observed_at = "2026-10-21T10:01:00Z",
    d => d.checks[0].duration_ms = -1,
    d => d.checks[0].http_status = 500,
    d => d.checks[0].application_count = -1,
    d => d.checks[0].status = "failed",
    d => d.checks[0].reason = "unexpected"
  ]) {
    const data = fixture();
    mutate(data);
    assert.throws(() => validate(data));
  }
});


test("OPA rejects contradictory evidence", () => {
  for (const changes of [
    {cases_passed: 5},
    {cases_passed: 7},
    {cases_passed: -1},
    {cases_passed: 1.5},
    {cases_total: 5},
    {application_count: 14},
    {check: "inventory_read"},
    {status: "failed", reason: "decision_mismatch", cases_passed: 6}
  ]) {
    const data = fixture();
    Object.assign(data.checks.find(row => row.service === "opa"), changes);
    assert.throws(() => validate(data));
  }
});

test("OPA decision mismatch remains failed with HTTP 200", () => {
  const data = fixture();
  Object.assign(data.checks.find(row => row.service === "opa"), {
    status: "failed",
    reason: "decision_mismatch",
    cases_passed: 5
  });
  const row = view(validate(data)).find(row => row.service === "opa");
  assert.equal(row.status, "failed");
  assert.equal(row.http_status, 200);
  assert.equal(row.application_count, null);
  assert.equal(row.cases_passed, 5);
});

test("stale OPA evidence withholds case counts", () => {
  const row = view(validate(fixture()), 30)
    .find(row => row.service === "opa");
  assert.equal(row.status, "stale");
  assert.equal(row.cases_passed, null);
  assert.equal(row.cases_total, null);
  assert.equal(row.http_status, null);
});

test("missing OPA report has no successful case evidence", () => {
  const row = view(null).find(row => row.service === "opa");
  assert.equal(row.status, "unavailable");
  assert.equal(row.check, "policy_decisions");
  assert.equal(row.cases_passed, null);
  assert.equal(row.cases_total, null);
});
