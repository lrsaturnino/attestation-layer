# The Attestation Layer

**Architecture specification for spec-mediated verification of agent-produced software.**

> Review the spec, not the code. Verify the code against the spec, not against human intuition. Make the spec small enough to review, formal enough to check, and expressive enough to capture what matters. Treat code as a disposable compilation artifact derived from specs, regenerated on demand, trusted only because the specs are trusted.

This repository holds the **yellow paper** specifying the transitional architecture of the Attestation Layer: the architecture operators should build over the 2026–2030 window, before the human chokepoint at specification review dissolves into exception handling and the closed-loop steady state (described in the Wanabai white paper) becomes achievable.

The full specification is in [**YELLOW_PAPER.md**](./YELLOW_PAPER.md).

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

## Reference implementation

This repository now includes the Phase 0 core for a general-purpose NL Requirement Attestation Layer under `src/nlreq`.

The Phase 0 implementation is adapter-neutral. It provides:

- controlled-language parsing,
- typed IR and generated JSON Schemas,
- source-span provenance,
- a generic static-symbol adapter,
- an executable adapter conformance suite,
- evidence/status objects,
- Z3-backed Phase 0 SMT checks,
- package generation,
- and a CLI.

Install and test with `uv`:

```bash
uv sync --extra dev
uv run python scripts/check_schema_drift.py
uv run pytest
uv run nlreq validate-all requirements
```

Parse a controlled requirement:

```bash
uv run nlreq parse tests/fixtures/requirements/authorization_precondition.nlreq
```

Build and validate a package:

```bash
uv run nlreq package tests/fixtures/requirements/authorization_precondition.nlreq \
  --out requirements/REQ-AUTH-001 \
  --requirement-id REQ-AUTH-001 \
  --title "Unauthorized operation is rejected before state changes" \
  --claim-kind authorization_precondition

uv run nlreq validate requirements/REQ-AUTH-001
```

Validate every committed example package:

```bash
uv run nlreq validate-all requirements
```

Run adapter conformance against the Phase 0 generic adapter:

```bash
uv run nlreq conformance
```

Run adapter conformance against the Phase 1 Python package adapter:

```bash
uv run nlreq python-conformance tests/fixtures/adapters/pythonpkg/samplepkg --package-name samplepkg
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

uv run nlreq python-validate /tmp/REQ-PY-001 \
  --package-root tests/fixtures/adapters/pythonpkg/samplepkg \
  --package-name samplepkg \
  --project-root . \
  --test-path tests/fixtures/adapters/pythonpkg
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

Example packages live under `requirements/`.

The Phase 0 completion record is in [docs/phase-0-completion.md](./docs/phase-0-completion.md).
The Phase 1 Python adapter slice is described in
[docs/phase-1-python-adapter.md](./docs/phase-1-python-adapter.md).
The Phase 2 Python evidence package slice is described in
[docs/phase-2-python-evidence.md](./docs/phase-2-python-evidence.md).

## License

Apache License 2.0. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

## Author

Leonardo Saturnino — lrsaturnino@gmail.com — [@Lrsaturnino](https://x.com/Lrsaturnino) — [github.com/lrsaturnino](https://github.com/lrsaturnino)
