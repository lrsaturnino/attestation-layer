# ADR 0025: DSL v2 Grammar And Refusal Taxonomy

## Status

Proposed

## Context

The Phase-0 controlled-language parser accepts one narrow pattern and lowers it
to flat `ir_version: "0.1"`. Phase 19 added compositional `0.2` IR, so the input
surface can become richer without flattening away temporal, numeric, and
multi-premise structure.

The roadmap requires DSL v2 before translator and drafting work. A deterministic
controlled grammar is the trust anchor; LLMs may draft later, but parser output
must remain deterministic and reviewable.

## Decision

Add DSL v2 as a separate parser and grammar.

DSL v2 produces `RequirementIRV2` directly. It does not replace the existing
Phase-0 parser or package builder.

The first grammar supports:

- universal scope: `For every <entity>:`;
- premise block introduced by `when`;
- conjunction with `and`;
- authorization and confirmation predicates;
- numeric `<=` and `>=` comparisons;
- action obligation introduced by `then <action> must`;
- bounded event obligations: `emit <event> within <number> <unit>`;
- state floor/ceiling obligations: `keep <state> >= <bound>`.

Refusals are deterministic. Unsupported or malformed input returns a DSL v2
parse diagnostic that names the failure class and location when available. The
parser must not reinterpret unsupported prose as best-effort semantics.

## Consequences

The project gains a controlled input surface for multi-premise and bounded
temporal requirements while preserving all existing `0.1` workflows.

The tradeoff is limited language coverage. That is intentional. Unsupported
requirements should be made explicit and expanded deliberately in later grammar
versions rather than inferred.
