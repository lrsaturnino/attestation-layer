# Phase 144 - Cross-Language Causal Proof Closure

## Status

Implemented.

## Purpose

Close requirements that span more than one language, runtime, or adapter as one
proof object without hiding per-adapter evidence or causal trace gaps.

## Implementation

Primary module:

- `src/nlreq/cross_language.py`

Primary artifacts:

- `CrossLanguageProofObjectV2`
- `CrossLanguageEvidenceSliceV2`
- `AdapterEvidenceReference`
- `CausalTraceLinkV2`

Schema:

- `schemas/cross-language-proof-object-v2.schema.json`

## Contract

The v2 proof object records:

- the base proof id and requirement id;
- one evidence slice per source adapter;
- source language, runtime, modules, and trace ids for each slice;
- retained evidence artifact hashes, producer ids, evidence labels, and replay
  bundle hashes;
- causal links between trace events from different adapters;
- explicit blockers for open proof objects, insufficient language diversity,
  missing adapter evidence, missing replay bundles, and broken causal links.

Closure requires:

- the base proof object is closed;
- at least two source languages are represented;
- every required adapter has an evidence slice;
- every adapter slice has retained evidence;
- adapter evidence that participates in closure has a replay bundle hash;
- required causal links resolve to retained trace events.

## Failure Behavior

- Open base proof: `proof` blocker and `unknown` result.
- Single-language evidence: `language_diversity` blocker.
- Missing required adapter: `adapter_evidence` blocker.
- Missing retained evidence: `adapter_evidence` blocker.
- Missing replay bundle hash: `replay_bundle` blocker.
- Missing source or target event: `trace_link` blocker.

## Verification

`tests/test_milestone_group14.py` verifies that a Python/Solidity causal trace
can close as one accepted proof object and that a missing target trace event
blocks closure.
