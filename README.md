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

The yellow paper specifies a Tier 1 property-based-testing loop as the first implementable slice. The reference implementation of that loop — a specifier agent that generates properties, a verifier harness that runs them against agent-generated code, and a retry loop driven by shrunk counterexamples — is in development and will be published in this repository under `/src` once a runnable end-to-end example is available.

The paper can be read and implemented against without the reference code. The code, when published, will serve as an existence proof that the specified architecture is buildable with today's tooling.

## License

Apache License 2.0. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

## Author

Leonardo Saturnino — lrsaturnino@gmail.com — [@Lrsaturnino](https://x.com/Lrsaturnino) — [github.com/lrsaturnino](https://github.com/lrsaturnino)
