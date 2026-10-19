#!/usr/bin/env node
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function validateReport(report) {
  assert.ok(report && !report.error, "npm audit returned an error");
  assert.ok(report.vulnerabilities && report.metadata?.vulnerabilities,
    "npm audit did not return vulnerability data");
  assert.equal(report.metadata.vulnerabilities.total,
    Object.keys(report.vulnerabilities).length, "inconsistent audit report");
}

export function checkAudit({ all, production, exception, lock, hashes, branch, now }) {
  validateReport(all);
  validateReport(production);
  assert.equal(production.metadata.vulnerabilities.total, 0,
    "production vulnerabilities are never exempt");
  if (all.metadata.vulnerabilities.total === 0) return "npm audit: no findings";
  assert.ok(exception.branches.includes(branch), "exception does not apply to this branch");
  assert.ok(Number.isFinite(Date.parse(exception.expires)) && now < Date.parse(exception.expires),
    "development dependency exception expired");
  assert.deepEqual(hashes, exception.sha256, "dependency manifests changed; exception invalid");
  assert.deepEqual(all.vulnerabilities, exception.vulnerabilities,
    "audit findings changed; maintainer review required");
  for (const finding of Object.values(all.vulnerabilities)) {
    assert.ok(["moderate", "high"].includes(finding.severity), "severity outside exception");
    assert.ok(finding.nodes?.length, "missing affected dependency paths");
    for (const node of finding.nodes) {
      assert.equal(lock.packages[node]?.dev, true, `${node} is not development-only`);
    }
  }
  return `EXCEPTION ${exception.issue}: unchanged development-only findings accepted until ` +
    `${exception.expires}; remediation ${exception.remediation}. Production audit: zero findings.`;
}

function audit(frontend, output, name, args) {
  const result = spawnSync("npm", ["audit", "--json", ...args], {
    cwd: frontend, encoding: "utf8", timeout: 120000,
  });
  fs.writeFileSync(path.join(output, `${name}.json`), result.stdout || "");
  fs.writeFileSync(path.join(output, `${name}.stderr`), result.stderr || "");
  assert.ok(!result.error && [0, 1].includes(result.status),
    `npm audit failed: ${result.error || result.status}`);
  const report = JSON.parse(result.stdout);
  validateReport(report);
  assert.equal(result.status, report.metadata.vulnerabilities.total ? 1 : 0,
    "unexpected npm audit exit status");
  return report;
}

function main() {
  const frontend = path.join(root, "frontend");
  const output = path.join(frontend, "npm-audit-reports");
  fs.mkdirSync(output, { recursive: true });
  const all = audit(frontend, output, "all", []);
  const production = audit(frontend, output, "production", ["--omit=dev"]);
  const hashes = Object.fromEntries(["package.json", "package-lock.json"].map(name => [
    name, createHash("sha256").update(fs.readFileSync(path.join(frontend, name))).digest("hex"),
  ]));
  const branch = process.env.GITHUB_HEAD_REF || process.env.GITHUB_REF_NAME ||
    spawnSync("git", ["branch", "--show-current"], { cwd: root, encoding: "utf8" }).stdout?.trim();
  console.log(checkAudit({
    all, production, hashes, branch, now: Date.now(),
    lock: JSON.parse(fs.readFileSync(path.join(frontend, "package-lock.json"))),
    exception: JSON.parse(fs.readFileSync(path.join(root, "docs/security/SCRUM-58-npm-exception.json"))),
  }));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(); } catch (error) {
    console.error(`npm security gate FAILED: ${error.message}`);
    process.exitCode = 1;
  }
}
