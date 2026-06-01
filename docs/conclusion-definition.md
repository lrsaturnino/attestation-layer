# Conclusion Definition

The conclusion release target is a closed requirement gate:

```text
human requirement
-> approved controlled requirement
-> compositional IR candidate
-> self-consistency result
-> system consistency result against reviewed S
-> fresh code/spec/trace evidence
-> closed proof object
-> downstream action allowed
```

The gate must preserve the human's original intent, refuse silent semantic
rewrites, label evidence precisely, and make every refusal actionable.

## Release Bars

Alpha requires approved controlled intake, deterministic IR, explicit refusal
codes, review records, and bounded evidence labels only.

Beta requires the alpha bar plus real formal backend execution, system
consistency, trace grounding, and benchmark tracking.

Conclusion requires the beta bar plus cross-language closure, signed retained
evidence, public benchmark accountability, threat-model review, and release
certification.

## Evidence Discipline

`BOUNDED_CHECKED` means bounded model checking with recorded bounds. It is not
an inductive proof.

`PROVEN_INDUCTIVE` can only be emitted by a registered proof-producing backend.
No group 1 phase can emit it.

`TRACE_VALIDATED` means observed traces were replayed or checked. It is not a
theorem.

`REVIEWED` means a human approval is bound to artifact hashes and becomes stale
when those hashes change.

## Machine Contract

The schema-backed definition artifact is
`docs/conclusion-definition.artifact.json`. The machine-readable gap checklist
is `docs/conclusion-gap-checklist.json` and is validated by:

```bash
uv run nlreq conclusion-gap-check docs/conclusion-gap-checklist.json
```
