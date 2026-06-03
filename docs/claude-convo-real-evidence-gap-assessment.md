# Claude Conversation Real-Evidence Gap Assessment

## Status

Implemented for contract coverage. Release evidence remains blocked until real
retained artifacts are supplied.

## Target From `docs/claude-convo.md`

The Claude conversation describes a requirement gate with this shape:

```text
NL requirement
-> controlled formal claim
-> self-consistency check
-> checked against existing formal system spec S
-> affected code and traces grounded
-> closure or structured refusal
```

The important property is not that the system has artifact names. The important
property is that downstream action is impossible unless every premise closes, and
that ambiguous, unsupported, stale, uncovered, contradicted, timed-out, or
non-replayable evidence produces refusal instead of acceptance.

## Current Alignment

Phases 151-192 now add a single schema-backed real-evidence contract over the
final roadmap:

- every phase has a spec and ADR;
- every phase has required artifact types;
- phase reports block missing, scaffold, blocked, unreviewed, or non-replayable
  evidence;
- milestone reports aggregate phases 15 through 20;
- the Claude-conversation gap assessment computes how close the supplied phase
  evidence is to the target claim;
- a follow-up plan is required whenever important phase evidence is still
  missing.

## Remaining Important Gaps

The code can now represent and enforce the required evidence, but the repository
does not yet contain real release-grade external inputs for:

- a large labeled semantic translation corpus with measured false acceptance and
  false refusal;
- retained Apalache and TLC runs over non-toy reviewed TLA+ specs;
- a non-toy brownfield demo with accepted and refused requirements;
- public benchmark reproduction by an external reviewer;
- red-team findings and mitigation records;
- beta pilot evidence;
- signed final release bundle publication.

These gaps are intentionally release blockers. They should not be satisfied with
fixtures or generated placeholder reports.

## Assessment

The implementation is close to the Claude target in architecture and enforcement
surface. It is not yet publishable as the full real-evidence claim until the
operational evidence in
`docs/operational-real-evidence-gap-closure-plan.md` is produced and the
phase/milestone reports pass against those artifacts.
