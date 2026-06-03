import hashlib
import json
from pathlib import Path

from nlreq.cli import main
from nlreq.coverage_alignment import (
    CodeSpecCoverageManifestV2,
    SpecCoverageReport,
    build_code_spec_coverage_gate_report_v2,
)
from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.jsonutil import read_json
from nlreq.models import NormalizedTraceArtifact, RequirementIRV2
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.runtime_trace_sdk import (
    TraceExtractionRequest,
    TraceProducerRegistration,
    TraceProducerRegistry,
    build_trace_producer_evidence_report,
    producer_from_registry,
)
from nlreq.source_adapter import SourceManifest
from nlreq.source_impact import (
    SemanticImpactSuggestion,
    analyze_production_source_impact,
)
from nlreq.spec_drift import CodeSpecManifest
from nlreq.spec_extraction import (
    build_spec_extraction_workbench_report,
    build_specula_extraction_integration_report,
    promote_candidate_spec_with_review,
    reject_candidate_spec,
)
from nlreq.spec_freshness import (
    SpecFreshnessDriftCiReport,
    build_spec_freshness_lockfile_v2,
    validate_spec_freshness_lockfile_v2,
)
from nlreq.system_spec import SystemSpecRegistry
from nlreq.trace_replay import TraceReplayReport
from nlreq.trace_validation import build_trace_validation_gate_report


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_phase131_production_source_impact_separates_gateable_and_review_inputs(
    tmp_path: Path,
) -> None:
    manifest = _source_project(tmp_path)
    adapter = PythonSourceLanguageAdapter(project_root=tmp_path)

    report = analyze_production_source_impact(
        adapter,
        manifest,
        symbols=["operation"],
        traces=_impact_traces(),
        semantic_suggestions=[
            SemanticImpactSuggestion(module_id="billing", reason="semantic hint", source="llm")
        ],
    )
    blocked = analyze_production_source_impact(
        adapter,
        manifest,
        symbols=["missing_symbol"],
    )

    assert report.deterministic_modules == ["auth", "state"]
    assert report.trace_touched_modules == ["audit"]
    assert report.affected_modules == ["audit", "auth", "state"]
    assert report.closure_effect == "review"
    assert any(finding.category == "semantic_suggestion" for finding in report.findings)
    assert blocked.closure_effect == "block"
    assert blocked.findings[0].category == "unresolved_symbol"


def test_phase132_coverage_manifest_v2_blocks_candidates_and_dependency_gaps() -> None:
    report = build_code_spec_coverage_gate_report_v2(
        impact=_impact(["redemption", "wallet"]),
        manifest=CodeSpecCoverageManifestV2.model_validate(
            {
                "schema_version": "0.2",
                "entries": [
                    {
                        "module_id": "redemption",
                        "spec_ids": ["spec:redemption"],
                        "review_status": "reviewed",
                        "coverage_level": "full",
                        "coverage_ratio": 1.0,
                        "freshness": "fresh",
                        "dependency_module_ids": ["wallet"],
                    },
                    {
                        "module_id": "wallet",
                        "spec_ids": ["candidate:wallet"],
                        "review_status": "candidate",
                        "coverage_level": "full",
                        "coverage_ratio": 1.0,
                        "freshness": "unknown",
                    },
                ],
            }
        ),
    )

    statuses = {status.module_id: status for status in report.modules}
    assert report.result == "blocked"
    assert statuses["wallet"].status == "candidate"
    assert statuses["redemption"].status == "dependency_gap"


def test_phase133_freshness_ci_blocks_changed_specs_and_expired_validation(
    tmp_path: Path,
) -> None:
    source_hash = _write_file(tmp_path / "redemption.py", "def finalize(): return True\n")
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_file(specs / "Redemption.tla", "---- MODULE Redemption ----\n====\n")
    manifest = _code_spec_manifest({"redemption.py": source_hash})
    registry = _registry(tmp_path)
    lockfile = build_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        project_root=tmp_path,
        validated_at="2026-06-01T00:00:00Z",
    )

    (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\nChanged == TRUE\n====\n")
    stale = validate_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        lockfile=lockfile,
        project_root=tmp_path,
        now="2026-06-03T00:00:00Z",
    )
    expired = validate_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        lockfile=lockfile,
        project_root=tmp_path,
        now="2026-06-03T00:00:00Z",
        max_validation_age_hours=1,
    )

    assert stale.result == "blocked"
    assert stale.statuses[0].changed_specs == ["spec:redemption"]
    assert expired.closure_effect == "block"


def test_phase134_specula_extraction_is_candidate_only_until_trace_review() -> None:
    blocked = build_specula_extraction_integration_report(
        requirement=_ir(),
        impact=_impact(["redemption"]),
        registry=SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": []}),
        project_root=Path("."),
    )
    grounded = build_specula_extraction_integration_report(
        requirement=_ir(),
        impact=_impact(["redemption"]),
        registry=SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": []}),
        project_root=Path("."),
        trace_replay=TraceReplayReport(
            requirement_id="REQ-M12-001",
            result="passed",
            observations=[],
        ),
    )

    assert blocked.result == "blocked"
    assert blocked.candidates[0].review_status == "draft"
    assert blocked.structural_validations[0].status == "valid"
    assert "trace validation has not passed" in blocked.blockers[0]
    assert grounded.result == "candidates"
    assert grounded.trust_boundary == "candidate_only"


def test_phase135_candidate_review_promotion_is_hash_bound_and_rejections_audit() -> None:
    candidate = build_spec_extraction_workbench_report(
        requirement=_ir(),
        impact=_impact(["redemption"]),
        registry=SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": []}),
        project_root=Path("."),
        trace_replay=TraceReplayReport(
            requirement_id="REQ-M12-001",
            result="passed",
            observations=[],
        ),
    ).candidates[0]

    stale = promote_candidate_spec_with_review(
        candidate,
        approved_hash="sha256:wrong",
        version="1",
        reviewer_id="reviewer-a",
        reviewed_at="2026-06-03T00:00:00Z",
    )
    promoted = promote_candidate_spec_with_review(
        candidate,
        approved_hash=candidate.content_hash,
        version="1",
        reviewer_id="reviewer-a",
        reviewed_at="2026-06-03T00:00:00Z",
    )
    rejected = reject_candidate_spec(
        candidate,
        reviewer_id="reviewer-b",
        reviewed_at="2026-06-03T00:00:00Z",
        rejection_reasons=["candidate invariant is too weak"],
    )

    assert stale.decision == "blocked"
    assert promoted.decision == "promoted"
    assert promoted.promoted_spec is not None
    assert promoted.promoted_spec.review_status == "reviewed"
    assert rejected.decision == "rejected"
    assert rejected.rejection_reasons == ["candidate invariant is too weak"]


def test_phase136_trace_producer_evidence_blocks_lossy_high_assurance_traces(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(_traces(lossy=True).model_dump_json())
    registry = TraceProducerRegistry(
        producers=[
            TraceProducerRegistration(
                producer_id="trace:python",
                adapter_id="python-source",
                language="python",
                runtime="cpython",
                produces_normalized_schema="0.1",
                signing_key_id="trace-key",
            )
        ]
    )
    producer = producer_from_registry(registry, "trace:python")
    extraction = producer.extract(
        TraceExtractionRequest(
            producer_id="trace:python",
            trace_source="traces.json",
            run_id="RUN-M12-136",
        ),
        project_root=tmp_path,
    )
    report = build_trace_producer_evidence_report(
        registration=registry.producers[0],
        result=extraction,
        high_assurance=True,
        require_signature=True,
    )

    assert extraction.status == "extracted"
    assert extraction.replay_input_hashes
    assert report.result == "blocked"
    assert "lossy traces" in report.blockers[0]


def test_phase137_trace_validation_gate_distinguishes_grounding_from_blockers(
    tmp_path: Path,
    capsys,
) -> None:
    satisfied = build_trace_validation_gate_report(
        requirement=_ir(),
        traces=_traces(),
        coverage=_coverage(),
    )
    lossy = build_trace_validation_gate_report(
        requirement=_ir(),
        traces=_traces(lossy=True),
        coverage=_coverage(),
    )
    stale = build_trace_validation_gate_report(
        requirement=_ir(),
        traces=_traces(),
        coverage=_coverage(),
        freshness=SpecFreshnessDriftCiReport.model_validate(
            {
                "schema_version": "0.2",
                "result": "blocked",
                "closure_effect": "block",
                "statuses": [
                    {
                        "module_id": "redemption",
                        "status": "stale",
                        "closure_effect": "block",
                        "reason": "source changed",
                    }
                ],
            }
        ),
    )

    assert satisfied.result == "satisfied"
    assert satisfied.evidence_label == "trace_grounding"
    assert lossy.outcomes[0].status == "lossy"
    assert stale.outcomes[0].status == "stale"

    ir_path = tmp_path / "requirement.ir.json"
    traces_path = tmp_path / "traces.json"
    coverage_path = tmp_path / "coverage.json"
    out = tmp_path / "trace-gate.json"
    ir_path.write_text(_ir().model_dump_json())
    traces_path.write_text(_traces().model_dump_json())
    coverage_path.write_text(_coverage().model_dump_json())

    exit_code = main(
        [
            "trace-validation-gate",
            "--requirement-ir",
            str(ir_path),
            "--trace-artifact",
            str(traces_path),
            "--coverage",
            str(coverage_path),
            "--out",
            str(out),
        ]
    )

    assert exit_code == 0
    assert "Trace validation gate report:" in capsys.readouterr().out
    assert read_json(out)["evidence_label"] == "trace_grounding"


def _source_project(tmp_path: Path) -> SourceManifest:
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    return state_change()\n"
    )
    (src / "state.py").write_text("def state_change():\n    return 'changed'\n")
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "auth",
                    "path": "src/auth.py",
                    "symbols": ["operation"],
                },
                {
                    "module_id": "state",
                    "path": "src/state.py",
                    "symbols": ["state_change"],
                },
            ],
        }
    )


def _impact(modules: list[str]) -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=modules,
    )


def _impact_traces() -> NormalizedTraceArtifact:
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "TRACE-M12-IMPACT",
                "adapter_id": "python-source",
                "source_hash": "sha256:trace",
                "events": [
                    {
                        "event_id": "evt-1",
                        "timestamp": "2026-06-03T00:00:00Z",
                        "action": "audit_log",
                        "metadata": {"module_id": "audit"},
                    }
                ],
            }
        ]
    )


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-M12-001", title="Group 12")


def _coverage(*, result: str = "passed") -> SpecCoverageReport:
    return SpecCoverageReport(
        result=result,
        threshold=1.0,
        covered_modules=1 if result == "passed" else 0,
        total_modules=1,
        coverage_ratio=1.0 if result == "passed" else 0.0,
    )


def _traces(*, lossy: bool = False) -> NormalizedTraceArtifact:
    return NormalizedTraceArtifact.model_validate(
        [
            {
                "trace_id": "TRACE-M12-001",
                "adapter_id": "python-source",
                "source_hash": "sha256:trace-source",
                "events": [
                    {
                        "event_id": "evt-action",
                        "timestamp": "2026-06-03T00:00:00Z",
                        "action": "finalize_redemption",
                    },
                    {
                        "event_id": "evt-finalized",
                        "timestamp": "2026-06-03T00:00:01Z",
                        "action": "redemption_finalized",
                        "post_state": {"collateral": 150, "reserve_floor": 100},
                        "metadata": {"lossy_normalization": True} if lossy else {},
                    },
                ],
                "metadata": {"lossy_normalization": lossy},
            }
        ]
    )


def _write_file(path: Path, content: str) -> str:
    path.write_text(content)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _code_spec_manifest(source_hashes: dict[str, str]) -> CodeSpecManifest:
    return CodeSpecManifest.model_validate(
        {
            "schema_version": "0.1",
            "entries": [
                {
                    "module_id": "redemption",
                    "source_paths": list(source_hashes),
                    "spec_ids": ["spec:redemption"],
                    "recorded_source_hashes": source_hashes,
                }
            ],
        }
    )


def _registry(tmp_path: Path) -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )
