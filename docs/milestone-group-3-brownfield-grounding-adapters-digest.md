# Milestone Group 3 Brownfield Grounding And Adapters Digest

Milestone group 3 is roadmap Step 3, covering phases 62 through 72. It starts
after Safe Requirement Intake and Formal Closure Core can produce an approved
requirement `R`, explicit self-consistency outcomes, formal backend evidence,
and real `S and R` compatibility results.

## Objective

Group 3 connects the formal core to real code and runtime behavior. The output
should be a closure decision that knows which modules are affected, whether
their reviewed specs are fresh, whether observed traces align with the
requirement, and whether evidence across multiple programming ecosystems can be
aggregated into one proof object.

## Phase Digest

| Phase | Focus | Core Dependency From Groups 1-2 |
|---:|---|---|
| 62 | Specula-style extraction runner | Provenance graph, refusal surface, formal artifact boundary |
| 63 | Code-to-spec manifest | Impact analysis, system spec registry, `S and R` composition |
| 64 | Spec freshness lockfile | Gap checklist discipline, spec drift semantics |
| 65 | Runtime trace extraction SDK | Normalized trace schema, trace replay grounding |
| 66 | Trace normalization | Product refusal codes, counterexample normalization |
| 67 | Solidity adapter | Adapter boundary, event/state correspondence DSL v3 class |
| 68 | Go adapter | Adapter conformance, contextual source impact |
| 69 | TypeScript adapter | JavaScript adapter lessons, package/source split |
| 70 | Rust or Java adapter | Compiled ecosystem conformance pressure test |
| 71 | Adapter certification suite | Cross-adapter conformance and producer validation |
| 72 | Cross-language proof object | Proof-level evidence boundary, backend agreement reports |

## Required Shape

- Candidate specs generated from code are draft artifacts only. They must not
  satisfy freshness or reviewed-spec gates until a human review binds them by
  hash.
- The code-to-spec manifest must map affected modules, source files, specs,
  trace producers, adapter IDs, and freshness hashes in one auditable artifact.
- Freshness must be reproducible from source, spec, manifest, and lockfile
  content hashes.
- Runtime traces must be emitted by registered producers and normalized before
  trace replay consumes them.
- Production adapters must expose the same manifest, symbol resolution, call
  graph, trace extraction, and conformance contracts as existing source
  adapters.
- Cross-language closure must aggregate per-adapter evidence into one proof
  object without hiding adapter-specific unsupported, timeout, drift, or trace
  mismatch outcomes.

## Handoff From Groups 1-2

Group 1 supplies approved controlled requirements, selected/agreed translation
candidates, source-span provenance, review state, and actionable refusal
reports. Group 2 supplies explicit formal outcomes and the evidence boundary
that prevents bounded checks from being called proofs. Group 3 must preserve
those trust boundaries while adding code/spec/trace evidence.

## Main Risks

- Treating extracted candidate specs as reviewed specs.
- Passing closure with stale specs or stale trace fixtures.
- Creating adapter-specific evidence shapes that cannot be compared.
- Letting one language adapter mask another adapter's unsupported result.
- Overfitting trace normalization to a single runtime event format.
- Emitting cross-language proof objects that lose per-artifact hashes.

## Non-Goals

- Full automatic code-to-spec correctness.
- Support for every programming language.
- Inferring production runtime traces from tests alone.
- Replacing reviewer approval for generated specs.
- Collapsing all ecosystem semantics into one lowest-common-denominator trace.

## Exit Readiness Checklist

- Each phase has an ADR and spec describing trust boundaries and artifacts.
- At least three materially different adapters pass certification.
- At least one adapter is event/transaction oriented.
- At least one adapter targets a statically typed compiled/runtime ecosystem.
- Cross-language proof objects retain per-adapter evidence hashes and blockers.
- Benchmark cases cover stale specs, trace mismatch, adapter disagreement, and
  multi-language closure.
