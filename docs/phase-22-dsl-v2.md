# Phase 22 DSL v2

Phase 22 adds a richer controlled input surface that targets the compositional
IR introduced in Phase 19.

This phase does not replace the Phase-0 parser. It adds a separate DSL v2 parser
so existing flat `0.1` workflows remain stable while new requirements can enter
as `ir_version: "0.2"`.

## Purpose

The phase lets the Attestation Layer say:

```text
A controlled DSL v2 requirement can be parsed deterministically into the
compositional IR, and malformed or unsupported fragments are refused before
translation or backend checks run.
```

It does not say:

```text
Free-form prose can be accepted directly.
LLMs can approve rewrites.
The parsed requirement has been formally lowered or checked.
Source code or system spec S has been analyzed.
```

## Why This Comes After Phase 21

Phase 19 created the compositional IR target. Phase 20 defined the formal backend
edge. Phase 21 defined the source adapter edge. DSL v2 now has a safe target for
richer semantics without smuggling backend or source-language details into the
input grammar.

## Grammar Shape

The first DSL v2 grammar supports a small but useful controlled corpus:

```text
For every redemption:
when wallet is authorized
and deposit is confirmed
and requested_amount <= spendable_balance
then finalize_redemption must emit redemption_finalized within 6 hours
and keep collateral >= reserve_floor.
```

Supported premise fragments:

- `<name> is authorized`;
- `<name> is confirmed`;
- `<name> <= <name>`;
- `<name> >= <name>`.

Supported obligation fragments:

- `emit <event> within <number> <unit>`;
- `keep <state> >= <floor>`;
- `keep <state> <= <ceiling>`.

Unsupported fragments refuse with a DSL v2 parse diagnostic rather than falling
back to prose interpretation.

## CLI Shape

Parse DSL v2 into compositional IR:

```bash
uv run nlreq ir-v2 tests/fixtures/requirements/dsl_v2_redemption.nlreq2 \
  --requirement-id REQ-DSL-V2-001 \
  --title "Redemption finalization is timely and reserve-safe"
```

## Implementation Scope

Phase 22 implementation should include:

- a versioned DSL v2 grammar file;
- deterministic parser to `RequirementIRV2`;
- source spans on parsed semantic nodes;
- refusal diagnostics for malformed or unsupported input;
- fixture coverage for a multi-premise temporal requirement;
- CLI output of canonical `0.2` IR JSON;
- tests proving existing parser/package behavior remains compatible.

## Evidence Semantics

Parsing DSL v2 is not verification.

DSL v2 output may satisfy schema/type validation of a reviewed IR artifact. It
does not satisfy `CONSISTENCY_CHECKED`, `BOUNDED_CHECKED`, or
`PROVEN_INDUCTIVE`.

## Success Criterion

Phase 22 succeeds when:

- a small real-domain DSL v2 corpus parses to compositional IR;
- parser refusals identify malformed or unsupported fragments;
- parsed output validates as `ir_version: "0.2"`;
- source spans and deterministic provenance are present;
- and existing `0.1` parser/package behavior is unchanged.

## Boundary

This phase is not free-form NL drafting, LLM approval, formal lowering, temporal
checking, source impact analysis, system-spec registry, or closure gating.
