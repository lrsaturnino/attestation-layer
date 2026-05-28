# Attestation Artifact Catalog

This catalog records the artifact kinds currently understood by the NL
Requirement Attestation Layer and how Phase 8 continuous attestation treats
them.

## Requirement Package Artifacts

| Artifact | Owner | Continuous Use |
|---|---|---|
| `requirement.ir.json` | Package builder | Parsed and hash-checked by package validation. |
| `bindings.json` | Package builder | Compared against current adapter symbol resolution. |
| `assumptions.json` | Package builder | Checked for package integrity. |
| `review.json` | Human review workflow | Used for review decision and review age. |
| `verification-tasks.json` | Adapter/core task generation | Recomputed for freshness and source-sensitive drift. |
| `adapter-results.json` | Adapter backend execution | Checked against current task input hashes. |
| `command-checks.json` | Phase 10 command adapter | Reviewed command linkage for command-backed packages. |
| `command-results.json` | Phase 10 command adapter | Bounded command execution results and source/test hashes. |
| `trace-validation-results.json` | Phase 11 trace validator | Runtime trace validation results and counterexamples. |
| `tla-models.json` | Phase 13 TLA adapter | Reviewed model/config bindings and checker configuration. |
| `tla-results.json` | Phase 13 TLA adapter | Bounded model-checking results and model/config hashes. |
| `generated-tests.json` | Generated-test backend | Cataloged as generated test evidence, not proof. |
| `counterexamples.json` | Backend result normalization | Cataloged as structured failure evidence. |
| `normalized-traces.json` | Trace ingestion | Parsed as trace artifacts when present. |
| `evidence.json` | Evidence aggregation | Compared for hash changes and status inputs. |
| `status.json` | Pure status decision | Compared for status regressions. |
| `implementation-spec.md` | Package emission | Checked for package integrity. |
| `smt/C1.smt2` | Core SMT backend | Checked for package integrity. |

## Continuous Run Artifact

The `continuous-attestation` command emits a JSON object with:

- `run_version`,
- `run_id`,
- `trigger`,
- `timestamp`,
- `repo_ref`,
- `adapter_config`,
- `summary`,
- `findings`,
- `package_freshness`,
- `trace_artifacts`,
- `deltas`,
- and `package_index`.

Continuous run artifacts are time-indexed reports. They reference requirement
packages but do not rewrite reviewed package artifacts.

## Agent Workflow Artifacts

Phase 9 adds agent workflow artifacts:

- `agent_implementation_task`: task payload for coder agents, including
  requirement ids, package hashes, status, review state, required evidence,
  assumptions, allowed paths, reviewer constraints, and blockers.
- `agent_verifier_handoff`: verification summary for reviewers and coder retry,
  including package summaries, gate reports, continuous-attestation summaries,
  findings, retry payloads, and review focus.
- `agent_audit_entry`: append-only provenance entry for one workflow step,
  including agent role, tool invocation, input package hashes, output artifact
  hashes, git ref, decision summary, timestamp, and human approval references.

Agent workflow artifacts are orchestration artifacts. They do not satisfy
evidence levels by themselves.

## Normalized Trace Artifact

Normalized traces use the existing `NormalizedTraceArtifact` schema. A trace
must include:

- `trace_id`,
- `adapter_id`,
- `source_hash`,
- `events`,
- and metadata describing provenance.

Phase 8 expects trace metadata to include:

- `requirement_ids`,
- `environment`,
- `capture_window`,
- and `redaction.status`.

Allowed redaction status values for a clean Phase 8 run are `redacted` and
`not_required`.

## Evidence Mapping

| Artifact | May Satisfy Evidence |
|---|---|
| Valid IR and package schemas | `TYPE_CHECKED` |
| Current adapter bindings | `STATICALLY_RESOLVED` |
| Core consistency backend | `CONSISTENCY_CHECKED` |
| Core SMT backend | `SMT_CHECKED` |
| Scoped pytest, generated property runs, or reviewed command checks | `TEST_VALIDATED` |
| Validated normalized traces | `TRACE_VALIDATED` |
| Reviewed TLA+ model checks | `BOUNDED_CHECKED` |
| Agent audit entries | None |

Trace artifacts are ingested and reported in Phase 8. Phase 11 adds explicit
trace validation; only supported validators over acceptable redaction states may
produce `TRACE_VALIDATED`. Raw normalized trace presence remains report-only.
