import json
import sys
from pathlib import Path

from nlreq.cli import main
from nlreq.counterexample_normalization import (
    explain_counterexamples,
    normalize_backend_counterexamples,
)
from nlreq.dsl_v2 import DslV2Parser
from nlreq.dsl_v3 import DslV3Parser
from nlreq.evidence_boundary import (
    ProofArtifactRef,
    build_proof_producing_backend_boundary_report,
)
from nlreq.formal_backend import (
    FormalBackendBudget,
    FormalBackendExecution,
    build_formal_backend_request,
    check_formal_backend,
)
from nlreq.formal_claim import (
    build_formal_claim,
    build_formal_claim_semantics_completion_reference,
)
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import BackendResult, EvidenceLevel, RequirementIRV2
from nlreq.proof_closure import default_evidence_producer_mapping
from nlreq.system_checker import check_solver_backed_system_consistency
from nlreq.system_composition import build_s_and_r_composition_report
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import lower_ir_v2_to_tla
from nlreq.verification_budget import (
    build_verification_budget_report,
    classify_budgeted_outcome,
)


DSL_V2 = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)

DSL_V3_STATE_PRECONDITION = (
    "requirement state_precondition:\n"
    "scope operation\n"
    "when actor is approved\n"
    "then operation must succeed\n"
)


def test_phase124_formal_claim_semantics_reference_is_complete(tmp_path: Path, capsys) -> None:
    reference = build_formal_claim_semantics_completion_reference()

    assert reference.result == "complete"
    assert {entry.claim_class for entry in reference.claim_classes} == {
        "authorization_precondition",
        "state_precondition",
        "state_postcondition",
        "numeric_invariant",
        "event_state_correspondence",
        "bounded_temporal",
        "cross_module_causal_obligation",
    }
    causal = next(
        entry
        for entry in reference.claim_classes
        if entry.claim_class == "cross_module_causal_obligation"
    )
    assert "causal_transition" in causal.supported_fragment_kinds
    assert EvidenceLevel.BOUNDED_CHECKED in causal.required_evidence

    out = tmp_path / "semantics.json"
    exit_code = main(["formal-claim-semantics", "--out", str(out)])

    assert exit_code == 0
    assert "Formal claim semantics reference:" in capsys.readouterr().out
    assert json.loads(out.read_text())["result"] == "complete"


def test_phase125_apalache_records_symbolic_profile_and_non_success_outcomes(tmp_path: Path) -> None:
    valid = check_formal_backend(
        build_formal_backend_request(
            _ir(),
            # Classless DSL v2 input — opt into the legacy skeleton so the backend has a module to
            # run (the live path refuses an absent requirement_class).
            legacy_skeleton=True,
            backend_id="apalache",
            budget=FormalBackendBudget(timeout_seconds=5, max_depth=14),
            execution=FormalBackendExecution(
                checker_id="custom-apalache",
                command=[sys.executable, "-c", "print('The outcome is: NoError')"],
                # A recorded run version backs the bounded claim; without it the producer
                # self-gates the level to None (see the unbacked cases below).
                tool_version="apalache 0.58.0",
                artifact_dir=(tmp_path / "apalache-valid").as_posix(),
            ),
        )
    )
    timeout = check_formal_backend(
        build_formal_backend_request(
            _ir(),
            # Classless DSL v2 input — opt into the legacy skeleton so the backend has a module to
            # run (the live path refuses an absent requirement_class).
            legacy_skeleton=True,
            backend_id="apalache",
            execution=FormalBackendExecution(
                checker_id="custom-apalache",
                command=[sys.executable, "-c", "print('Timed out while checking')"],
                artifact_dir=(tmp_path / "apalache-timeout").as_posix(),
            ),
        )
    )
    missing = check_formal_backend(
        build_formal_backend_request(
            _ir(),
            # Classless DSL v2 input — opt into the legacy skeleton so the backend has a module to
            # run (the live path refuses an absent requirement_class).
            legacy_skeleton=True,
            backend_id="apalache",
            execution=FormalBackendExecution(
                checker_id="custom-apalache",
                command=["definitely-missing-nlreq-apalache"],
                artifact_dir=(tmp_path / "apalache-missing").as_posix(),
            ),
        )
    )

    assert valid.result.status == "valid"
    assert valid.result.evidence_level == EvidenceLevel.BOUNDED_CHECKED
    assert valid.result.details["evidence_flavor"] == "symbolic_bounded"
    assert valid.result.details["bounds"]["max_depth"] == 14
    assert timeout.result.status == "timeout"
    assert timeout.result.evidence_level is None
    assert missing.result.status == "unsupported"
    assert missing.result.details["tool_missing"] is True


def test_phase126_tlc_records_explicit_state_counterexample(tmp_path: Path) -> None:
    response = check_formal_backend(
        build_formal_backend_request(
            _ir(),
            # Classless DSL v2 input — opt into the legacy skeleton so the backend has a module to
            # run (the live path refuses an absent requirement_class).
            legacy_skeleton=True,
            backend_id="tlc",
            execution=FormalBackendExecution(
                checker_id="custom-tlc",
                command=[sys.executable, "-c", "print('Invariant Foo is violated.')"],
                # A recorded run version backs the bounded claim; a counterexample found within
                # the bounds is BOUNDED_CHECKED evidence of a violation only when it is backed.
                tool_version="tlc 2.18",
                artifact_dir=(tmp_path / "tlc").as_posix(),
            ),
        )
    )

    assert response.result.status == "counterexample"
    assert response.result.evidence_level == EvidenceLevel.BOUNDED_CHECKED
    assert response.result.details["evidence_flavor"] == "explicit_state_bounded"
    assert response.result.details["counterexamples"][0]["marker"] == "is violated"


def test_phase127_s_and_r_composition_report_records_backend_artifacts(tmp_path: Path) -> None:
    # A reviewed system spec S is composed into the lowered requirement R; a stub checker
    # exercises the report plumbing over the real composed S ∧ R module.
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "RedemptionSystem.tla").write_text(
        "---- MODULE RedemptionSystem ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        '\\* System invariant: authorization defaults closed.\n'
        'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
        "====\n"
    )
    registry = SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/RedemptionSystem.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "invariants": ["SystemDefaultsClosed"],
                }
            ],
        }
    )

    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-M11-127",
        title="S and R composition",
    )
    lowered = lower_ir_v2_to_tla(ir)
    consistency = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=registry,
        impact=_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=5, max_depth=12),
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )
    report = build_s_and_r_composition_report(
        requirement=ir,
        lowered=lowered,
        registry=registry,
        impact=_impact(),
        project_root=tmp_path,
        consistency=consistency,
    )

    assert report.result == "valid"
    assert {artifact.kind for artifact in report.composition_artifacts} == {
        "backend_result",
        "tla_module",
        "tla_config",
    }
    # The composition records the real conjoined invariants, not the retired tautology.
    assert report.preserved_invariants == ["RequirementHolds", "SystemDefaultsClosed"]
    assert report.blockers == []


def test_phase128_counterexample_explanation_maps_formal_claim_spans(tmp_path: Path) -> None:
    response = check_formal_backend(
        build_formal_backend_request(
            _ir(),
            # Classless DSL v2 input — opt into the legacy skeleton so the backend has a module to
            # run (the live path refuses an absent requirement_class).
            legacy_skeleton=True,
            backend_id="apalache",
            execution=FormalBackendExecution(
                checker_id="custom-apalache",
                command=[sys.executable, "-c", "print('Counterexample: action violates property')"],
                artifact_dir=(tmp_path / "apalache-cex").as_posix(),
            ),
        )
    )
    normalization = normalize_backend_counterexamples([response])
    formal_claim_report = build_formal_claim(
        DslV3Parser().parse_ir(
            DSL_V3_STATE_PRECONDITION,
            requirement_id="REQ-M11-128",
            title="Counterexample explanation",
        )
    )
    report = explain_counterexamples(
        normalization,
        formal_claim=formal_claim_report.formal_claim,
        backend_responses=[response],
    )

    assert report.result == "explained"
    explanation = report.explanations[0]
    assert explanation.backend == "apalache"
    assert explanation.source_mappings
    assert "Counterexample" in explanation.markdown
    assert explanation.next_actions


def test_phase129_budget_outcomes_have_closure_effects() -> None:
    budget = build_verification_budget_report(_ir(), requirement_class="system_compatibility")

    valid = classify_budgeted_outcome(
        requirement_id="REQ-M11-129",
        budget_report=budget,
        backend_result=BackendResult(backend="apalache", status="valid"),
    )
    timeout = classify_budgeted_outcome(
        requirement_id="REQ-M11-129",
        budget_report=budget,
        backend_result=BackendResult(backend="apalache", status="timeout"),
    )
    unknown = classify_budgeted_outcome(
        requirement_id="REQ-M11-129",
        budget_report=budget,
        backend_result=BackendResult(backend="apalache", status="invalid"),
    )
    review = classify_budgeted_outcome(
        requirement_id="REQ-M11-129",
        budget_report=budget,
        backend_result=BackendResult(backend="apalache", status="unsupported"),
    )

    assert valid.closure_effect == "allow"
    assert timeout.outcome == "timeout"
    assert timeout.closure_effect == "block"
    assert unknown.outcome == "unknown"
    assert unknown.closure_effect == "block"
    assert review.outcome == "inconclusive"
    assert review.closure_effect == "review"


def test_phase130_proof_producing_boundary_blocks_fake_inductive_claims() -> None:
    mapping = default_evidence_producer_mapping()
    # The result carries well-formed checked-proof + proof-assistant + command metadata (passes the
    # construction guard) but its producer is not a registered proof assistant and no retained
    # checked_proof artifact or checker command is supplied to the boundary; the emission-boundary
    # report must still block the claim (defense in depth).
    fake = build_proof_producing_backend_boundary_report(
        backend_result=BackendResult(
            backend="apalache",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={
                "proof_artifact_sha256": "sha256:" + "a" * 64,
                "proof_assistant": "apalache",
                "command": ["apalache-mc", "check", "--inductive-invariant=Inv", "Spec.tla"],
            },
        ),
        producer_mapping=mapping,
    )
    checked = build_proof_producing_backend_boundary_report(
        backend_result=BackendResult(
            backend="tlaps",
            status="valid",
            evidence_level=EvidenceLevel.PROVEN_INDUCTIVE,
            details={
                "proof_artifact_sha256": "sha256:" + "c" * 64,
                "proof_assistant": "tlaps",
                "command": ["tlapm", "Proof.tla"],
            },
        ),
        producer_mapping=mapping,
        proof_artifacts=[
            ProofArtifactRef(
                artifact_id="checked",
                kind="checked_proof",
                sha256="sha256:" + "c" * 64,
            )
        ],
        checker_command=["tlapm", "Proof.tla"],
    )
    bounded = build_proof_producing_backend_boundary_report(
        backend_result=BackendResult(
            backend="tlc",
            status="valid",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={
                "bounds": {"max_depth": 10},
                "command": ["java", "-cp", "tla2tools.jar", "tlc2.TLC", "Model.tla"],
                "tool_version": "tlc 2.18",
            },
        ),
        producer_mapping=mapping,
    )

    assert fake.result == "blocked"
    assert any(finding.severity == "blocking" for finding in fake.findings)
    assert checked.result == "accepted"
    assert bounded.result == "accepted"
    assert "cannot claim PROVEN_INDUCTIVE" in bounded.findings[0].message


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(DSL_V2, requirement_id="REQ-M11-001", title="Group 11")


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def _registry(tmp_path: Path) -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Redemption.tla").write_text(
        "---- MODULE Redemption ----\nRedemptionInvariant == TRUE\n====\n"
    )
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
