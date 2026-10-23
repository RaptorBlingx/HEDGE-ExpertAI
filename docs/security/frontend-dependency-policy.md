# Frontend dependency security policy

This policy supersedes the temporary SCRUM-58 npm exception. On 19 October 2026,
the sole maintainer accepted the Store integration, cancelled the separate
remediation task and requested a durable policy without a calendar-triggered CI
failure. Historical SCRUM-58 acceptance/advisory records remain unchanged as history;
neither their expiry nor their remediation reference drives the current gate.
No Jira task is required or created by this policy.

## Current decision

Vitest is updated from 4.1.10 to 4.1.12. Targeted compatible development-transitive
updates cover baseline-browser-mapping, browserslist, nanoid and source-map-js and
their resolved dependencies. All changed resolved package versions are development
only; production dependencies/versions remain unchanged. The final full audit has
**5 high and 1 moderate** findings, down from 8 high and 4 moderate. Production
has **zero findings**. Raw full audit still exits 1; it is not represented as clean.

The remaining graph is Tailwind 3.4.19 → chokidar/fast-glob/micromatch/braces and
postcss-selector-parser. npm offers a Tailwind 4 major migration for the remaining
findings rather than a compatible complete repair. That UI tooling migration is
outside this accepted Store integration. These are pattern/selector-processing
resource-exhaustion risks in build/dev tooling. Build inputs and configuration must
remain trusted; do not expose development servers to untrusted networks. This risk
acceptance does not imply that running a build on hostile source is safe.

`frontend-development-audit.json` records the exact reviewed advisory objects and
manifest hashes. The repository gate accepts only that development graph, on any
branch, without an expiry date or a cancelled Jira prerequisite. Every run still:

- Collects and retains full and production npm audit JSON and stderr.
- Fails on npm errors or malformed/inconsistent reports.
- Rejects every production finding, including moderate or low severity.
- Requires exact manifest hashes and advisory objects, development-only affected
  lockfile paths and only the reviewed moderate/high severities.
- Rejects new/changed advisories, escalations and graph changes until reviewed.

A completely clean audit passes without acceptance. Changes to the dependency
manifests or the remaining findings require maintainer review and deliberate
baseline regeneration, never automatic acceptance from CI. Remove the baseline
when the graph is clean. This is explicit ongoing risk acceptance, not remediation
or a silent downgrade to a production-only audit.

The CI workflow, backend audits, licence checks, history secret scan, source scan,
SBOM, production audit and other protections remain intact. This baseline applies
only to the npm checker; it does not suppress other scanners or guarantee their
remote results.
