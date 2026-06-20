# The Attestation Layer

**Architecture specification for spec-mediated verification of agent-produced software — plus `nlreq`, a working requirement-attestation gate that implements it.**

> Review the spec, not the code. Verify the code against the spec, not against human intuition. Make the spec small enough to review, formal enough to check, and expressive enough to capture what matters. Treat code as a disposable compilation artifact derived from specs, regenerated on demand, trusted only because the specs are trusted.

This repository holds two things:

1. The **yellow paper** specifying the transitional architecture of the Attestation Layer: the architecture operators should build over the 2026–2030 window, before the human chokepoint at specification review dissolves into exception handling and the closed-loop steady state (described in the Wanabai white paper) becomes achievable. The full specification is in [**YELLOW_PAPER.md**](./YELLOW_PAPER.md).
2. The **reference implementation**, `nlreq` (under `src/nlreq/`): a general-purpose gatekeeper for natural-language requirements, described below in plain terms.

## What problem this addresses

When agent fleets drive the marginal cost of software production toward zero, the bottleneck moves from producing software to knowing it is correct. The yellow paper specifies the shape of the infrastructure that closes that gap:

- **The specification artifact** as the non-stochastic anchor — above it, inference is stochastic (LLM-generated); below it, verification is deterministic (tool-checked). The human reviews the spec, not the code.
- **Five specification tiers** — from property-based tests (Tier 1) through contracts, TLA+ model checking, verification-aware intermediate languages (Dafny, Lean 4), to runtime trace verification.
- **A two-agent topology** — specifier and verifier — integrated into an orchestration DAG with a single human review point.
- **An explicit migration path** to the closed-loop steady state described in the companion Wanabai white paper.

## Companion series

| # | Piece | Audience | Link |
|---|------|----------|------|
| 1 | *Out of the Loop* | CTOs, investors, strategists | [Substack](https://saturnino.substack.com/p/out-of-the-loop) |
| 2 | *The Attestation Layer* (article) | Senior engineers, architects | [Substack](https://saturnino.substack.com/p/the-attestation-layer) |
| 3 | *Software as Electricity* | Engineering leadership, futurists | [Substack](https://saturnino.substack.com/p/software-as-electricity) |
| 4 | **Yellow paper** (this repo) | Practicing implementers, formal-methods community | [YELLOW_PAPER.md](./YELLOW_PAPER.md) |
| 5 | *Wanabai* white paper | Builders, VCs, collaborators | [github.com/wanabai/wanabai](https://github.com/wanabai/wanabai) |

---

# `nlreq` — the reference implementation, in plain terms

## What it is

`nlreq` is a **gatekeeper for requirements**. Today, a requirement like "users can only refund their own orders" lives in a ticket, a prompt, or someone's head — and whether the code honors it depends on people remembering to check. `nlreq` makes the requirement itself a checkable object. You state it in a controlled form of English, the system translates it into formal logic, and then it verifies three things before anyone is allowed to build against it:

1. **Does it contradict itself?** Within one requirement, and jointly across a *set* of requirements (two rules that can never both hold are flagged with the conflicting fragments).
2. **Does it contradict what your system already guarantees?** The requirement is checked against a registered formal model of your existing system (`S`) with a real symbolic model checker (Apalache). A conflict comes back as a concrete counterexample — the exact sequence of steps where the new rule breaks an existing invariant — not an opinion.
3. **Does the code actually behave this way today?** The requirement's words are bound to real symbols in your codebase, and real execution traces (Foundry tests, `go test -trace`) are replayed against it.

If everything closes, the requirement becomes an immutable, content-hashed **package** with an honest evidence label on every claim. If anything fails, you get a structured refusal pointing at the **exact phrase** that is ambiguous, unbound, or contradicted, with suggested next actions. Downstream consumers — CI gates, agent work orders — only accept approved packages. The gate refuses instead of guessing; that is the entire point.

## The controlled language (and why not free prose)

Requirements are written in a small, fixed grammar — a deliberate menu of sentence shapes. A real example from the test fixtures:

```text
For every operation request:
  if actor is not authorized
  then operation must be rejected before state_change.
```

There are six claim kinds (`authorization_precondition`, `state_precondition`, `state_postcondition`, `event_state_correspondence`, `numeric_invariant`, `bounded_temporal`), a fixed set of predicates (`X is authorized`, `X state is Y`, numeric comparisons, set membership), and a fixed set of obligations (`must succeed`, `must reject before X`, `emit X within N seconds`, `keep X <= Y`, `module A causes module B to X within N seconds`).

Why not plain English? Because a checker needs exactly one meaning, and prose has several. "Users can only refund their own orders" can be read at least three ways. The controlled grammar guarantees that one sentence parses to exactly one logic formula, deterministically, every time. Every fragment of the parsed requirement carries a **source span** back to the characters you wrote, so refusals and clarifications point at the precise phrase in question.

## Starting from plain prose

You do not have to write the controlled form by hand. `nlreq intake-draft` accepts free-form prose (English or Portuguese) and uses an LLM to *propose* a controlled rewrite. The proposal is never auto-accepted:

- you review a hash-linked, side-by-side diff (`intake-diff`) between your original text and the proposed controlled form;
- you explicitly approve or reject it (`intake-approve`);
- the package permanently records the original text, the proposal, the approved form, the diff, and the model metadata;
- if the model is not confident about a fragment, it emits a clarification request naming that fragment instead of guessing.

The system refuses to *check* anything until the meaning has been pinned down and a human has signed off on the pinning.

## Where the LLM sits — and where it never sits

An LLM (optional, off by default) is used in exactly four places, all of them **proposal-only**:

1. **Drafting** — free prose → proposed controlled rewrite (the intake flow above).
2. **Semantic decomposition** — controlled text → proposed compositional IR, which a deterministic translator then lowers into formal logic, with agreement gates that refuse when independent translations disagree.
3. **Impact estimation** — a second opinion on which modules a requirement touches, cross-validated against the deterministic call graph; disagreements become review flags, never silent picks.
4. **Candidate spec extraction** — proposing draft formal invariants from existing code (Specula-style), which are untrusted until a human reviews and promotes them.

The LLM **never produces evidence, never decides a status, and never approves anything.** Every verdict in the pipeline comes from deterministic tools: the Lark parser, Z3, cvc5, Apalache, real test runners, and real trace readers. Construction-time guards in the data model make it impossible to even *represent* a high-assurance claim without the backing evidence object.

Practical configuration: the provider is Anthropic (`pip` extra `llm`), the default model is pinned in code (`claude-haiku-4-5-20251001` — cheap and fast is correct, since the model only drafts), overridable per call with `--model`. The API key is read from the `NLREQ_ANTHROPIC_API_KEY` environment variable or a `.claude/.env` file. A `RecordedLlmClient` replays captured responses so tests and CI are deterministic and need no network — the deterministic core never makes a network call.

## What an approved requirement gives you

The approved package is not prose. It contains the typed IR (claims with conditions and expected results), bindings to exact code symbols, the lowered formal artifacts, the evidence objects with their tool versions and bounds, the review records, and ready-made agent handoff artifacts (implementation contract sheet, work order with allowed paths, verifier handoff).

For an LLM implementer this is meaningfully better than natural language for three reasons. First, **ambiguity is gone** — the model can't pick a convenient reading. Second, **the acceptance criteria are executable** — the same checks that approved the requirement re-run after implementation, so "done" is mechanical, not vibes. Third, **the loop has backpressure** — an implementation that violates the claim fails the gate, and the failure feeds back as concrete context instead of a reviewer's memory. The thesis throughout: don't make the agent smarter; make the target unforgiving.

## Evidence honesty

Every claim carries one of nine evidence levels, and they are never conflated:

`TYPE_CHECKED` · `CONSISTENCY_CHECKED` · `STATICALLY_RESOLVED` · `SMT_CHECKED` · `TEST_VALIDATED` · `TRACE_VALIDATED` · `BOUNDED_CHECKED` · `PROVEN_INDUCTIVE` · `REVIEWED`

The discipline behind the labels:

- `BOUNDED_CHECKED` records its bound — "no violation within k steps" is never sold as a proof.
- `PROVEN_INDUCTIVE` can only be emitted by a registered proof-producing backend.
- A missing tool **blocks** (`tool_error` / `unsupported`) — it never fakes a pass. A solver timeout is a first-class non-approving outcome, never a silent approval.
- Every formal result records the exact command, tool version, and bounds, so it is reproducible.

## Using it on an existing (brownfield) system

`nlreq` never claims to check "the whole codebase." Every check is explicitly scoped, and the scoping is honest:

- **Impact analysis** walks the real call graph from the symbols your requirement names (Slither for Solidity, gopls for Go) to compute the affected-module set, cross-validated by an LLM estimate; disagreements surface as review flags.
- **The system model `S` is per-module.** You register formal specs for specific modules in a spec registry (with versioning, review status, and freshness). The `S ∧ R` consistency check runs against those models within an explicit verification budget.
- **Trace validation** replays recorded executions of the affected modules — including validating that a registered spec still reproduces the code's real traces, so you are never checking against fiction.

For a years-old legacy codebase, the practical limit is not size — it is **spec coverage**. Most brownfield modules have no formal model, and the honest behavior is the point: a requirement touching an unmodeled module is **blocked** as needing spec coverage, and a Specula-style extraction is queued that drafts a candidate spec from the code (grounded in its real traces) for human review and promotion. If an obscure corner of the legacy system contradicts your requirement and that corner is inside a registered `S` or reachable through the call graph and traces, the model checker finds it and names it. If it is outside both, the output says *no coverage* — never *passes*. Spec freshness is hash-tracked: when covered source drifts, the spec is marked stale and `S ∧ R` is blocked until a real trace re-validation releases it.

The realistic adoption posture: model the few critical paths first (the money paths, the auth paths), gate requirements against those, and grow coverage module by module — the same way test coverage grew historically.

## Using it on a brand-new (greenfield) system

No existing system is required — greenfield is the easier case. The flow inverts: each accepted requirement appends to the accumulated spec; the next requirement is checked against everything accepted so far; code is written to satisfy the spec; traces confirm it continuously. No drift, no archaeology, no extraction step. Requirements can also be attested before any `S` exists, at the evidence levels that don't need one (parsing, self-consistency, SMT).

## Multi-language requirements

Every real product is several languages glued together — contracts in Solidity, services in Go, frontends in TypeScript. Every verification tool on the market checks one island; the expensive bugs live on the *bridges between islands* (the contract emitted the event; the backend never acted on it).

`nlreq` lets you write the rule once — "a redemption must be authorized on-chain before the off-chain service sweeps it" — and produces **one proof object** spanning both sides. Each language's guard is discharged by a real per-language `S ∧ R` run, the results aggregate into a single proof whose closure gates the downstream action, and a counterexample on *either* side blocks it. The grammar has a dedicated obligation shape for this: `module A causes module B to X within N seconds`. A guard from one language can never be discharged by another language's result.

Language support is tiered, and the tiering is enforced — an adapter cannot claim a capability level its recorded tool provenance doesn't back:

| Tier | Languages | Backing |
|---|---|---|
| Production verticals | Solidity, Go | Real Slither symbol/call-graph resolution, real Foundry trace extraction; real gopls + callgraph, real `go test -trace` with a vendored trace reader |
| Tool-backed | Python | Real `ast`-based resolution, certified through the conformance suite |
| Static-resolution | TypeScript, JavaScript, Rust, Java | Declaration-level resolution today; honestly capped at the lower capability level |
| Contract formats | OpenAPI, GraphQL, JSON Schema, AsyncAPI, Protobuf/gRPC, command/test-runner, TLA+ models | Declaration adapters with their own packaging and validation flows |

On the formal side the core speaks Z3 and cvc5 (SMT), and TLA+ through Apalache (with a TLC runner contract). The formalism is a backend, not the spine: the IR projects into backends through a lowering boundary, and cross-backend agreement is itself checked.

## For auditors and reviewers

What an auditor usually gets is "we used good practices" plus a code snapshot. What an `nlreq` package hands them, per requirement:

- the exact controlled text and its full approval trail — including the LLM-rewrite diff if one happened;
- every claim with the tool that checked it, the command, the version, and the bounds — reproducible, with replayable evidence bundles;
- signed producer attestations with key-trust policy, an immutable content-addressed artifact store, and review records hash-bound to the exact artifact versions reviewed;
- refusals as first-class artifacts — you can show what the system rejected and why.

This supports three concrete workflows: handing auditors intended behavior with conformance evidence (so they spend their time hunting what the spec missed, not reverse-engineering intent); mechanical change-control evidence for compliance regimes; and post-incident forensics — which requirement was approved, against which spec version, with what evidence, signed by whom, answerable in minutes. The honest limit: evidence quality is bounded by spec quality, which is exactly why human review records are first-class, hash-bound artifacts.

---

## Quickstart

Install and run the test suite (requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/)):

```bash
uv sync --extra dev
uv run python scripts/check_schema_drift.py
uv run pytest
```

The deterministic core needs only Z3 (installed automatically). Optional extras: `--extra llm` (Anthropic drafting), `--extra formal` (cvc5 second backend). The heavier evidence paths use external tools when present — `apalache-mc`, `forge` (Foundry), `slither`, `go` — and **block honestly when absent**.

Parse a controlled requirement:

```bash
uv run nlreq parse tests/fixtures/requirements/authorization_precondition.nlreq
```

Build and validate a requirement package:

```bash
uv run nlreq package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out requirements/REQ-AUTH-001 \
  --requirement-id REQ-AUTH-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition

uv run nlreq validate requirements/REQ-AUTH-001
```

Expected validation output:

```text
Requirement: REQ-AUTH-001
IR: valid
Bindings: valid
Consistency: checked
SMT: checked
Status: ACCEPTED_WITH_EVIDENCE
```

Start from free prose instead (`--method llm` requires `--extra llm` and `NLREQ_ANTHROPIC_API_KEY`; `--method manual` works offline with a `--suggested` controlled file you provide):

```bash
echo "Refunds must only be issued to the customer who placed the order." > /tmp/prose.txt

uv run nlreq intake-draft /tmp/prose.txt --method llm \
  --intake-id INTAKE-001 --proposal-id PROP-001 \
  --out /tmp/intake-proposal.json

uv run nlreq intake-diff /tmp/intake-proposal.json      # review the original-vs-controlled diff

uv run nlreq intake-approve /tmp/intake-proposal.json \
  --approval-id APPROVAL-001 --approved-by you@example.com \
  --decision approved --out /tmp/intake-approval.json
```

Validate every committed example package, and wire the gates into CI (report-only → soft → hard):

```bash
uv run nlreq validate-all requirements
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001
uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-AUTH-001 \
  --changed-path src/auth.py
```

Example packages live under `requirements/`; worked examples under `examples/` and `docs/examples.md`. The CLI has 148 subcommands covering the full pipeline (`uv run nlreq --help`) — the most-used flows are walked through below.

<details>
<summary><strong>Full command walkthroughs</strong> — per-adapter packaging and conformance, gates, continuous attestation, traces, routing, TLA+, agent handoff</summary>

Run adapter conformance against the generic adapter:

```bash
uv run nlreq conformance
```

Run adapter conformance against the Python package adapter:

```bash
uv run nlreq python-conformance tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg
```

Run adapter conformance against the OpenAPI adapter:

```bash
uv run nlreq openapi-conformance tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api
```

Run adapter conformance against the GraphQL adapter:

```bash
uv run nlreq graphql-conformance tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

Run adapter conformance against the JSON Schema adapter:

```bash
uv run nlreq json-schema-conformance tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

Run adapter conformance against the AsyncAPI adapter:

```bash
uv run nlreq asyncapi-conformance tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

Run adapter conformance against the Protobuf/gRPC adapter:

```bash
uv run nlreq protobuf-conformance tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf
```

Build and validate a Python-adapter evidence package:

```bash
uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq \
  --out /tmp/REQ-PY-001 \
  --requirement-id REQ-PY-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg

uv run nlreq python-package tests/fixtures/requirements/python_operation_success.nlreq \
  --out /tmp/REQ-PY-PROP-001 \
  --requirement-id REQ-PY-PROP-001 \
  --title "Python operation succeeds for approved actor" \
  --claim-kind state_precondition \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --property-checks

uv run nlreq python-validate /tmp/REQ-PY-001 \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
```

Build and validate an OpenAPI-adapter evidence package:

```bash
uv run nlreq openapi-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-OPENAPI-001 \
  --requirement-id REQ-OPENAPI-001 \
  --title "Unauthorized OpenAPI operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api

uv run nlreq openapi-validate /tmp/REQ-OPENAPI-001 \
  --document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api
```

Build and validate a GraphQL-adapter evidence package:

```bash
uv run nlreq graphql-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-GRAPHQL-001 \
  --requirement-id REQ-GRAPHQL-001 \
  --title "Unauthorized GraphQL operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --schema tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql

uv run nlreq graphql-validate /tmp/REQ-GRAPHQL-001 \
  --schema tests/fixtures/adapters/graphql/sample-schema.graphql \
  --graphql-name sample-graphql
```

Build and validate a JSON Schema-adapter evidence package:

```bash
uv run nlreq json-schema-package tests/fixtures/requirements/state_postcondition.nlreq \
  --out /tmp/REQ-JSON-SCHEMA-001 \
  --requirement-id REQ-JSON-SCHEMA-001 \
  --title "Approved operation sets accepted status" \
  --claim-kind state_postcondition \
  --schema tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema

uv run nlreq json-schema-validate /tmp/REQ-JSON-SCHEMA-001 \
  --schema tests/fixtures/adapters/jsonschema/sample-schema.json \
  --json-schema-name sample-json-schema
```

Build and validate an AsyncAPI-adapter evidence package:

```bash
uv run nlreq asyncapi-package tests/fixtures/requirements/event_emit.nlreq \
  --out /tmp/REQ-ASYNCAPI-001 \
  --requirement-id REQ-ASYNCAPI-001 \
  --title "Approved operation emits accepted event" \
  --claim-kind event_state_correspondence \
  --document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api

uv run nlreq asyncapi-validate /tmp/REQ-ASYNCAPI-001 \
  --document tests/fixtures/adapters/asyncapi/sample-asyncapi.json \
  --asyncapi-name sample-event-api
```

Build and validate a Protobuf/gRPC-adapter evidence package:

```bash
uv run nlreq protobuf-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-PROTOBUF-001 \
  --requirement-id REQ-PROTOBUF-001 \
  --title "Unauthorized gRPC operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --schema tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf

uv run nlreq protobuf-validate /tmp/REQ-PROTOBUF-001 \
  --schema tests/fixtures/adapters/protobuf/sample.proto \
  --protobuf-name sample-protobuf
```

Build and validate a command/test-runner-backed evidence package:

```bash
uv run nlreq command-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-CMD-001 \
  --requirement-id REQ-CMD-001 \
  --title "Unauthorized operation is rejected by an existing command check" \
  --claim-kind authorization_precondition \
  --checks docs/examples/command-checks.example.json \
  --project-root tests/fixtures/adapters/command

uv run nlreq command-validate /tmp/REQ-CMD-001 \
  --checks docs/examples/command-checks.example.json \
  --project-root tests/fixtures/adapters/command

uv run nlreq command-evidence requirements \
  --checks docs/examples/command-checks.example.json \
  --requirement-id REQ-AUTH-001 \
  --project-root tests/fixtures/adapters/command \
  --out /tmp/nlreq-command-results.json
```

Build adoption artifacts:

```bash
uv run nlreq package-index requirements --out requirements/index.json

uv run nlreq package-index requirements \
  --openapi-document tests/fixtures/adapters/openapi/sample-openapi.json \
  --openapi-name sample-api

uv run nlreq ci-report requirements \
  --out /tmp/nlreq-ci-report.json \
  --markdown-out /tmp/nlreq-ci-report.md

uv run nlreq review-template REQ-AUTH-001
```

Run the soft gate:

```bash
uv run nlreq soft-gate requirements --requirement-id REQ-AUTH-001

uv run nlreq soft-gate requirements \
  --references-file /tmp/pr-body.md \
  --out /tmp/nlreq-soft-gate.json \
  --markdown-out /tmp/nlreq-soft-gate.md \
  --fail-on-blocking
```

Run the hard gate:

```bash
uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-AUTH-001 \
  --changed-path src/auth.py

uv run nlreq hard-gate requirements \
  --policy docs/examples/gate-policy.example.json \
  --requirement-id REQ-REFUSED-UNBOUND-001 \
  --changed-path src/auth.py
```

The refused-package hard-gate command is expected to exit non-zero.

Run a continuous attestation report:

```bash
uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --out /tmp/nlreq-continuous.json \
  --markdown-out /tmp/nlreq-continuous.md
```

Validate normalized runtime traces:

```bash
uv run nlreq trace-validate requirements \
  --requirement-id REQ-AUTH-001 \
  --trace-artifact /tmp/normalized-traces.json \
  --out /tmp/nlreq-trace-validation.json \
  --markdown-out /tmp/nlreq-trace-validation.md

uv run nlreq continuous-attestation requirements \
  --trigger schedule \
  --trace-artifact /tmp/normalized-traces.json \
  --trace-validation \
  --out /tmp/nlreq-continuous-with-traces.json
```

Build an adapter routing report:

```bash
uv run nlreq validate-adapter-registry docs/examples/adapter-registry.example.json
uv run nlreq validate-routing-policy docs/examples/routing-policy.example.json

uv run nlreq route-adapters requirements \
  --adapter-registry docs/examples/adapter-registry.example.json \
  --routing-policy docs/examples/routing-policy.example.json \
  --changed-path src/auth.py \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-routing.json \
  --markdown-out /tmp/nlreq-routing.md
```

Build and validate a TLA/model-checking-backed package:

```bash
uv run nlreq tla-package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out /tmp/REQ-AUTH-TLA-001 \
  --requirement-id REQ-AUTH-TLA-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition \
  --model-config docs/examples/tla-models.example.json \
  --project-root tests/fixtures/adapters/tla

uv run nlreq tla-validate /tmp/REQ-AUTH-TLA-001 \
  --model-config docs/examples/tla-models.example.json \
  --project-root tests/fixtures/adapters/tla

uv run nlreq tla-check requirements \
  --model-config docs/examples/tla-models.example.json \
  --requirement-id REQ-AUTH-001 \
  --project-root tests/fixtures/adapters/tla \
  --out /tmp/nlreq-tla-results.json
```

Build an agent verifier handoff:

```bash
uv run nlreq agent-task requirements \
  --requirement-id REQ-AUTH-001 \
  --allowed-path src/auth.py \
  --out /tmp/nlreq-agent-task.json

uv run nlreq agent-verify requirements \
  --requirement-id REQ-AUTH-001 \
  --out /tmp/nlreq-agent-handoff.json \
  --markdown-out /tmp/nlreq-agent-handoff.md
```

Early-phase walkthrough docs: [Phase 0 completion](./docs/phase-0-completion.md) ·
[Python adapter](./docs/phase-1-python-adapter.md) ·
[Python evidence](./docs/phase-2-python-evidence.md) ·
[adoption workflow](./docs/phase-3-adoption-workflow.md) ·
[soft gate](./docs/phase-4-soft-gate-pilot.md) ·
[hard gate](./docs/phase-5-hard-gate.md) ·
[stronger backends](./docs/phase-6-stronger-backends.md) ·
[OpenAPI](./docs/phase-7-openapi-adapter.md) ·
[continuous attestation](./docs/phase-8-continuous-attestation.md) ·
[agent workflow](./docs/phase-9-agent-workflow.md) ·
[command/test-runner](./docs/phase-10-command-test-runner-adapter.md) ·
[runtime traces](./docs/phase-11-runtime-trace-validation.md) ·
[registry & routing](./docs/phase-12-adapter-registry-routing.md) ·
[TLA+ adapter](./docs/phase-13-tla-model-checking-adapter.md) ·
[GraphQL](./docs/phase-14-graphql-schema-adapter.md) ·
[JSON Schema](./docs/phase-15-json-schema-adapter.md) ·
[AsyncAPI](./docs/phase-16-asyncapi-adapter.md) ·
[Protobuf/gRPC](./docs/phase-17-protobuf-grpc-adapter.md).
The full phase roadmap continues through `docs/phase-192-*.md`.

</details>

## Status (as of 2026-06)

The capability surface described above is implemented and tested: 1,047 tests pass (the suite executes the real toolchain where installed — Apalache, Z3, cvc5, Slither, Foundry, Go — including a cross-language capstone that closes one proof object across a real Solidity and Go `S ∧ R` and blocks the gated action on a counterexample from either side). The original vision-to-implementation gap inventory ([docs/vision-gap-spec.md](./docs/vision-gap-spec.md)) is fully closed.

What remains before the project's own final conclusion claim is **operational evidence, not code** — release-scale measured translation corpora, retained runs over non-toy reviewed specs, an external reproduction and red-team pass, pilot evidence, and a signed release bundle. The system tracks this about itself: see [docs/claude-convo-real-evidence-gap-assessment.md](./docs/claude-convo-real-evidence-gap-assessment.md) and [docs/operational-real-evidence-gap-closure-plan.md](./docs/operational-real-evidence-gap-closure-plan.md). Until those close, it deliberately refuses to certify its own conclusion — the same honesty discipline it applies to requirements.

## Adoption references

- [C4 architecture diagrams](./docs/c4-architecture.md)
- [Adapter authoring guide](./docs/adapter-authoring-guide.md)
- [Adding a requirement](./docs/adding-a-requirement.md)
- [Attestation artifact catalog](./docs/attestation-artifact-catalog.md)
- [Future adapter expansion and routing](./docs/future-adapter-routing.md)
- [Review checklist template](./docs/review-checklist-template.md)
- [Examples](./docs/examples.md)
- [Scope and non-goals](./docs/scope.md) — *historical (2026-05-30): predates the gap-closure campaigns; cross-requirement consistency, LLM-assisted drafting, and impact analysis described there as out of scope are implemented today. The still-true non-goals: no code generation, no agent invocation, no implementation-planning decomposition.*

## License

Apache License 2.0. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

## Author

Leonardo Saturnino — lrsaturnino@gmail.com — [@Lrsaturnino](https://x.com/Lrsaturnino) — [github.com/lrsaturnino](https://github.com/lrsaturnino)
