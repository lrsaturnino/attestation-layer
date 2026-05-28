# ADR 0015: Phase 13 TLA+ Model-Checking Adapter

## Status

Proposed

## Context

The roadmap through Phase 12 prioritizes broad brownfield usefulness before
formal methods:

- Phase 10: command/test-runner evidence for existing checks;
- Phase 11: runtime trace validation for observed behavior;
- Phase 12: adapter registry and routing so multiple evidence sources can
  coexist safely.

After those phases, the next high-value gap is design-level state-machine
verification. The core model already reserves `bounded_temporal` claims,
`BOUNDED_CHECKED`, and `PROVEN_INDUCTIVE`, but no implemented backend currently
produces those evidence levels. TLA+ is the right first formal/model-checking
target because it is designed for system-level behavior, protocols,
concurrency, ordering, and state transitions.

This phase should not try to generate trustworthy TLA+ from arbitrary natural
language. The first useful version should bind reviewed requirements to
reviewed TLA+ modules and configurations, run a model checker, record
counterexamples, and produce conservative evidence.

Specula is a strong reference implementation for the surrounding TLA+ workflow.
It provides methodology and tools for code analysis, TLA+ spec generation, trace
validation, TLC model checking, counterexample analysis, and bug confirmation.
Phase 13 should be compatible with selected Specula artifacts and tools, but it
should not make the whole Specula agentic pipeline the Attestation Layer trust
anchor.

## Decision

Phase 13 will introduce a TLA+/model-checking adapter for reviewed TLA+ specs.

The first adapter will support spec-first or spec-linked workflows:

- bind requirement ids to TLA+ modules, invariants, properties, and configs;
- validate that referenced model files exist and are hash-addressed;
- run a configured model-checking command such as TLC or Apalache;
- parse pass, failure, timeout, and counterexample outcomes;
- emit normalized backend results;
- produce `BOUNDED_CHECKED` evidence only when a bounded model check completes
  successfully under recorded bounds/configuration;
- reserve `PROVEN_INDUCTIVE` for future proof-oriented backends that actually
  establish inductive invariants.

The adapter will record:

- requirement ids,
- TLA+ module paths and hashes,
- config paths and hashes,
- model checker name and version,
- command argv,
- constants and bounds,
- invariant or property names,
- result status,
- timeout and resource limits,
- output hashes or bounded excerpts,
- and counterexample traces when checks fail.

The adapter must not:

- treat unchecked TLA+ syntax as evidence;
- claim proof from bounded model checking;
- hide state-space bounds;
- mutate reviewed requirement packages in place;
- infer a model from arbitrary prose without review;
- treat a Specula-generated model as reviewed merely because Specula produced it;
- treat Specula bug reports as package evidence without normalized backend
  results;
- or let model-checking failures become coder retry payloads without reviewer
  context when the failure indicates a design/specification issue.

## Relationship To Specula

Phase 13 may reuse or interoperate with selected Specula components:

- TLA+ model/checking conventions such as `base.tla`, `MC.tla`, `MC.cfg`, and
  `MC_hunt_*.cfg`;
- TLC launch patterns and bundled TLA+ jars;
- TLC output parsing and counterexample navigation tools;
- trace-validation methodology and trace/debugging tools;
- counterexample classification methodology: invariant too strong, spec
  modeling issue, or real implementation bug;
- and case-study methodology for choosing useful model scope.

Those components are inputs or helpers. The Attestation Layer still owns the
auditable contract:

- reviewed requirement package;
- reviewed TLA+ model/config references;
- model/config hashes;
- checker command, version, bounds, constants, and timeout;
- normalized backend result;
- normalized counterexample artifact;
- evidence object;
- status decision;
- gate reports;
- continuous reports;
- and agent handoff/audit artifacts.

Specula's agent-generated analysis, specs, fixes, bug reports, and reproduction
tests may be useful drafting or investigation artifacts, but they do not satisfy
`BOUNDED_CHECKED` by themselves. Gateable Phase 13 evidence starts only when the
reviewed model/config is checked by a deterministic backend and normalized into
the Attestation Layer evidence model.

## Planned Artifacts

TLA+ binding/config artifact:

```json
{
  "schema_version": "0.1",
  "adapter": "tla",
  "models": [
    {
      "model_id": "authorization-state-machine",
      "requirement_ids": ["REQ-AUTH-001"],
      "module": "specs/models/Authorization.tla",
      "config": "specs/models/Authorization.cfg",
      "checker": "tlc",
      "command": [
        "tlc2.TLC",
        "-config",
        "specs/models/Authorization.cfg",
        "specs/models/Authorization.tla"
      ],
      "properties": ["UnauthorizedRejectedBeforeStateChange"],
      "bounds": {
        "actors": 3,
        "resources": 3,
        "steps": 10
      },
      "requested_evidence": "BOUNDED_CHECKED"
    }
  ]
}
```

Model-checking result artifact:

```json
{
  "schema_version": "0.1",
  "adapter": "tla",
  "model_id": "authorization-state-machine",
  "requirement_ids": ["REQ-AUTH-001"],
  "status": "valid",
  "evidence_level": "BOUNDED_CHECKED",
  "checker": {
    "name": "tlc",
    "version": "..."
  },
  "module_hash": "sha256:...",
  "config_hash": "sha256:...",
  "bounds": {
    "actors": 3,
    "resources": 3,
    "steps": 10
  },
  "checked_properties": ["UnauthorizedRejectedBeforeStateChange"]
}
```

Counterexamples should be normalized so gates, continuous reports, and agent
handoffs can show the failing state/action sequence without depending on raw
checker output.

## Evidence Semantics

The adapter may produce `BOUNDED_CHECKED` when:

- the model checker command completed successfully;
- the checked module, config, constants, and bounds are recorded;
- the requirement id is explicitly linked to the checked property;
- no invariant/property violation was reported within the configured model;
- and the result is bound to reviewed package and model hashes.

The adapter may not produce `PROVEN_INDUCTIVE` unless a future backend performs
an actual inductive proof and records the proof artifact. TLC or bounded
Apalache runs should not be mislabeled as proof.

## Consequences

Phase 13 gives the Attestation Layer its first formal state-machine evidence
path. It is especially useful for critical authorization flows, distributed
protocols, concurrent state transitions, and ordering properties where tests and
traces are not enough.

The tradeoff is methodology cost. TLA+ models are separate artifacts and require
review. That is acceptable because this phase targets high-risk design paths,
not every requirement.
