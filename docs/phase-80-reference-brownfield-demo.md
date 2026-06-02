# Phase 80 - Reference Brownfield Demo

## Status

Implemented.

## Purpose

Provide a reproducible brownfield demonstration contract for the conclusion
release. The demo must show both a requirement that closes and a requirement
that refuses or blocks with evidence.

Synthetic unit fixtures are useful for development, but a conclusion release
needs a public artifact that exercises real code, reviewed specs, runtime
traces, commands, and gate reports together.

## Scope

The reference demo manifest records:

- source root;
- accepted and refused controlled requirements;
- expected gate report paths;
- reviewed system specs;
- trace artifacts;
- commands needed to reproduce the demo;
- reproducibility notes.

The report validates artifact presence and, when expected report paths are
declared, verifies that actual report decisions match expected decisions.

## Data Contracts

Implementation module: `nlreq.reference_demo`.

Schemas:

- `schemas/reference-demo-manifest.schema.json`
- `schemas/reference-demo-report.schema.json`

Primary models:

- `ReferenceDemoManifest`
- `ReferenceDemoRequirement`
- `ReferenceDemoDecisionCheck`
- `ReferenceDemoReport`

Important report fields:

- `missing_artifacts`: required paths absent from the project root.
- `has_accept_and_refuse`: whether the manifest includes both outcome classes.
- `decision_checks`: expected-vs-actual decision checks for report artifacts.
- `decision_mismatches`: requirements whose actual decision differs.
- `unchecked_reports`: expected report artifacts that could not be checked.
- `command_count`: number of declared reproduction commands.

## API And CLI

Core function:

- `build_reference_demo_report(manifest, existing_paths, actual_decisions_by_requirement=None)`

CLI:

```bash
uv run nlreq reference-demo-check demo/manifest.json --project-root . \
  --out /tmp/reference-demo-report.json
```

The CLI resolves manifest paths under `--project-root` and extracts decisions
from expected report artifacts when present.

## Invariants

- A non-empty demo must include both accepted and refused requirements.
- Missing source, spec, trace, controlled-text, or expected report artifacts
  block reproducibility.
- Expected report decisions must match actual report decisions when report paths
  are declared.
- Reproduction commands are release-certification evidence; a demo report with
  zero commands cannot certify the conclusion release.
- Presence checks do not imply that formal evidence is valid. They only prove
  that the demo artifact set is reproducible enough for certification.

## Verification

`tests/test_milestone_group7.py` verifies successful demo reproduction,
decision mismatch blocking, missing-artifact blocking, and command-count
propagation into certification.

## Exit Criteria

- Demo manifests require both positive and negative requirement outcomes.
- Missing artifacts and decision mismatches are explicit blockers.
- Demo reports expose enough metadata for conclusion certification.
- The reference demo can be rerun from declared commands and checked artifacts.
