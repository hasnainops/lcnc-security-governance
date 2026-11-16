const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { parseFields, validateCredential } = require("../governance-portal/owner-context.js");

test("field descriptions preserve schema and reject inconsistent definitions", () => {
  assert.deepEqual(parseFields("request_id: Purchase request ID\namount: Purchase amount", "declared_schema"), [
    { name: "request_id", description: "Purchase request ID" }, { name: "amount", description: "Purchase amount" }
  ]);
  assert.throws(() => parseFields("amount: One\nAmount: Two", "declared_schema"));
  assert.throws(() => parseFields("password=actual-value", "declared_schema"));
  assert.throws(() => parseFields("", "declared_schema"));
  assert.deepEqual(parseFields("", "no_data_fields"), []);
});

test("credential validation binds the selected application and expiry", () => {
  const credential = { application_id: "app-1", token: "lo1_" + "t".repeat(43), expires_at: new Date(Date.now() + 60000).toISOString() };
  assert.equal(validateCredential(credential, "app-1"), credential);
  assert.throws(() => validateCredential(credential, "app-2"));
  assert.throws(() => validateCredential({ ...credential, expires_at: "2000-01-01" }, "app-1"));
  assert.throws(() => validateCredential({ ...credential, token: "invalid" }, "app-1"));
});

test("the governance summary withholds a stored suggestion when evidence is stale", () => {
  const source = fs.readFileSync(require.resolve("../governance-portal/app.js"), "utf8");
  const start = source.indexOf("function classificationCard(");
  const end = source.indexOf("function renderV2Summary(", start);
  const card = vm.runInNewContext(source.slice(start, end) + "\nclassificationCard", {
    renderEvidenceCard: (...args) => args,
    displayPercent: value => String(value)
  });
  assert.equal(card({ ml_classification_status: "assessed", suggested_classification: "internal", confidence: .8 })[1], "internal");
  assert.equal(card({ ml_classification_status: "stale", suggested_classification: "public" })[1], "stale");
  assert.equal(card(null)[1], "Current evidence unavailable");
});
