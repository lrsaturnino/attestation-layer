# Phase 122 ALICE-Grade Self-Consistency

Phase 122 documents and enforces a deterministic requirement contradiction
taxonomy.

## Purpose

Before checking a requirement against a system spec, the system must check
whether the requirement contradicts itself. Deterministic contradictions block
closure. LLM-assisted suggestions are retained as untrusted audit hints and
cannot pass or fail a requirement.

## Contracts

`src/nlreq/requirement_self_consistency.py` defines:

- `RequirementContradictionTaxonomy`
- `RequirementContradictionTaxonomyEntry`
- `UntrustedContradictionSuggestion`
- `build_requirement_contradiction_taxonomy`
- `check_requirement_self_consistency`

`RequirementSelfConsistencyResult` records:

- taxonomy version;
- checked taxonomy codes;
- deterministic contradictions;
- untrusted suggestions;
- backend response when executed.

## Taxonomy

The current taxonomy version is `alice-style-0.1`.

Blocking contradiction classes include:

- direct opposite predicates;
- impossible literal comparisons;
- mutually exclusive states;
- overlapping opposite obligations;
- temporal impossibility;
- numeric bound conflict;
- duplicate obligation conflict;
- backend counterexample.

## Untrusted Suggestions

Untrusted suggestions record producer, message, suggested type, and optional
source spans. They never affect `status`.

## Exit Criteria

This phase exits when:

- deterministic contradiction classes are documented and emitted;
- supported contradictions block before backend dispatch;
- backend counterexamples map to contradiction results;
- untrusted suggestions are preserved but non-blocking;
- tests cover taxonomy exposure and non-blocking suggestions.
