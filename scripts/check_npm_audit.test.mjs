import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import { checkAudit } from "./check_npm_audit.mjs";

const baseline = JSON.parse(fs.readFileSync(new URL(
  "../docs/security/frontend-development-audit.json", import.meta.url)));
const lock = JSON.parse(fs.readFileSync(new URL("../frontend/package-lock.json", import.meta.url)));
const report = vulnerabilities => ({
  vulnerabilities, metadata: { vulnerabilities: { total: Object.keys(vulnerabilities).length } },
});
function input() {
  return structuredClone({
    all: report(structuredClone(baseline.vulnerabilities)), production: report({}), baseline, lock,
    hashes: { ...baseline.sha256 },
  });
}

test("accepts only the reviewed development graph with explicit risk output", () => {
  assert.match(checkAudit(input()), /ACCEPTED DEVELOPMENT RISK.*production audit: zero findings/);
});
test("a clean audit needs no risk acceptance", () => {
  const value = input();
  value.all = report({});
  assert.match(checkAudit(value), /no findings/);
});

for (const [name, mutate] of [
  ["production findings", value => { value.production = value.all; }],
  ["changed package manifest", value => { value.hashes["package.json"] = "changed"; }],
  ["changed lock", value => { value.hashes["package-lock.json"] = "changed"; }],
  ["new advisory", value => { value.all.vulnerabilities.braces.via.push({ source: 999 }); }],
  ["severity escalation", value => { value.all.vulnerabilities.braces.severity = "critical"; }],
  ["runtime dependency paths", value => { value.lock.packages["node_modules/braces"].dev = false; }],
  ["npm error payloads", value => { value.all.error = { code: "E503" }; }],
  ["new dependency", value => { value.all.vulnerabilities.unknown = value.all.vulnerabilities.braces; value.all.metadata.vulnerabilities.total++; }],
  ["missing audit data", value => { delete value.production.metadata; }],
  ["inconsistent report counts", value => { value.all.metadata.vulnerabilities.total = 0; }],
]) {
  test(`rejects ${name}`, () => {
    const value = input();
    mutate(value);
    assert.throws(() => checkAudit(value));
  });
}
