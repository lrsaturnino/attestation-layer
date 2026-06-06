from __future__ import annotations

from pathlib import Path

from nlreq.artifact_store import (
    ArtifactRecord,
    ReplayCommandMetadata,
    build_replay_bundle_manifest_v2,
    put_artifact,
    verify_replay_bundle,
)
from nlreq.benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus
from nlreq.benchmark_reporting import (
    EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS,
    ExtendedBenchmarkDimensionResult,
    PublicBenchmarkSuite,
    PublicLeaderboardEntry,
    build_benchmark_evaluation_report,
    build_extended_benchmark_evaluation_report,
    build_public_benchmark_release_report,
)
from nlreq.ci_pr_gate import build_ci_adoption_report
from nlreq.conclusion_certification import (
    build_final_real_evidence_conclusion_certification_report,
)
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.cross_language import (
    AdapterEvidenceReference,
    CausalTraceLinkV2,
    build_cross_language_causal_proof_object,
)
from nlreq.dsl_v2 import DslV2Parser
from nlreq.end_to_end_gate import (
    EXTENDED_GATE_REQUIRED_STAGES,
    EndToEndRequirementGateReport,
    build_extended_requirement_gate_report,
)
from nlreq.gate import GatePolicy
from nlreq.jsonutil import sha256_json
from nlreq.models import BackendResult, EvidenceLevel, NormalizedTraceArtifact
from nlreq.policy_governance import (
    PolicyChangeRecord,
    build_ci_policy_governance_report,
    build_waiver_audit_report,
)
from nlreq.proof_closure import build_proof_dispatch_plan, build_proof_object
from nlreq.reference_demo import (
    BetaPilotFinding,
    BetaPilotReport,
    ReferenceDemoManifest,
    build_extended_reference_demo_report,
    build_reference_brownfield_pilot_report,
    build_reference_demo_report,
)
from nlreq.signed_evidence import ProducerKey, ProducerKeyRegistry, sign_evidence_payload
from nlreq.source_adapter import SourceManifest
from nlreq.verification_cache import (
    ParallelDispatchTask,
    VerificationCacheIndex,
    VerificationCachePolicyV2,
    build_parallel_dispatch_plan,
    build_verification_cache_key,
    record_cache_artifact,
)


PASSED_EXTENDED_STAGE_STATUSES = {
    stage: "passed" for stage in EXTENDED_GATE_REQUIRED_STAGES
}
PASSED_EXTENDED_STAGE_STATUSES.update(
    {
        "controlled_intake": "approved",
        "semantic_translation": "accepted",
        "formal_claim": "lowered",
        "requirement_self_consistency": "valid",
        "s_and_r_composition": "valid",
        "spec_freshness": "fresh",
        "trace_validation": "satisfied",
        "adapter_evidence": "certified",
        "proof_closure": "closed",
    }
)


def test_phase144_cross_language_causal_proof_closes_and_blocks_missing_links() -> None:
    proof = _closed_proof()
    manifests = [_manifest("python-source", "python"), _manifest("solidity-source", "solidity")]
    traces = [_traces()]
    evidence = [
        AdapterEvidenceReference(
            evidence_id="py-evidence",
            adapter_id="python-source",
            artifact_hash="sha256:py",
            evidence_level="TRACE_VALIDATED",
            producer_id="python-producer",
            replay_bundle_hash="sha256:py-bundle",
        ),
        AdapterEvidenceReference(
            evidence_id="sol-evidence",
            adapter_id="solidity-source",
            artifact_hash="sha256:sol",
            evidence_level="TRACE_VALIDATED",
            producer_id="solidity-producer",
            replay_bundle_hash="sha256:sol-bundle",
        ),
    ]
    link = CausalTraceLinkV2(
        link_id="py-to-sol",
        from_adapter_id="python-source",
        from_trace_id="py-trace",
        from_event_id="request",
        to_adapter_id="solidity-source",
        to_trace_id="sol-trace",
        to_event_id="settle",
        relation="causes",
        evidence_hash="sha256:causal-link",
    )

    closed = build_cross_language_causal_proof_object(
        proof=proof,
        manifests=manifests,
        traces=traces,
        evidence=evidence,
        causal_links=[link],
        required_adapter_ids=["python-source", "solidity-source"],
    )
    missing_link = build_cross_language_causal_proof_object(
        proof=proof,
        manifests=manifests,
        traces=traces,
        evidence=evidence,
        causal_links=[
            link.model_copy(update={"to_event_id": "missing"})
        ],
        required_adapter_ids=["python-source", "solidity-source"],
    )

    assert closed.closure_status == "closed"
    assert closed.result == "accepted"
    assert closed.language_count == 2
    assert closed.causal_links[0].status == "satisfied"
    assert missing_link.closure_status == "blocked"
    assert missing_link.blockers[0].category == "trace_link"


def test_phase145_replay_verifier_enforces_artifacts_producers_and_signatures(
    tmp_path: Path,
) -> None:
    source = tmp_path / "evidence.json"
    source.write_text('{"result":"valid"}\n')
    store_root = tmp_path / "store"
    record = put_artifact(
        store_root=store_root,
        source_path=source,
        logical_name="formal-result",
        metadata={
            "evidence_level": "BOUNDED_CHECKED",
            "producer_id": "apalache",
        },
    )
    envelope = sign_evidence_payload(
        payload={"artifact_hash": record.artifact_hash, "logical_name": record.logical_name},
        producer_id="apalache",
        key_id="key-apalache",
        secret="secret",
        envelope_id="env-apalache",
    )
    registry = ProducerKeyRegistry(
        keys=[
            ProducerKey(
                key_id="key-apalache",
                producer_id="apalache",
                trusted_for_high_assurance=True,
            )
        ]
    )
    bundle = build_replay_bundle_manifest_v2(
        bundle_id="bundle-valid",
        source_store_id="store",
        command=ReplayCommandMetadata(command=["apalache", "check", "Spec.tla"]),
        records=[record],
        signed_envelopes=[envelope],
    )

    valid = verify_replay_bundle(
        bundle_root=store_root,
        bundle=bundle,
        registry=registry,
        secrets_by_key_id={"key-apalache": "secret"},
    )
    missing_producer = verify_replay_bundle(
        bundle_root=store_root,
        bundle=bundle.model_copy(
            update={
                "records": [
                    record.model_copy(update={"metadata": {"evidence_level": "BOUNDED_CHECKED"}})
                ]
            }
        ),
        registry=registry,
        secrets_by_key_id={"key-apalache": "secret"},
    )
    untrusted = verify_replay_bundle(
        bundle_root=store_root,
        bundle=bundle,
        registry=ProducerKeyRegistry(
            keys=[
                ProducerKey(
                    key_id="key-apalache",
                    producer_id="apalache",
                    trusted_for_high_assurance=False,
                )
            ]
        ),
        secrets_by_key_id={"key-apalache": "secret"},
    )
    missing_artifact = verify_replay_bundle(
        bundle_root=store_root,
        bundle=bundle.model_copy(
            update={
                "records": [
                    ArtifactRecord(
                        artifact_hash="sha256:missing",
                        logical_name="missing",
                        store_path="objects/mi/missing.json",
                        size_bytes=1,
                        metadata={
                            "evidence_level": "BOUNDED_CHECKED",
                            "producer_id": "apalache",
                        },
                    )
                ]
            }
        ),
        registry=registry,
        secrets_by_key_id={"key-apalache": "secret"},
    )

    assert valid.result == "valid"
    assert valid.verified_envelope_ids == ["env-apalache"]
    assert missing_producer.result == "blocked"
    assert missing_producer.findings[0].category == "producer"
    assert untrusted.result == "blocked"
    assert untrusted.findings[0].category == "signature"
    assert missing_artifact.result == "blocked"
    assert missing_artifact.missing_artifact_hashes == ["sha256:missing"]


def test_phase146_parallel_dispatch_reuses_cache_and_invalidates_changed_inputs() -> None:
    policy = VerificationCachePolicyV2(max_parallelism=2, ci_runtime_budget_ms=1_000)
    task = ParallelDispatchTask(
        task_id="formal-1",
        stage="formal_backend",
        input_hashes={"model": "sha256:model-a"},
        tool_versions={"apalache": "1.0"},
        estimated_runtime_ms=800,
    )
    cached_key = build_verification_cache_key(
        stage=task.stage,
        input_hashes=task.input_hashes,
        tool_versions=task.tool_versions,
        policy_hash=sha256_json(policy),
    )
    cache_index = record_cache_artifact(
        VerificationCacheIndex(),
        cached_key,
        artifact_hash="sha256:formal-result",
    )

    plan = build_parallel_dispatch_plan(
        plan_id="dispatch-ok",
        tasks=[
            task,
            task.model_copy(
                update={
                    "task_id": "trace-1",
                    "stage": "trace_validation",
                    "input_hashes": {"trace": "sha256:trace-a"},
                    "estimated_runtime_ms": 800,
                }
            ),
        ],
        cache_index=cache_index,
        policy=policy,
    )
    changed = build_parallel_dispatch_plan(
        plan_id="dispatch-changed",
        tasks=[
            task.model_copy(update={"input_hashes": {"model": "sha256:model-b"}})
        ],
        cache_index=cache_index,
        policy=policy,
    )
    over_budget = build_parallel_dispatch_plan(
        plan_id="dispatch-over-budget",
        tasks=[
            task.model_copy(update={"task_id": "a", "input_hashes": {"a": "sha256:a"}}),
            task.model_copy(update={"task_id": "b", "input_hashes": {"b": "sha256:b"}}),
            task.model_copy(update={"task_id": "c", "input_hashes": {"c": "sha256:c"}}),
        ],
        cache_index=VerificationCacheIndex(),
        policy=policy,
    )

    assert plan.result == "ready"
    assert plan.cache_hits == 1
    assert plan.cache_misses == 1
    assert changed.decisions[0].cache_status == "miss"
    assert over_budget.result == "blocked"
    assert over_budget.within_budget is False


def test_phase147_public_benchmark_report_blocks_false_closure_and_missing_leaderboard() -> None:
    corpus = _benchmark_corpus()
    base = build_benchmark_evaluation_report(
        corpus,
        [
            BenchmarkCaseResult(case_id="accepted", decision="accepted", runtime_ms=10),
            BenchmarkCaseResult(case_id="refused", decision="refused", runtime_ms=10),
        ],
    )
    dimensions = [
        ExtendedBenchmarkDimensionResult(
            dimension=dimension,
            total_cases=2,
            passed_cases=2,
            score=1.0,
        )
        for dimension in EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS
    ]
    extended = build_extended_benchmark_evaluation_report(base, dimensions)
    suite = PublicBenchmarkSuite(
        suite_id="real-evidence-public",
        version="0.2",
        dimensions=list(EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS),
        case_ids_by_dimension={
            dimension: ["accepted", "refused"]
            for dimension in EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS
        },
    )
    publishable = build_public_benchmark_release_report(
        suite=suite,
        base=base,
        extended=extended,
        leaderboard=[
            PublicLeaderboardEntry(
                runner_id="reference",
                report_hash=sha256_json(extended),
                score=1.0,
                result="passed",
            )
        ],
    )
    false_closure_base = build_benchmark_evaluation_report(
        corpus,
        [
            BenchmarkCaseResult(case_id="accepted", decision="accepted"),
            BenchmarkCaseResult(case_id="refused", decision="accepted"),
        ],
    )
    blocked = build_public_benchmark_release_report(
        suite=suite,
        base=false_closure_base,
        extended=extended,
        leaderboard=[],
    )

    assert publishable.result == "publishable"
    assert set(publishable.dimensions) == set(EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS)
    assert blocked.result == "blocked"
    assert any("false closure rate" in finding for finding in blocked.findings)
    assert "public leaderboard has no entries" in blocked.findings


def test_phase148_reference_brownfield_demo_requires_pilots_and_captured_findings() -> None:
    demo = _extended_demo()
    pilot = BetaPilotReport(
        pilot_id="pilot-a",
        participant="reference-team",
        workflow="pull-request-hard-gate",
        result="passed",
        requirements_exercised=["REQ-A", "REQ-R"],
        findings=[
            BetaPilotFinding(
                finding_id="latency-note",
                severity="minor",
                status="accepted",
                message="runtime budget is acceptable for the reference fixture",
            )
        ],
    )
    accepted = build_reference_brownfield_pilot_report(demo=demo, beta_pilots=[pilot])
    blocked = build_reference_brownfield_pilot_report(
        demo=demo,
        beta_pilots=[
            pilot.model_copy(
                update={
                    "findings": [
                        BetaPilotFinding(
                            finding_id="missing-replay",
                            severity="blocker",
                            status="open",
                            message="pilot could not replay a bundle",
                        )
                    ]
                }
            )
        ],
    )

    assert accepted.result == "accepted"
    assert accepted.release_findings
    assert blocked.result == "blocked"
    assert "unmitigated blocker" in blocked.blocking_findings[0]


def test_phase149_ci_policy_governance_requires_branch_protection_and_reviewed_policy() -> None:
    ci = build_ci_adoption_report(
        _accepted_extended_gate("REQ-GOV-001"),
        mode="hard_gate",
    )
    waiver_audit = build_waiver_audit_report(policy=GatePolicy(policy_id="release"), waivers=[])
    change = PolicyChangeRecord(
        change_id="policy-change-1",
        policy_hash="sha256:policy",
        previous_policy_hash="sha256:previous",
        reviewed_by="reviewer@example.invalid",
        reviewed_at="2026-06-03T00:00:00Z",
        rationale="Tighten release branch gate.",
    )

    passed = build_ci_policy_governance_report(
        governance_id="governance-ok",
        ci=ci,
        waiver_audit=waiver_audit,
        branch_protection_required_checks=["nlreq-real-evidence"],
        policy_changes=[change],
    )
    blocked = build_ci_policy_governance_report(
        governance_id="governance-blocked",
        ci=ci,
        waiver_audit=waiver_audit,
        branch_protection_required_checks=[],
        policy_changes=[change.model_copy(update={"reviewed_by": None})],
    )

    assert passed.result == "passed"
    assert blocked.result == "blocked"
    assert blocked.unreviewed_policy_changes == ["policy-change-1"]
    assert any("branch protection" in finding for finding in blocked.findings)


def test_phase150_final_certification_requires_all_real_evidence_inputs(tmp_path: Path) -> None:
    replay = _valid_replay_report(tmp_path)
    dispatch = build_parallel_dispatch_plan(
        plan_id="final-dispatch",
        tasks=[
            ParallelDispatchTask(
                task_id="adapter",
                stage="adapter_evidence",
                input_hashes={"adapter": "sha256:adapter"},
                tool_versions={"nlreq": "0.1"},
                estimated_runtime_ms=10,
            )
        ],
        cache_index=VerificationCacheIndex(),
        policy=VerificationCachePolicyV2(ci_runtime_budget_ms=100),
    )
    public_benchmark = _public_benchmark_report()
    demo = build_reference_brownfield_pilot_report(
        demo=_extended_demo(),
        beta_pilots=[
            BetaPilotReport(
                pilot_id="pilot-a",
                participant="reference-team",
                workflow="pull-request-hard-gate",
                result="passed",
                requirements_exercised=["REQ-A", "REQ-R"],
            )
        ],
    )
    governance = build_ci_policy_governance_report(
        governance_id="final-governance",
        ci=build_ci_adoption_report(_accepted_extended_gate("REQ-FINAL-001"), mode="hard_gate"),
        waiver_audit=build_waiver_audit_report(policy=GatePolicy(policy_id="release"), waivers=[]),
        branch_protection_required_checks=["nlreq-real-evidence"],
        policy_changes=[
            PolicyChangeRecord(
                change_id="policy-change-1",
                policy_hash="sha256:policy",
                reviewed_by="reviewer@example.invalid",
                reviewed_at="2026-06-03T00:00:00Z",
                rationale="Release governance lock.",
            )
        ],
    )
    cross_language = build_cross_language_causal_proof_object(
        proof=_closed_proof(),
        manifests=[_manifest("python-source", "python"), _manifest("solidity-source", "solidity")],
        traces=[_traces()],
        evidence=[
            AdapterEvidenceReference(
                evidence_id="py",
                adapter_id="python-source",
                artifact_hash="sha256:py",
                replay_bundle_hash="sha256:bundle",
            ),
            AdapterEvidenceReference(
                evidence_id="sol",
                adapter_id="solidity-source",
                artifact_hash="sha256:sol",
                replay_bundle_hash="sha256:bundle",
            ),
        ],
        causal_links=[
            CausalTraceLinkV2(
                link_id="py-to-sol",
                from_adapter_id="python-source",
                from_trace_id="py-trace",
                from_event_id="request",
                to_adapter_id="solidity-source",
                to_trace_id="sol-trace",
                to_event_id="settle",
                relation="causes",
            )
        ],
    )

    certified = build_final_real_evidence_conclusion_certification_report(
        release_id="real-evidence-1.0",
        cross_language=cross_language,
        replay=replay,
        dispatch=dispatch,
        public_benchmark=public_benchmark,
        reference_demo=demo,
        governance=governance,
        schemas_frozen=True,
        release_bundle_hash="sha256:release",
        signed_release_bundle_hash="sha256:signed-release",
    )
    blocked = build_final_real_evidence_conclusion_certification_report(
        release_id="real-evidence-1.0",
        cross_language=cross_language,
        replay=replay,
        dispatch=dispatch,
        public_benchmark=public_benchmark,
        reference_demo=demo,
        governance=governance,
        schemas_frozen=True,
        release_bundle_hash="sha256:release",
        signed_release_bundle_hash="sha256:signed-release",
        scaffold_evidence_hashes=["sha256:scaffold"],
    )

    assert certified.result == "certified"
    assert certified.blocking_findings == []
    assert blocked.result == "blocked"
    assert "no-scaffold-evidence: final certification cannot include scaffold evidence" in blocked.blocking_findings


def _closed_proof():
    ir = DslV2Parser().parse_ir(
        "For every redemption:\n"
        "when wallet is authorized\n"
        "then finalize_redemption must emit redemption_finalized within 6 hours.\n",
        requirement_id="REQ-G14-001",
        title="Cross language closure",
    )
    # This test isolates cross-language certification over a closed proof, not premise routing, so
    # it requests the legacy single-backend dispatch explicitly to close on one system_checker
    # verdict. The closure default now routes by kind, where a lone verdict would not close.
    return build_proof_object(
        requirement=ir,
        backend_results=[
            BackendResult(
                backend="system_checker",
                status="valid",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            )
        ],
        coverage=SpecCoverageReport(
            result="passed",
            threshold=1.0,
            covered_modules=1,
            total_modules=1,
            coverage_ratio=1.0,
        ),
        trace_alignment=TraceAlignmentReport(result="passed"),
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )


def _manifest(adapter: str, language: str) -> SourceManifest:
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": adapter,
            "language": language,
            "runtime": f"{language}-runtime",
            "modules": [
                {
                    "module_id": f"{language}:redemption",
                    "path": f"src/{language}/redemption",
                    "symbols": ["finalize_redemption"],
                }
            ],
        }
    )


def _traces() -> NormalizedTraceArtifact:
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "py-trace",
                "adapter_id": "python-source",
                "source_hash": "sha256:py",
                "language": "python",
                "events": [
                    {
                        "event_id": "request",
                        "timestamp": 1,
                        "action": "request_redemption",
                    }
                ],
            },
            {
                "trace_id": "sol-trace",
                "adapter_id": "solidity-source",
                "source_hash": "sha256:sol",
                "language": "solidity",
                "events": [
                    {
                        "event_id": "settle",
                        "timestamp": 2,
                        "action": "finalize_redemption",
                        "causal_predecessor": "py-trace:request",
                    }
                ],
            },
        ]
    )


def _benchmark_corpus() -> BenchmarkCorpus:
    return BenchmarkCorpus.model_validate(
        {
            "corpus_id": "real-evidence-public",
            "version": "0.2",
            "cases": [
                {
                    "case_id": "accepted",
                    "title": "Accepted",
                    "description": "accepted case",
                    "tags": ["semantic_translation", "formal_system"],
                    "expected": {"decision": "accepted"},
                },
                {
                    "case_id": "refused",
                    "title": "Refused",
                    "description": "refused case",
                    "tags": ["false_closure", "release_gate"],
                    "expected": {"decision": "refused", "counterexample_expected": True},
                },
            ],
        }
    )


def _public_benchmark_report():
    corpus = _benchmark_corpus()
    base = build_benchmark_evaluation_report(
        corpus,
        [
            BenchmarkCaseResult(case_id="accepted", decision="accepted", runtime_ms=10),
            BenchmarkCaseResult(
                case_id="refused",
                decision="refused",
                runtime_ms=10,
                counterexample_count=1,
            ),
        ],
    )
    dimensions = [
        ExtendedBenchmarkDimensionResult(
            dimension=dimension,
            total_cases=2,
            passed_cases=2,
            score=1.0,
        )
        for dimension in EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS
    ]
    extended = build_extended_benchmark_evaluation_report(base, dimensions)
    suite = PublicBenchmarkSuite(
        suite_id="real-evidence-public",
        version="0.2",
        dimensions=list(EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS),
    )
    return build_public_benchmark_release_report(
        suite=suite,
        base=base,
        extended=extended,
        leaderboard=[
            PublicLeaderboardEntry(
                runner_id="reference",
                report_hash=sha256_json(extended),
                score=1.0,
                result="passed",
            )
        ],
    )


def _reference_manifest() -> ReferenceDemoManifest:
    return ReferenceDemoManifest(
        demo_id="brownfield-reference",
        title="Brownfield reference",
        source_root="demo",
        requirements=[
            {
                "requirement_id": "REQ-A",
                "expected_decision": "accepted",
                "controlled_text_path": "requirements/REQ-A.nlreq",
                "expected_report_path": "reports/REQ-A.json",
            },
            {
                "requirement_id": "REQ-R",
                "expected_decision": "refused",
                "controlled_text_path": "requirements/REQ-R.nlreq",
                "expected_report_path": "reports/REQ-R.json",
            },
        ],
        system_specs=["specs/system.tla"],
        trace_artifacts=["traces/trace.json"],
        commands=[["nlreq", "gate", "demo"]],
    )


def _extended_demo():
    manifest = _reference_manifest()
    base = build_reference_demo_report(
        manifest,
        existing_paths={
            "demo",
            "requirements/REQ-A.nlreq",
            "requirements/REQ-R.nlreq",
            "reports/REQ-A.json",
            "reports/REQ-R.json",
            "specs/system.tla",
            "traces/trace.json",
        },
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "refused"},
    )
    return build_extended_reference_demo_report(
        manifest,
        base,
        gate_reports=[
            _accepted_extended_gate("REQ-A"),
            build_extended_requirement_gate_report(
                _base_gate("REQ-R", "refused", downstream_action_allowed=False),
                stage_statuses={**PASSED_EXTENDED_STAGE_STATUSES, "semantic_translation": "refused"},
            ),
        ],
        replay_bundle_hashes={"REQ-A": "sha256:bundle-a", "REQ-R": "sha256:bundle-r"},
    )


def _accepted_extended_gate(requirement_id: str):
    return build_extended_requirement_gate_report(
        _base_gate(requirement_id, "accepted", downstream_action_allowed=True),
        stage_statuses=PASSED_EXTENDED_STAGE_STATUSES,
    )


def _base_gate(
    requirement_id: str,
    decision: str,
    *,
    downstream_action_allowed: bool,
) -> EndToEndRequirementGateReport:
    return EndToEndRequirementGateReport(
        requirement_id=requirement_id,
        decision=decision,
        downstream_action="merge",
        downstream_action_allowed=downstream_action_allowed,
        proof_status="closed" if downstream_action_allowed else "open",
        closure_result="passed" if downstream_action_allowed else "blocked",
        statuses={
            "translation_agreement": "agreed",
            "requirement_self_consistency": "valid",
            "trace_alignment": "passed",
            "trace_replay": "passed",
            "system_consistency": "valid",
            "proof_object": "closed" if downstream_action_allowed else "open",
            "closure_gate": "passed" if downstream_action_allowed else "blocked",
        },
    )


def _valid_replay_report(tmp_path: Path):
    source = tmp_path / "release-evidence.json"
    source.write_text('{"result":"valid"}\n')
    store_root = tmp_path / "release-store"
    record = put_artifact(
        store_root=store_root,
        source_path=source,
        logical_name="release-evidence",
        metadata={
            "evidence_level": "BOUNDED_CHECKED",
            "producer_id": "apalache",
        },
    )
    envelope = sign_evidence_payload(
        payload={"artifact_hash": record.artifact_hash},
        producer_id="apalache",
        key_id="key-apalache",
        secret="secret",
        envelope_id="env-apalache",
    )
    bundle = build_replay_bundle_manifest_v2(
        bundle_id="release-bundle",
        source_store_id="release-store",
        command=ReplayCommandMetadata(command=["nlreq", "replay", "release-bundle"]),
        records=[record],
        signed_envelopes=[envelope],
    )
    return verify_replay_bundle(
        bundle_root=store_root,
        bundle=bundle,
        registry=ProducerKeyRegistry(
            keys=[
                ProducerKey(
                    key_id="key-apalache",
                    producer_id="apalache",
                    trusted_for_high_assurance=True,
                )
            ]
        ),
        secrets_by_key_id={"key-apalache": "secret"},
    )
