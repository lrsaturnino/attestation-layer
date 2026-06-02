from nlreq.benchmark_corpus import BenchmarkCaseResult, BenchmarkCorpus
from nlreq.benchmark_reporting import (
    EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS,
    ExtendedBenchmarkDimensionResult,
    build_benchmark_evaluation_report,
    build_extended_benchmark_evaluation_report,
)
from nlreq.ci_pr_gate import build_ci_adoption_report
from nlreq.conclusion_certification import build_extended_conclusion_certification_report
from nlreq.end_to_end_gate import (
    EXTENDED_GATE_REQUIRED_STAGES,
    EndToEndRequirementGateReport,
    build_extended_requirement_gate_report,
)
from nlreq.public_sdk import (
    REQUIRED_PUBLIC_DOC_TOPICS,
    build_default_public_documentation_index,
    build_public_documentation_freeze_report,
    validate_public_documentation_index,
)
from nlreq.reference_demo import (
    ReferenceDemoManifest,
    build_extended_reference_demo_report,
    build_reference_demo_report,
)
from nlreq.threat_model import (
    REQUIRED_RELEASE_ARTIFACTS,
    build_default_threat_model,
    build_extended_tcb_review_report,
)


PASSED_EXTENDED_STAGE_STATUSES = {
    "controlled_intake": "approved",
    "semantic_translation": "accepted",
    "formal_claim": "lowered",
    "requirement_self_consistency": "valid",
    "s_and_r_composition": "valid",
    "spec_freshness": "fresh",
    "trace_validation": "satisfied",
    "adapter_evidence": "certified",
    "proof_closure": "closed",
    "release_action_gate": "passed",
}


def test_phase110_extended_gate_requires_real_pipeline_stages() -> None:
    accepted = build_extended_requirement_gate_report(
        _base_gate("REQ-G9-GATE-001", "accepted", downstream_action_allowed=True),
        stage_statuses=PASSED_EXTENDED_STAGE_STATUSES,
    )
    missing = build_extended_requirement_gate_report(
        _base_gate("REQ-G9-GATE-001", "accepted", downstream_action_allowed=True),
        stage_statuses={
            key: value
            for key, value in PASSED_EXTENDED_STAGE_STATUSES.items()
            if key != "adapter_evidence"
        },
    )

    assert accepted.decision == "accepted"
    assert accepted.downstream_action_allowed is True
    assert accepted.artifact_layout_version == "extended-release-v1"
    assert accepted.required_stage_count == len(EXTENDED_GATE_REQUIRED_STAGES)
    assert missing.decision == "unknown"
    assert missing.downstream_action_allowed is False
    assert "adapter_evidence" in {stage.stage for stage in missing.stages if stage.status == "missing"}


def test_phase111_ci_adoption_modes_preserve_stable_json_and_hard_blocking() -> None:
    gate = build_extended_requirement_gate_report(
        _base_gate("REQ-G9-CI-001", "unknown", downstream_action_allowed=False),
        stage_statuses={
            **PASSED_EXTENDED_STAGE_STATUSES,
            "s_and_r_composition": "timeout",
        },
    )

    report_only = build_ci_adoption_report(gate, mode="report_only")
    hard_gate = build_ci_adoption_report(gate, mode="hard_gate")

    assert report_only.result == "reported"
    assert report_only.enforcement == "none"
    assert hard_gate.result == "blocked"
    assert hard_gate.enforcement == "blocking"
    assert hard_gate.stable_json_hash.startswith("sha256:")
    assert "machine_result" in hard_gate.blocked_checks
    assert hard_gate.pr_markdown is not None
    assert "Stable JSON hash" in hard_gate.pr_markdown


def test_phase112_extended_benchmark_requires_release_dimensions() -> None:
    base = _passing_benchmark()
    dimensions = [
        ExtendedBenchmarkDimensionResult(
            dimension=dimension,
            total_cases=2,
            passed_cases=2,
            score=1.0,
        )
        for dimension in EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS
    ]

    passed = build_extended_benchmark_evaluation_report(
        base,
        dimensions,
        release_thresholds={"runtime": 0.95},
    )
    missing = build_extended_benchmark_evaluation_report(base, dimensions[:-1])
    failed_threshold = build_extended_benchmark_evaluation_report(
        base,
        [
            item.model_copy(update={"score": 0.5}) if item.dimension == "runtime" else item
            for item in dimensions
        ],
        release_thresholds={"runtime": 0.95},
    )

    assert passed.result == "passed"
    assert missing.result == "failed"
    assert missing.missing_dimensions == ["counterexample_quality"]
    assert failed_threshold.result == "failed"
    assert failed_threshold.failed_dimensions == ["runtime"]


def test_phase113_reference_demo_uses_extended_gate_reports_and_replay_bundles() -> None:
    manifest = _reference_demo_manifest()
    base_demo = build_reference_demo_report(
        manifest,
        existing_paths=_demo_paths(),
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "refused"},
    )
    accepted_gate = build_extended_requirement_gate_report(
        _base_gate("REQ-A", "accepted", downstream_action_allowed=True),
        stage_statuses=PASSED_EXTENDED_STAGE_STATUSES,
    )
    refused_gate = build_extended_requirement_gate_report(
        _base_gate("REQ-R", "refused", downstream_action_allowed=False),
        stage_statuses={
            **PASSED_EXTENDED_STAGE_STATUSES,
            "semantic_translation": "refused",
        },
    )

    report = build_extended_reference_demo_report(
        manifest,
        base_demo,
        gate_reports=[accepted_gate, refused_gate],
        replay_bundle_hashes={"REQ-A": "sha256:bundle-a", "REQ-R": "sha256:bundle-r"},
    )
    missing_bundle = build_extended_reference_demo_report(
        manifest,
        base_demo,
        gate_reports=[accepted_gate, refused_gate],
        replay_bundle_hashes={"REQ-A": "sha256:bundle-a"},
    )

    assert report.result == "reproducible"
    assert report.stage_failures == []
    assert missing_bundle.result == "blocked"
    assert missing_bundle.missing_replay_bundles == ["REQ-R"]


def test_phase114_public_docs_freeze_requires_topics_schemas_and_commitments() -> None:
    index = build_default_public_documentation_index(version="0.2")
    existing_paths = {doc.path for doc in index.docs} | {example.path for example in index.examples}
    existing_schemas = {schema_ref for doc in index.docs for schema_ref in doc.schema_refs}
    coverage = validate_public_documentation_index(
        index,
        existing_paths=existing_paths,
        existing_schemas=existing_schemas,
    )
    frozen_schema_hashes = {schema: f"sha256:{schema}" for schema in existing_schemas}

    passed = build_public_documentation_freeze_report(
        index,
        coverage,
        frozen_schema_hashes=frozen_schema_hashes,
        covered_topics=list(REQUIRED_PUBLIC_DOC_TOPICS),
        compatibility_commitments=["CLI and schema contracts are frozen for the release."],
    )
    blocked = build_public_documentation_freeze_report(
        index,
        coverage,
        frozen_schema_hashes=frozen_schema_hashes,
        covered_topics=["evidence_labels"],
        compatibility_commitments=[],
    )

    assert passed.result == "passed"
    assert blocked.result == "blocked"
    assert "limitations" in blocked.missing_topics
    assert any("compatibility commitments" in finding for finding in blocked.findings)


def test_phase115_extended_tcb_review_requires_release_artifacts_and_residual_risks() -> None:
    threat_model = build_default_threat_model()
    release_artifacts = {
        artifact: f"sha256:{artifact}"
        for artifact in REQUIRED_RELEASE_ARTIFACTS
    }
    accepted_risks = [scenario.residual_risk for scenario in threat_model.scenarios]

    complete = build_extended_tcb_review_report(
        threat_model,
        release_artifact_hashes=release_artifacts,
        accepted_residual_risks=accepted_risks,
    )
    missing = build_extended_tcb_review_report(
        threat_model,
        release_artifact_hashes={},
        accepted_residual_risks=[],
    )

    assert complete.result == "complete"
    assert complete.evidence_attack_scenarios
    assert missing.result == "needs_review"
    assert set(REQUIRED_RELEASE_ARTIFACTS).issubset(set(missing.missing_release_artifacts))


def test_phase116_extended_certification_certifies_only_complete_release_evidence() -> None:
    gate = build_extended_requirement_gate_report(
        _base_gate("REQ-G9-CERT-001", "accepted", downstream_action_allowed=True),
        stage_statuses=PASSED_EXTENDED_STAGE_STATUSES,
    )
    ci = build_ci_adoption_report(gate, mode="hard_gate")
    benchmark = build_extended_benchmark_evaluation_report(
        _passing_benchmark(),
        [
            ExtendedBenchmarkDimensionResult(
                dimension=dimension,
                total_cases=2,
                passed_cases=2,
                score=1.0,
            )
            for dimension in EXTENDED_BENCHMARK_REQUIRED_DIMENSIONS
        ],
    )
    manifest = _reference_demo_manifest()
    base_demo = build_reference_demo_report(
        manifest,
        existing_paths=_demo_paths(),
        actual_decisions_by_requirement={"REQ-A": "accepted", "REQ-R": "refused"},
    )
    demo = build_extended_reference_demo_report(
        manifest,
        base_demo,
        gate_reports=[
            build_extended_requirement_gate_report(
                _base_gate("REQ-A", "accepted", downstream_action_allowed=True),
                stage_statuses=PASSED_EXTENDED_STAGE_STATUSES,
            ),
            build_extended_requirement_gate_report(
                _base_gate("REQ-R", "refused", downstream_action_allowed=False),
                stage_statuses={
                    **PASSED_EXTENDED_STAGE_STATUSES,
                    "semantic_translation": "refused",
                },
            ),
        ],
        replay_bundle_hashes={"REQ-A": "sha256:bundle-a", "REQ-R": "sha256:bundle-r"},
    )
    index = build_default_public_documentation_index(version="0.2")
    existing_paths = {doc.path for doc in index.docs} | {example.path for example in index.examples}
    existing_schemas = {schema_ref for doc in index.docs for schema_ref in doc.schema_refs}
    docs = build_public_documentation_freeze_report(
        index,
        validate_public_documentation_index(
            index,
            existing_paths=existing_paths,
            existing_schemas=existing_schemas,
        ),
        frozen_schema_hashes={schema: f"sha256:{schema}" for schema in existing_schemas},
        covered_topics=list(REQUIRED_PUBLIC_DOC_TOPICS),
        compatibility_commitments=["Public schema and CLI compatibility is frozen."],
    )
    threat_model = build_default_threat_model()
    tcb = build_extended_tcb_review_report(
        threat_model,
        release_artifact_hashes={
            artifact: f"sha256:{artifact}"
            for artifact in REQUIRED_RELEASE_ARTIFACTS
        },
        accepted_residual_risks=[scenario.residual_risk for scenario in threat_model.scenarios],
    )

    certified = build_extended_conclusion_certification_report(
        release_id="extended-conclusion-0.2",
        gate=gate,
        ci=ci,
        benchmark=benchmark,
        demo=demo,
        docs=docs,
        tcb_review=tcb,
        schemas_frozen=True,
        producer_evidence_present=True,
        release_bundle_hash="sha256:release-bundle",
        signed_release_bundle_hash="sha256:signed-release-bundle",
    )
    blocked = build_extended_conclusion_certification_report(
        release_id="extended-conclusion-0.2",
        gate=gate,
        ci=build_ci_adoption_report(gate, mode="soft_gate"),
        benchmark=benchmark,
        demo=demo,
        docs=docs,
        tcb_review=tcb,
        schemas_frozen=False,
        producer_evidence_present=False,
        release_bundle_hash=None,
    )

    assert certified.result == "certified"
    assert certified.blocking_findings == []
    assert blocked.result == "blocked"
    assert any(finding.startswith("ci-adoption:") for finding in blocked.blocking_findings)
    assert "schema-freeze: schema freeze evidence was not provided" in blocked.blocking_findings
    assert "producer-evidence: producer evidence validation was not provided" in blocked.blocking_findings
    assert "release-bundle: release bundle hash was not provided" in blocked.blocking_findings


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


def _passing_benchmark():
    corpus = BenchmarkCorpus.model_validate(
        {
            "corpus_id": "extended-release",
            "version": "0.2",
            "cases": [
                {
                    "case_id": "accepted",
                    "title": "Accepted",
                    "description": "accepted case",
                    "tags": ["positive-closure", "semantic_translation", "formal_system"],
                    "expected": {"decision": "accepted"},
                },
                {
                    "case_id": "refused",
                    "title": "Refused",
                    "description": "refused case",
                    "tags": ["false-closure-risk", "trace_grounding", "adapter_evidence"],
                    "expected": {"decision": "refused"},
                },
            ],
        }
    )
    return build_benchmark_evaluation_report(
        corpus,
        [
            BenchmarkCaseResult(case_id="accepted", decision="accepted"),
            BenchmarkCaseResult(case_id="refused", decision="refused"),
        ],
    )


def _reference_demo_manifest() -> ReferenceDemoManifest:
    return ReferenceDemoManifest.model_validate(
        {
            "demo_id": "extended-demo",
            "title": "Extended Reference Demo",
            "source_root": "demo",
            "system_specs": ["demo/specs/Auth.tla"],
            "trace_artifacts": ["demo/traces/auth.json"],
            "commands": [["nlreq", "requirement-gate", "requirements/REQ-A.nlreq3"]],
            "requirements": [
                {
                    "requirement_id": "REQ-A",
                    "expected_decision": "accepted",
                    "controlled_text_path": "requirements/REQ-A.nlreq3",
                    "expected_report_path": "reports/REQ-A.gate.json",
                },
                {
                    "requirement_id": "REQ-R",
                    "expected_decision": "refused",
                    "controlled_text_path": "requirements/REQ-R.nlreq3",
                    "expected_report_path": "reports/REQ-R.gate.json",
                },
            ],
            "reproducibility_notes": ["Run the checked-in replay scripts."],
        }
    )


def _demo_paths() -> set[str]:
    return {
        "demo",
        "demo/specs/Auth.tla",
        "demo/traces/auth.json",
        "requirements/REQ-A.nlreq3",
        "requirements/REQ-R.nlreq3",
        "reports/REQ-A.gate.json",
        "reports/REQ-R.gate.json",
    }
