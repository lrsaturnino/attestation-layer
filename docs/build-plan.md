# NL Requirement Attestation Layer: General-Purpose Build Plan

> A system-neutral requirements gate for the Attestation Layer: turn precise natural-language requirements into typed, reviewable, machine-checkable specification packages, then route those packages through deterministic checks appropriate to the target system.

---

## 0. Executive Summary

The NL Requirement Attestation Layer is a general-purpose component of the Attestation Layer. It sits before implementation work and turns human intent into a deterministic specification package.

It is not a Solidity tool, a blockchain tool, or a project-specific validator. The core must work for any system that can expose enough structure for symbol binding and evidence collection:

- libraries,
- services,
- smart contracts,
- CLIs,
- distributed systems,
- data pipelines,
- APIs,
- infrastructure-as-code,
- or spec-only systems.

The first implementation should build the system-neutral core:

```text
Controlled requirement
  -> parsed AST
  -> typed IR
  -> symbol-bound IR
  -> verification tasks
  -> evidence object
  -> status decision
  -> implementation-ready spec package
```

Adapters then plug specific ecosystems into the core:

- Python adapter,
- TypeScript adapter,
- Go adapter,
- Solidity adapter,
- Rust adapter,
- TLA+/spec-only adapter,
- or any other adapter that satisfies the interface.

The core product is not "natural language in, proof out." It is:

> controlled requirement in, typed and symbol-bound spec package out, with explicit evidence about what was checked and what remains unverified.

---

## 1. Product Definition

### 1.1 Plain-English Definition

This system is a requirements checker and spec-package generator.

Given a requirement like:

> For every request, if the actor is not authorized for the resource, the operation must be rejected before state changes.

the system emits a deterministic package containing:

- the normalized requirement,
- the formal claim,
- source spans linking claims back to requirement text,
- symbol bindings into the target system,
- assumptions,
- verification tasks,
- evidence,
- refusal or acceptance status,
- and implementation-facing acceptance criteria.

The implementation target is the generated spec package, not ambiguous prose.

### 1.2 What This Is Not

The first implementation is not:

- a general free-form natural-language theorem prover,
- a fully automatic requirements approval system,
- a replacement for human spec review,
- a proof of arbitrary production-code correctness,
- a universal adapter suite,
- or a system that treats LLM output as evidence.

LLMs may draft or propose. Deterministic parsers, schemas, validators, checkers, and review records decide what enters the package.

### 1.3 Scope Boundary

The core must be adapter-neutral.

The core owns:

- controlled-language grammar,
- parser,
- IR schema,
- source-span provenance,
- review workflow,
- evidence taxonomy,
- status decision,
- package layout,
- adapter interface,
- CLI,
- and golden tests.

Adapters own:

- symbol resolution for a target ecosystem,
- static analysis integration,
- trace/test extraction,
- backend-specific task generation,
- and target-specific evidence collection.

---

## 2. Feasibility Position

### 2.1 Feasible Now

The following is feasible for Phase 0:

- A narrow controlled-language grammar.
- Parsing into a deterministic AST.
- A typed, versioned IR.
- Source spans from controlled text to IR nodes.
- A generic symbol table adapter for toy systems.
- A generic verification-task format.
- SMT-backed checks for simple logical/numeric claims.
- A pure status-decision function.
- An implementation-ready package format.
- Golden tests proving deterministic output.

### 2.2 Feasible After Core

The following is feasible after the core exists:

- Python adapter using Python AST, pytest, and Hypothesis.
- TypeScript adapter using the TypeScript compiler API and test traces.
- Go adapter using `gopls`, `go/analysis`, and test/runtime traces.
- Solidity adapter using ecosystem-specific static analysis and transaction traces.
- TLA+/spec-only adapter for systems where the implementation is not the first artifact.
- Model-checking backend integration for hand-written or generated state models.

### 2.3 Not Feasible To Promise In V1

Do not promise:

- free-form NL correctness,
- fully automatic NL-to-formal-spec correctness,
- arbitrary target-language support,
- automatic trustworthy spec extraction from any codebase,
- proof from bounded model checking,
- proof from trace validation,
- or cross-system verification before one adapter is proven.

### 2.4 Evidence Principle

Every result must carry its evidence level.

Supported evidence levels:

- `TYPE_CHECKED`: IR/schema is well formed.
- `CONSISTENCY_CHECKED`: supported claims do not contradict each other.
- `STATICALLY_RESOLVED`: symbols and bindings resolve in the target adapter.
- `SMT_CHECKED`: an SMT query is valid/unsat under declared assumptions.
- `TEST_VALIDATED`: generated or referenced tests pass.
- `TRACE_VALIDATED`: observed traces conform to the requirement model.
- `BOUNDED_CHECKED(k)`: state search found no violation up to bound `k`.
- `PROVEN_INDUCTIVE`: an inductive invariant was actually established.
- `REVIEWED`: a human reviewer approved the package or a specific artifact.

These are not interchangeable. The status decision must preserve the distinction.

---

## 3. System Architecture

The core architecture has seven layers.

```text
Layer 7: Package and Gate Emission
  Writes spec packages, CI reports, PR comments, and handoff artifacts.
  ↑
Layer 6: Status Decision
  Pure function: evidence + required levels + review state -> final status.
  ↑
Layer 5: Evidence Aggregator
  Collects backend results and assigns evidence levels.
  ↑
Layer 4: Verification Dispatcher
  Converts claims into backend tasks and routes them to checks.
  ↑
Layer 3: Adapter Interface and Symbol Binding
  Resolves requirement terms into target-system symbols.
  ↑
Layer 2: Requirement IR
  Typed, deterministic intermediate representation.
  ↑
Layer 1: Controlled Requirement Input
  Restricted grammar plus optional LLM-assisted drafting.
```

Layer 6 must remain pure and unit-testable. It must not write files, call tools, post comments, or mutate state. Layer 7 performs effects after Layer 6 returns a status.

---

## 4. Data Flow

### 4.1 Submit Requirement

The user submits controlled natural language.

Example:

```text
For every operation request:
  if actor is not authorized
  then operation must be rejected before state_change.
```

Vague requirements are refused before translation.

Rejected examples:

- "The system should be secure."
- "The API should handle bad users."
- "State updates should work correctly."

The refusal must say which required part is missing: actor, action, condition, expected result, target state, or scope.

### 4.2 Optional LLM Rewrite

If the user starts from free-form prose, an LLM may suggest a controlled-language rewrite.

That rewrite is not accepted automatically. The package must preserve:

- original free-form text,
- LLM-suggested controlled form,
- approved controlled form,
- diff between original and controlled form,
- model/provider metadata,
- prompt/template version,
- timestamp,
- and explicit approval record.

No parser or verifier runs on an LLM rewrite until the controlled form is explicitly approved.

### 4.3 Parse To AST

The approved controlled form is parsed deterministically.

Example AST:

```json
{
  "kind": "universal_rule",
  "scope": {"entity": "operation_request"},
  "condition": [
    {"op": "not", "predicate": "authorized", "args": ["actor"]}
  ],
  "expected": {
    "action": "operation",
    "result": "rejected",
    "before": "state_change"
  }
}
```

### 4.4 Lower To IR

The AST is lowered into typed IR.

In Phase 0, only deterministic AST-to-IR lowering is accepted automatically. Any LLM-generated IR is marked `NEEDS_REVIEW`.

### 4.5 Bind Symbols Through Adapter

The core asks an adapter to resolve terms.

Example generic binding:

```yaml
bindings:
  operation:
    adapter: generic
    symbol: Operation.execute
  actor:
    adapter: generic
    symbol: Request.actor
  authorized:
    adapter: generic
    symbol: AuthorizationPolicy.is_authorized
  state_change:
    adapter: generic
    symbol: StateMutation
```

If a term cannot be bound, the package status becomes `REFUSED_UNBOUND_SYMBOLS`.

### 4.6 Validate IR

The validator checks:

- supported `ir_version`,
- schema validity,
- all names defined,
- source spans present,
- bindings present for required terms,
- types match,
- assumptions explicit,
- evidence requirements known,
- and no unsupported claim hidden behind weaker evidence.

### 4.7 Self-Consistency Check

Before checking the target system, the package checks whether its own supported claims are internally consistent.

V1 scope:

- contradictory expected results under overlapping conditions,
- impossible conjunctions over simple predicates,
- duplicate claims with incompatible outcomes,
- and unsatisfiable numeric constraints.

Evidence level: `CONSISTENCY_CHECKED`.

### 4.8 Dispatch Verification Tasks

The dispatcher routes claims based on type and adapter capabilities:

- schema/type checks -> core validator,
- simple logic/arithmetic -> SMT backend,
- symbol resolution -> adapter,
- tests -> test backend,
- traces -> trace backend,
- state machines -> model-checking backend,
- unsupported claims -> review/refusal.

### 4.9 Aggregate Evidence

Backend results are aggregated into an evidence object. The aggregator records:

- backend name,
- backend version,
- command or query,
- input hash,
- output hash,
- assumptions,
- result,
- and evidence level.

### 4.10 Decide Status

The status decision is pure.

Inputs:

- required evidence levels,
- achieved evidence levels,
- failed checks,
- timeouts,
- unsupported claims,
- review state,
- freshness state,
- and unbound symbols.

Output:

- final status,
- reason,
- next actions,
- optional source span for the failing phrase.

### 4.11 Emit Spec Package

The final artifact is a deterministic package:

```text
requirements/<requirement-id>/
  requirement.md
  source-diff.md
  requirement.ir.json
  bindings.json
  assumptions.json
  review.json
  verification-tasks.json
  evidence.json
  status.json
  implementation-spec.md
```

---

## 5. Intermediate Representation

### 5.1 Purpose

The IR is the stable middle layer between controlled language and verification backends.

It must be:

- typed,
- versioned,
- adapter-neutral,
- deterministic,
- diffable,
- hashable,
- and easy to validate.

Every IR node derived from controlled language carries provenance:

```yaml
source_span:
  document: controlled_requirement
  start_char: 42
  end_char: 65
  text: "actor is not authorized"
```

Source spans refer to the canonical controlled form after parser normalization. The normalization rule is versioned with `ir_version`.

### 5.2 Versioning And Migration

The IR is versioned. Phase 0 starts at `ir_version: 0.1`.

Policy:

- Patch versions may add optional fields only.
- Minor versions may add claim kinds or evidence fields.
- Existing packages are never silently upgraded.
- Migration commands preserve old IR hash, migration tool version, and migration diff.
- Validators reject unsupported `ir_version` values.

Example:

```bash
nlreq migrate requirements/REQ-AUTH-001 --to-ir-version 0.2
```

### 5.3 V1 Claim Kinds

V1 supports six system-neutral claim kinds:

1. Authorization precondition:
   - if actor lacks permission, action must be rejected or impossible.

2. State precondition:
   - action may succeed only if state predicate holds.

3. State postcondition:
   - after action succeeds, state predicate must hold.

4. Numeric invariant:
   - quantities must satisfy arithmetic constraints.

5. Event/state correspondence:
   - if observable event occurs, matching state transition must occur.

6. Bounded temporal claim:
   - within bounded steps, a transition must or must not occur.

Phase 0 implements the first three pipeline examples:

- authorization precondition,
- state postcondition,
- numeric invariant.

These exercise the full core pipeline without requiring trace integration or temporal model checking, which come later.

### 5.4 Example IR

```json
{
  "ir_version": "0.1",
  "requirement_id": "REQ-AUTH-001",
  "title": "Unauthorized operation is rejected before state changes",
  "source": {
    "original_text": "Unauthorized users should not be able to change state.",
    "controlled_text": "For every operation request:\n  if actor is not authorized\n  then operation must be rejected before state_change.\n",
    "controlled_text_approval": {
      "status": "approved",
      "approved_by": "reviewer@example.com",
      "approved_at": "2026-05-26T00:00:00Z"
    }
  },
  "claim": {
    "kind": "authorization_precondition",
    "action": "operation",
    "forall": [
      {"name": "request", "type": "OperationRequest"}
    ],
    "condition": [
      {
        "op": "not_authorized",
        "args": ["actor"],
        "source_span": {
          "document": "controlled_requirement",
          "start_char": 35,
          "end_char": 58,
          "text": "actor is not authorized"
        }
      }
    ],
    "expected": {
      "result": "rejected_before",
      "target": "state_change",
      "source_span": {
        "document": "controlled_requirement",
        "start_char": 66,
        "end_char": 114,
        "text": "operation must be rejected before state_change"
      }
    }
  },
  "required_evidence": [
    {
      "claim_path": "claim",
      "minimum_level": "SMT_CHECKED"
    }
  ]
}
```

The full JSON Schema is a Phase 0 deliverable. Inline examples are explanatory, not the schema contract.

The schema lives at `schemas/requirement-ir-0.1.schema.json` and is regenerated from the Pydantic models. CI must fail if the committed schema drifts from the generated schema.

### 5.5 Review Workflow

`NEEDS_REVIEW` has a required transition path.

A package may leave `NEEDS_REVIEW` only when `review.json` records:

- reviewer identity,
- reviewed artifact hashes,
- checklist results,
- approval or rejection,
- timestamp,
- and follow-up items.

Minimum checklist:

- Controlled form matches original intent.
- Claim shape matches controlled form.
- Source spans are present.
- Assumptions are explicit.
- Bindings are deterministic or manually justified.
- Required evidence level is appropriate.
- Unsupported claims are not hidden behind weaker evidence.

Solo mode:

- If author and reviewer are the same person, the review must be performed at least 24 hours after controlled-form approval.
- The package records that the review is a self-audit.

---

## 6. Controlled Natural Language

### 6.1 V1 Grammar

The grammar should be intentionally small.

Supported pattern:

```text
For every <entity>:
  if <condition>
  [and <condition> ...]
  then <action> must <expected_result>.
```

Supported expected results:

- `be rejected`
- `succeed`
- `emit <event>`
- `set <state> to <value>`
- `not change <state>`
- `increase <quantity> by <amount>`
- `decrease <quantity> by <amount>`
- `be rejected before <state_or_event>`

Supported conditions:

- equality,
- inequality,
- numeric comparison,
- membership,
- boolean predicate,
- authorization predicate,
- and conjunction.

Defer disjunction, nested temporal logic, probabilistic claims, and unbounded liveness.

### 6.2 Parser Tools

Phase 0 uses:

- Python,
- Lark,
- Pydantic,
- canonical JSON,
- pytest golden tests.

---

## 7. Adapter Interface

### 7.1 Purpose

Adapters let the core remain general-purpose.

The core does not know how to inspect every target system. It knows how to ask an adapter for symbols, coverage, tests, traces, and backend tasks.

### 7.2 Interface

```text
Adapter:
  adapter_id: string
  target_kind: string

  resolve_symbols(refs: SymbolRef[]) -> SymbolResolution[]
  validate_binding(binding: Binding) -> ValidationResult
  available_evidence(symbols: Symbol[]) -> EvidenceCapability[]
  generate_tasks(ir: RequirementIR) -> VerificationTask[]
  collect_evidence(task_results: TaskResult[]) -> BackendEvidence[]
```

### 7.3 Phase 0 Generic Adapter

Phase 0 uses a generic adapter backed by a static symbol table.

Example:

```json
{
  "symbols": {
    "operation": {"type": "action"},
    "actor": {"type": "principal"},
    "authorized": {"type": "predicate"},
    "state_change": {"type": "state_transition"}
  }
}
```

This proves the adapter contract without tying the core to any real ecosystem.

The generic adapter produces `STATICALLY_RESOLVED` evidence for symbol resolution and routes SMT-eligible claims through the core SMT backend using predicates encoded from the symbol table. It does not produce `TEST_VALIDATED` or `TRACE_VALIDATED` evidence. Those require a real adapter.

### 7.4 Adapter Conformance

Every real adapter must pass the adapter conformance suite before it can satisfy package gates.

The conformance suite checks that an adapter:

- implements every interface method,
- returns stable symbol-resolution results for the same input,
- distinguishes unresolved, ambiguous, and resolved symbols,
- reports evidence capabilities honestly,
- produces verification tasks in the core task schema,
- and returns evidence in the core evidence schema.

The Phase 0 generic adapter is the reference implementation used to build this suite.

### 7.5 Future Adapters

Future adapters may target:

- Python packages,
- TypeScript services,
- Go services,
- smart contracts,
- Rust crates,
- TLA+ specs,
- OpenAPI services,
- Terraform modules,
- or custom internal systems.

Each adapter should be added only after the core package format and status decision are stable.

---

## 8. Verification Backends

### 8.1 Self-Consistency Backend

Runs before target-system checks.

V1 detects:

- contradictory outcomes under overlapping conditions,
- unsatisfiable conjunctions,
- duplicate incompatible claims,
- and simple numeric contradictions.

Evidence: `CONSISTENCY_CHECKED`.

### 8.2 SMT Backend

Phase 0 uses Z3 for:

- simple predicates,
- finite-domain authorization logic,
- arithmetic constraints,
- threshold checks,
- and contradiction checks over supported IR.

Evidence: `SMT_CHECKED`.

### 8.3 Test Backend

Adapters may expose tests as evidence.

Evidence: `TEST_VALIDATED`.

Test evidence must record:

- command,
- test names,
- seed/config,
- tool version,
- input hash,
- and output hash.

### 8.4 Trace Backend

Adapters may expose runtime or execution traces.

Evidence: `TRACE_VALIDATED`.

Trace evidence proves only observed behavior, not unobserved behavior.

### 8.5 Model-Checking Backend

Phase 2+ may add state models.

Evidence:

- `BOUNDED_CHECKED(k)` for bounded search,
- `PROVEN_INDUCTIVE` only when a true inductive proof is established,
- `FAILED` with counterexample when violated,
- `TIMEOUT` when budget is exceeded.

The evidence object must record bounds, constants, model scope, checker version, and command line.

### 8.6 Normalized Trace Schema

Trace evidence is not part of Phase 0, but a shared trace schema is required before a second real adapter ships.

Phase 2 must define `NormalizedTrace` before trace validation becomes a gateable evidence source:

```text
NormalizedTrace:
  trace_id: string
  adapter_id: string
  source_hash: string
  events: TraceEvent[]

TraceEvent:
  event_id: string
  timestamp: string | logical_clock
  actor: string?
  action: string
  pre_state: object?
  post_state: object?
  metadata: object
```

Adapters may retain native traces, but gateable `TRACE_VALIDATED` evidence must point to a normalized trace or to a documented adapter-specific exception.

---

## 9. Statuses And Refusals

### 9.1 Final Status Values

Use these statuses:

- `ACCEPTED_WITH_EVIDENCE`
- `ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW`
- `REFUSED_AMBIGUOUS`
- `REFUSED_UNBOUND_SYMBOLS`
- `REFUSED_UNSUPPORTED_CLAIM`
- `REFUSED_FAILED_CHECK`
- `REFUSED_TIMEOUT`
- `NEEDS_SPEC_COVERAGE`

Do not use a single `CLOSED` status unless it is qualified by evidence level.

### 9.2 Refusal Payload

Every refusal must include:

- status,
- reason,
- source span when applicable,
- offending fragment,
- and next actions.

Example:

```json
{
  "status": "REFUSED_UNBOUND_SYMBOLS",
  "reason": "Term authorized has no approved binding.",
  "source_span": {
    "document": "controlled_requirement",
    "start_char": 44,
    "end_char": 54,
    "text": "authorized"
  },
  "next_actions": [
    "Add a binding for authorized in bindings.json.",
    "Or rewrite the requirement using an approved vocabulary term."
  ]
}
```

---

## 10. Implementation Spec Package

### 10.1 Purpose

The implementation spec package is what engineers or agents build from.

It is deterministic, reviewable, and auditable.

### 10.2 Contents

`implementation-spec.md` should contain:

- requirement ID,
- normalized requirement,
- target adapter,
- scope,
- affected symbols,
- required behavior,
- forbidden behavior,
- assumptions,
- acceptance tests or checks to add,
- evidence level,
- and open review items.

### 10.3 Example

```markdown
# REQ-AUTH-001

## Requirement

Unauthorized operation requests must be rejected before state changes.

## Scope

- Adapter: generic
- Action: operation
- Actor: actor
- Predicate: authorized
- Protected transition: state_change

## Required Behavior

If `actor` is not authorized, `operation` must be rejected before `state_change`.

## Acceptance Criteria

- Authorized actor path succeeds.
- Unauthorized actor path is rejected.
- Rejected path does not perform `state_change`.

## Evidence

- IR type-checked.
- Symbols resolved through generic adapter.
- Self-consistency checked.
- Authorization predicate SMT-checked under declared assumptions.
```

---

## 11. Package Coverage And Freshness

### 11.1 Coverage Manifest

Coverage is adapter-defined but core-recorded.

```json
{
  "version": "0.1",
  "coverage": [
    {
      "id": "generic-auth-v1",
      "adapter": "generic",
      "symbols": ["operation", "actor", "authorized", "state_change"],
      "spec_artifacts": [
        "requirements/REQ-AUTH-001/requirement.ir.json"
      ],
      "evidence": [
        "requirements/REQ-AUTH-001/evidence.json"
      ],
      "freshness": {
        "source_hash": "sha256:...",
        "validated_at": "2026-05-26T00:00:00Z"
      }
    }
  ]
}
```

If an adapter cannot provide enough coverage, the status is `NEEDS_SPEC_COVERAGE`.

### 11.2 Freshness

Adapters decide what source hashes mean. The core records and compares them.

Start in report-only mode. Do not block commits until evidence quality is proven.

---

## 12. CI And Gate Behavior

### 12.1 Shadow Mode

CI reports:

- package validity,
- stale evidence,
- unresolved bindings,
- failed checks,
- unsupported claims,
- and pending reviews.

### 12.2 Soft Gate

After shadow mode, require implementation PRs to reference a requirement package and show current status.

### 12.3 Hard Gate

Hard gates are opt-in and scoped by adapter, directory, and evidence level.

Do not hard-gate a new adapter until it has low false-positive rates in shadow mode.

---

## 13. Build Phases

Timeline assumption: these estimates assume one focused full-time engineer with access to a reviewer. As a solo side project, expect 2-3x longer.

### Phase 0: General-Purpose Core (Weeks 1-4)

Goal: implement the adapter-neutral core with a generic static-symbol adapter.

Deliverables:

- build plan committed as `docs/build-plan.md`,
- ADRs for Phase 0 tooling, IR versioning, LLM rewrite approval, and status purity,
- adapter interface specification in `docs/adapter-interface.md`,
- adapter-interface ADR in `docs/adr/0005-adapter-interface.md`,
- controlled-language grammar,
- parser,
- AST model,
- IR model,
- generated JSON Schemas,
- generic symbol-table adapter,
- adapter conformance test suite validated by the generic adapter,
- self-consistency check for supported claim shapes,
- Z3-backed SMT task runner,
- pure status-decision function,
- package writer,
- CLI,
- golden output tests.

Success criterion:

Three controlled requirements produce byte-stable packages:

- authorization precondition,
- state postcondition,
- numeric invariant.

Each package includes:

- `requirement.ir.json`,
- `bindings.json`,
- `assumptions.json`,
- `review.json`,
- `verification-tasks.json`,
- `evidence.json`,
- `status.json`,
- and `implementation-spec.md`.

No real target adapter is required in Phase 0.

### Phase 1: First Real Adapter (Weeks 5-10)

Goal: implement one real adapter selected by work priorities.

Candidate adapters:

- Python package adapter,
- TypeScript service adapter,
- Go service adapter,
- smart-contract adapter,
- OpenAPI adapter,
- spec-only adapter.

Selection criteria:

- important to the work project,
- small target surface,
- clear symbol model,
- existing tests or traces,
- low setup friction,
- reviewer available.

The plan should not choose the real adapter until Phase 0 proves the core.

By the end of Phase 0, the Phase 1 adapter selection must be committed in `docs/adr/0006-phase-1-adapter-selection.md`. The ADR names the selected ecosystem, the rationale, the expected adapter-specific tooling, and the evidence types Phase 1 will target.

### Phase 2: Stronger Evidence Backends (Weeks 11-18)

Goal: add stronger evidence for the chosen adapter.

Possible deliverables:

- property-based test generation,
- runtime trace validation,
- `NormalizedTrace` schema,
- model-checking integration,
- counterexample parser,
- evidence freshness checks,
- and CI report.

The exact backend depends on the Phase 1 adapter.

### Phase 3: Adoption Workflow (Weeks 19-26)

Goal: make the system usable by other engineers in shadow mode.

Deliverables:

- package index,
- review checklist UI or template,
- CI reporting,
- examples,
- adapter authoring guide,
- and documentation for adding a requirement.

### Phase 4: Soft Gate Pilot (Weeks 27-30)

Goal: let implementation workflows require visible requirement-package
references while keeping enforcement opt-in.

Deliverables:

- soft-gate report,
- requirement reference extraction from PR body or commit-message text,
- JSON and Markdown gate output,
- explicit non-zero exit mode for CI jobs that opt in,
- blocked/pass result over referenced packages,
- documentation for soft-gate rollout,
- and tests for pass, missing-reference, unknown-reference, and refused-package
  paths.

Success criterion:

An implementation PR or local CI job can reference `REQ-...` ids and receive a
deterministic report showing whether each referenced requirement exists,
validates, is approved, and has an accepted status. By default the command
reports blockers without failing; `--fail-on-blocking` enables opt-in failure.

---

## 14. Phase 0 Tooling

Phase 0 uses:

- Language: Python.
- Grammar: Lark.
- Schema/validation: Pydantic with generated JSON Schema committed.
- SMT: Z3.
- IR format: canonical JSON.
- Tests: pytest golden-file tests.
- CLI: argparse initially.

Rationale:

- Python is fast for verification tooling.
- Lark is easy to iterate with.
- Pydantic gives executable schema and JSON Schema.
- Z3 is mature and already fits the intended SMT use.
- Golden tests prove determinism early.

Future options:

- ANTLR after grammar stabilization.
- CVC5 if Z3 becomes a blocker.
- Apalache/TLC after state models exist.
- TypeScript tooling if a UI/service becomes primary.

---

## 15. Concrete First Milestone

The first milestone should create a package like:

```text
requirements/REQ-AUTH-001/
  requirement.md
  source-diff.md
  requirement.ir.json
  bindings.json
  assumptions.json
  review.json
  verification-tasks.json
  evidence.json
  status.json
  implementation-spec.md
  smt/C1.smt2
```

And a command:

```bash
nlreq validate requirements/REQ-AUTH-001
```

Expected success output:

```text
Requirement: REQ-AUTH-001
IR: valid
Bindings: valid
Consistency: checked
SMT: checked
Status: ACCEPTED_WITH_EVIDENCE
```

Expected refusal output:

```text
Requirement: REQ-AUTH-001
Status: REFUSED_UNBOUND_SYMBOLS
Reason: Term authorized has no approved binding.
Fragment: "authorized"
Next:
  - Add a binding for authorized in bindings.json.
  - Or rewrite the requirement using an approved vocabulary term.
```

---

## 16. Strategic Roadmap

The general-purpose core is the product foundation.

Adapters are how the system becomes useful in real environments, but no adapter should define the core.

Roadmap:

- V1: adapter-neutral core and generic adapter.
- V2: one real adapter selected by work priorities.
- V3: multiple adapters sharing the same package/evidence/status format.
- V4: cross-system requirements only after individual adapters are trustworthy.

Do not market cross-system validation until there is evidence across at least two mature adapters.

---

## 17. Final Position

This is a work project for a general-purpose Attestation Layer.

The correct implementation posture is:

> build the core once, keep it adapter-neutral, and let real systems plug in through explicit adapters.

That preserves the intellectual architecture of the Attestation Layer while keeping Phase 0 small enough to ship.
