# Phase 9 Agent Workflow Integration

Phase 9 adds artifact contracts that let agents draft, implement, verify, retry,
and summarize work without becoming the trust anchor. Requirement packages,
evidence, status decisions, gates, and human approvals remain authoritative.

## Implemented Slice

- ADR 0011 design anchor
- implementation task payloads for coder agents through `nlreq agent-task`
- verifier handoff payloads through `nlreq agent-verify`
- structured retry payloads for failed deterministic checks
- PR-review Markdown rendering through `nlreq agent-pr-comment`
- append-only audit log entries through `nlreq agent-audit`
- soft-gate integration in verifier handoffs
- optional hard-gate integration in verifier handoffs
- optional continuous-attestation finding integration in verifier handoffs
- package hash references in implementation tasks and audit entries
- reviewer constraints and allowed implementation scope in task payloads

## Build An Implementation Task

```bash
uv run nlreq agent-task requirements \
  --requirement-id REQ-AUTH-001 \
  --workflow-id WF-REQ-AUTH-001 \
  --allowed-path src/auth.py \
  --reviewer-constraint "Do not change reviewed package artifacts." \
  --out /tmp/nlreq-agent-task.json
```

The task payload includes requirement ids, package paths, package hashes,
status, review state, required evidence claims, assumptions, allowed paths, and
blockers. Coder agents should proceed only when `ready` is `true`.

## Build A Verifier Handoff

```bash
uv run nlreq agent-verify requirements \
  --requirement-id REQ-AUTH-001 \
  --workflow-id WF-REQ-AUTH-001 \
  --out /tmp/nlreq-agent-handoff.json \
  --markdown-out /tmp/nlreq-agent-handoff.md
```

Verifier handoffs include package summaries, soft-gate findings, optional
hard-gate findings, optional continuous-attestation findings, retry payloads,
and a reviewer focus section.

Hard-gate policy can be included:

```bash
uv run nlreq agent-verify requirements \
  --requirement-id REQ-AUTH-001 \
  --policy docs/examples/gate-policy.example.json \
  --changed-path src/auth.py \
  --out /tmp/nlreq-agent-handoff.json
```

Continuous attestation can be included:

```bash
uv run nlreq agent-verify requirements \
  --requirement-id REQ-AUTH-001 \
  --continuous-run /tmp/nlreq-continuous.json \
  --out /tmp/nlreq-agent-handoff.json
```

## Render A PR Comment

```bash
uv run nlreq agent-pr-comment /tmp/nlreq-agent-handoff.json \
  --out /tmp/nlreq-agent-pr-comment.md
```

The PR comment highlights findings before retry payloads, so reviewers see
blockers and refused packages before informational summaries.

## Append An Audit Entry

```bash
uv run nlreq agent-audit \
  --log /tmp/nlreq-agent-audit.json \
  --workflow-id WF-REQ-AUTH-001 \
  --step-id verify \
  --agent-role verifier \
  --tool "nlreq agent-verify" \
  --input-package requirements/REQ-AUTH-001 \
  --output-artifact /tmp/nlreq-agent-handoff.json \
  --decision-status pass
```

Audit entries record what an agent did and which deterministic artifacts it used
or produced. They do not satisfy evidence levels by themselves.

## Boundary

Phase 9 does not introduce an agent runtime, autonomous merge behavior, or a new
trust source. It emits JSON and Markdown artifacts that can be used by Codex,
GitHub Actions, local scripts, or another orchestrator.

Agents must not edit reviewed requirement package artifacts in place. Unsupported
claims, ambiguous symbols, failed checks, stale evidence, and verifier/coder
disagreement require a retry payload or human review handoff.

## Validation

```bash
uv run pytest tests/test_agent_workflow.py
uv run nlreq agent-task requirements --requirement-id REQ-AUTH-001
uv run nlreq agent-verify requirements --requirement-id REQ-AUTH-001
```
