#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.argv[2] || "frontend/node_modules");
const outputIndex = process.argv.indexOf("--output");
const output = outputIndex >= 0 ? process.argv[outputIndex + 1] : null;
const allowed = new Set([
  "0BSD",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "BlueOak-1.0.0",
  "CC-BY-4.0",
  "CC0-1.0",
  "ISC",
  "MIT",
  "MIT-0",
  "MPL-2.0",
]);
const packages = [];
const visited = new Set();

function scanNodeModules(directory) {
  if (!fs.existsSync(directory)) return;
  const realDirectory = fs.realpathSync(directory);
  if (visited.has(realDirectory)) return;
  visited.add(realDirectory);

  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
    const entryPath = path.join(directory, entry.name);
    if (entry.name.startsWith("@")) {
      for (const scopedEntry of fs.readdirSync(entryPath, { withFileTypes: true })) {
        if (scopedEntry.isDirectory()) scanPackage(path.join(entryPath, scopedEntry.name));
      }
    } else {
      scanPackage(entryPath);
    }
  }
}

function scanPackage(packageDirectory) {
  const manifestPath = path.join(packageDirectory, "package.json");
  if (!fs.existsSync(manifestPath)) return;
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const license = typeof manifest.license === "string" ? manifest.license : "UNKNOWN";
  packages.push({ name: manifest.name, version: manifest.version, license });
  scanNodeModules(path.join(packageDirectory, "node_modules"));
}

scanNodeModules(root);
packages.sort((left, right) => `${left.name}@${left.version}`.localeCompare(`${right.name}@${right.version}`));
const violations = packages.filter(({ license }) => !allowed.has(license));
if (output) fs.writeFileSync(output, `${JSON.stringify(packages, null, 2)}\n`);
if (violations.length) {
  for (const item of violations) {
    console.error(`disallowed or unknown licence: ${item.name}@${item.version}: ${item.license}`);
  }
  process.exit(1);
}
console.log(`validated ${packages.length} npm packages against the reviewed licence allowlist`);
