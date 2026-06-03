# Phase 127 - Real S And R TLA Composition

## Status

Implemented.

## Purpose

Compose reviewed system spec `S` with requirement claim `R` into
backend-checkable TLA artifacts and report the exact evidence boundary.

## Implementation

Primary modules:

- `src/nlreq/system_checker.py`
- `src/nlreq/system_composition.py`

Schemas:

- `schemas/system-consistency-result.schema.json`
- `schemas/s-and-r-composition-report.schema.json`

CLI:

```bash
uv run nlreq solver-system-consistency-check \
  --requirement-ir requirement.ir.json \
  --lowered lowered.json \
  --registry registry.json \
  --impact impact.json \
  --artifact-dir artifacts

uv run nlreq s-and-r-composition \
  --requirement-ir requirement.ir.json \
  --lowered lowered.json \
  --registry registry.json \
  --impact impact.json \
  --system-consistency solver-system-result.json \
  --out s-and-r-composition.json
```

## Contracts

- Only fresh reviewed specs can enter solver-backed composition.
- Stale, missing, draft, or unreviewed specs block composition before backend
  execution.
- Composed reports retain requirement hash, lowered artifact hash, impact hash,
  reviewed spec hashes, backend result hash, and generated TLA/config artifact
  hashes when available.
- Namespace policy is explicit in the report.
- Existing requirement property names remain visible:
  `RequirementHolds`, `SystemSpecAssumptions`, and `SystemAndRequirement`.

## Outcomes

Composition can return:

- `valid`
- `counterexample`
- `timeout`
- `unsupported`
- `invalid`

Only `valid` with acceptable evidence can support closure. The report itself
does not upgrade bounded evidence into proof.

## Verification

`tests/test_milestone_group11.py` runs a solver-backed composition with a local
fixture command and verifies composed artifact references, preserved invariant
names, and blockers for stale specs.
