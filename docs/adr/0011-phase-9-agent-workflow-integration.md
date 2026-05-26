# ADR 0011: Phase 9 Agent Workflow Integration

## Status

Accepted

## Context

Phases 0 through 8 establish controlled requirements, typed IR, package
generation, adapter evidence, gates, multiple adapters, and continuous
attestation reports. The next step is to connect those artifacts to an
agent-driven implementation loop without moving trust back into stochastic
output.

Phase 9 must support agents that draft requirements, generate or update code,
run verification, and prepare review handoffs. Those agents can improve
throughput, but they must not become hidden authorities. The human-reviewed
artifact remains the requirement package and its evidence. Agent output is useful
only when it is tied to deterministic package artifacts, explicit approvals,
backend results, and an audit log.

Agent workflow integration also introduces new failure modes:

- a specifier agent may over-normalize vague prose into a stronger requirement
  than the user intended,
- a coder agent may implement behavior that is not covered by the approved
  package,
- a verifier agent may retry until it finds a passing but weak evidence path,
- PR automation may bury important refusal or waiver details,
- and agents may disagree about unsupported claims, ambiguous symbols, stale
  traces, or failed backend evidence.

## Decision

Phase 9 will introduce an agent workflow integration layer around the existing
requirement-package, evidence, status, gate, and continuous-attestation
contracts.

The integration will define four workflow roles:

- **Specifier agent**: proposes controlled requirements, package metadata, and
  review checklist drafts.
- **Coder agent**: implements code or artifact changes against approved
  requirement packages.
- **Verifier agent**: runs package validation, adapter evidence collection,
  gates, and continuous-attestation commands.
- **Human reviewer**: approves controlled requirements, package revisions,
  waivers, and exception handling.

The specifier agent may draft controlled-language rewrites, but it must follow
the existing LLM rewrite approval protocol. No parser, verifier, gate, or coder
agent may treat a draft rewrite as approved input until the approval record is
present.

The coder agent must receive an implementation task payload that includes:

- requirement ids,
- package paths,
- current package hashes,
- accepted status decision,
- required evidence claims,
- adapter ids and target paths,
- assumptions,
- allowed implementation scope,
- and reviewer or policy constraints.

The verifier agent must emit a verification handoff payload after each run. The
payload will include:

- package validation summaries,
- evidence claim outcomes,
- gate report summaries,
- continuous-attestation findings when available,
- counterexamples,
- normalized trace references,
- stale evidence findings,
- unsupported claim findings,
- and a retry payload for the coder agent when deterministic checks fail.

Retry payloads must be structured. They may include failed check ids,
counterexamples, backend names, task input hashes, paths, and minimal diagnostic
messages. They must not ask the coder agent to bypass evidence requirements,
edit reviewed package artifacts in place, or weaken the requirement without a
new review workflow.

PR automation will post summaries that point reviewers to requirement packages,
status decisions, evidence claims, gate results, waivers, continuous-attestation
findings, and agent audit logs. It must highlight blockers and refused packages
before informational summaries. Human reviewers should be able to review the
requirement package and evidence first, then inspect code only when needed.

Phase 9 will add an append-only audit log for agent workflows. Each audit entry
will record:

- workflow id,
- step id,
- agent role,
- tool or command invoked,
- input package ids and hashes,
- output artifact ids and hashes,
- git ref or patch reference,
- decision or status summary,
- timestamp,
- and human approval references when applicable.

The audit log is evidence provenance, not a replacement for evidence. It can
show what agents did and which deterministic artifacts they produced, but it
does not by itself satisfy `TEST_VALIDATED`, `TRACE_VALIDATED`,
`BOUNDED_CHECKED`, or `PROVEN_INDUCTIVE`.

Escalation policy will be explicit:

- unsupported claims go back to the specifier and reviewer,
- ambiguous symbols require binding clarification or requirement rewrite,
- failed checks generate coder retry payloads only when the requirement remains
  approved and in scope,
- stale evidence triggers verifier refresh or human exception review,
- verifier/coder disagreement stops automation and creates a reviewer handoff,
- waiver use remains governed by the hard-gate waiver model,
- and continuous-attestation regressions create follow-up tasks rather than
  mutating historical packages.

The first Phase 9 slice will be report and artifact oriented. It will not
require a specific agent runtime. CLI and JSON payload contracts should be usable
from Codex, GitHub Actions, local scripts, or another orchestrator.

## Consequences

Phase 9 makes the Attestation Layer usable in an agent-driven implementation
loop while preserving the trust boundary established by earlier phases. Agents
can draft, implement, verify, retry, and summarize, but deterministic package
artifacts and human approvals remain the source of authority.

The tradeoff is additional workflow metadata. Implementation tasks, retry
payloads, PR comments, and audit entries must be kept small enough to review and
stable enough for automation. This is acceptable because the alternative is
letting agent behavior become implicit and unauditable.

The result should shift human attention from raw code diffs toward controlled
requirements, evidence claims, exceptions, and audit trails. Humans can still
inspect code and stop the workflow at every boundary.
