import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import { checkAudit } from "./check_npm_audit.mjs";

const exception = JSON.parse(fs.readFileSync(new URL(
  "../docs/security/SCRUM-58-npm-exception.json", import.meta.url)));
const lock = JSON.parse(fs.readFileSync(new URL("../frontend/package-lock.json", import.meta.url)));
const report = vulnerabilities => ({
  vulnerabilities, metadata: { vulnerabilities: { total: Object.keys(vulnerabilities).length } },
});
function input() {
  return structuredClone({
    all: report(structuredClone(exception.vulnerabilities)), production: report({}), exception, lock,
    hashes: { ...exception.sha256 }, branch: "feat/SCRUM-58-suitability-integration",
    now: Date.parse("2026-10-19T12:00:00Z"),
  });
}

test("accepts only the retained development graph, with explicit exception output", () => {
  assert.match(checkAudit(input()), /EXCEPTION SCRUM-58.*SCRUM-60/);
});
test("a clean audit needs no exception", () => {
  const value = input();
  value.all = report({});
  value.now = Date.parse("2027-01-01");
  value.branch = "main";
  assert.match(checkAudit(value), /no findings/);
});

for (const [name, mutate] of [
  ["production findings", value => { value.production = value.all; }],
  ["expiry at the exact deadline", value => { value.now = Date.parse(exception.expires); }],
  ["unrelated branches", value => { value.branch = "perf/prepared-store-discovery"; }],
  ["changed lock", value => { value.hashes["package-lock.json"] = "changed"; }],
  ["new advisory", value => { value.all.vulnerabilities.braces.via.push({ source: 999 }); }],
  ["severity escalation", value => { value.all.vulnerabilities.braces.severity = "critical"; }],
  ["runtime dependency paths", value => { value.lock.packages["node_modules/braces"].dev = false; }],
  ["npm error payloads", value => { value.all.error = { code: "E503" }; }],
  ["missing audit data", value => { delete value.production.metadata; }],
  ["inconsistent report counts", value => { value.all.metadata.vulnerabilities.total = 0; }],
]) {
  test(`rejects ${name}`, () => {
    const value = input();
    mutate(value);
    assert.throws(() => checkAudit(value));
  });
}
