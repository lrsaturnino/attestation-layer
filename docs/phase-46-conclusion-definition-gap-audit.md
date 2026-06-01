# Phase 46 Conclusion Definition And Gap Audit

Phase 46 freezes the finish line for the conclusion roadmap.

## Scope

- Publish a human-readable conclusion definition.
- Publish a schema-backed conclusion definition artifact.
- Publish a machine-readable gap checklist.
- Enforce group-1 phase and ADR numbering.
- Define alpha, beta, and conclusion release bars.
- Define evidence-label discipline for each bar.

## Contracts

`src/nlreq/conclusion.py` owns the contracts:

- `ConclusionDefinition`
- `ReleaseBar`
- `ConclusionGapChecklist`
- `ConclusionGapCheckReport`

The CLI emits and validates artifacts:

```bash
uv run nlreq conclusion-definition --out docs/conclusion-definition.artifact.json
uv run nlreq conclusion-gap-checklist --out docs/conclusion-gap-checklist.json
uv run nlreq conclusion-gap-check docs/conclusion-gap-checklist.json
```

## Invariants

- Group-1 phase references must be between 46 and 55.
- ADR numbering must map phase 46 to ADR 0055 and phase 55 to ADR 0064.
- `PROVEN_INDUCTIVE` cannot be claimed by group 1.
- Missing work must have an owner phase.

## Exit Criteria

The generated checklist validates, and the roadmap, phase specs, and ADRs agree
on group-1 numbering.

## Implementation Spec

Inputs:

- `docs/nl-attestation-conclusion-roadmap.md` as the authoritative phase and
  ADR sequence.
- Existing implementation artifacts from phases 0-45.
- The conclusion target statement and release bars defined for this roadmap.

Outputs:

- A human-readable conclusion definition in `docs/conclusion-definition.md`.
- A schema-backed artifact emitted by `nlreq conclusion-definition`.
- A gap checklist emitted by `nlreq conclusion-gap-checklist`.
- A validation report emitted by `nlreq conclusion-gap-check`.

Validation behavior:

- `ConclusionGapChecklist` rejects owner phases outside the conclusion roadmap.
- Each phase-to-ADR pair is checked by formula: phase 46 maps to ADR 0055,
  phase 47 maps to ADR 0056, and so on.
- The group-1 validation path requires one owner item for every phase from 46
  through 55.
- Release bars distinguish alpha, beta, and conclusion release claims. A later
  phase can add stricter bars, but it cannot weaken the evidence-label policy
  without a new ADR.

Failure modes:

- Unknown phase references produce a failed `ConclusionGapCheckReport`.
- ADR numbering drift produces a failed report and a diagnostic string naming
  the expected ADR.
- Missing group-1 owner phases are explicit blockers.

Tests:

- `tests/test_milestone_group1.py` verifies the default checklist, phase
  coverage, ADR numbering, and CLI JSON output.

Out of scope:

- This phase does not implement production formal backends, source extraction,
  or release certification. It only freezes the target and makes remaining
  work auditable.
