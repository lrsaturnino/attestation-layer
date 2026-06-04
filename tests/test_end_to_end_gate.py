import json
import sys
from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v3 import DslV3Parser
from nlreq.end_to_end_gate import build_proof_with_formal_claim_dispatch, run_end_to_end_requirement_gate
from nlreq.formal_backend import FormalBackendExecution
from nlreq.jsonutil import read_json
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.system_spec import SystemSpecRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_end_to_end_gate_accepts_closed_requirement(tmp_path: Path) -> None:
    manifest, registry = _project(tmp_path)

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-001",
        title="Requirement gate",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert report.decision == "accepted"
    assert report.downstream_action_allowed is True
    assert report.statuses["closure_gate"] == "passed"
    assert {artifact.name for artifact in report.artifacts} >= {
        "requirement_ir",
        "translation_agreement",
        "requirement_self_consistency",
        "source_impact",
        "spec_coverage",
        "trace_replay",
        "system_consistency",
        "delta_report",
        "proof_object",
        "closure_gate",
    }
    assert all(Path(artifact.path).is_file() for artifact in report.artifacts)


def test_build_proof_with_formal_claim_dispatch_uses_fragment_ids_for_classed_ir() -> None:
    """build_proof_with_formal_claim_dispatch must carry FormalClaim fragment IDs into the ProofObject.

    This tests the production entry point — not a manually-constructed dispatch plan — so the
    assertion that ProofObject.premises contain formal fragment IDs is not test-only wiring.
    With no backend results all premises are open; the test only verifies the IDs are present.
    """
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-FC-GATE",
        title="Authorization precondition (gate test)",
    )

    proof, formal_claim_report = build_proof_with_formal_claim_dispatch(
        requirement=ir,
        backend_results=[],
    )

    assert formal_claim_report.result == "lowered"
    assert formal_claim_report.formal_claim is not None
    premise_ids = {p.premise_id for p in proof.premises}
    for fragment in [*formal_claim_report.formal_claim.premises, *formal_claim_report.formal_claim.obligations]:
        assert fragment.fragment_id in premise_ids, (
            f"fragment {fragment.fragment_id} ({fragment.kind}) missing from ProofObject.premises"
        )
    # All premises open — no backend results were supplied
    assert all(p.status == "open" for p in proof.premises)


def test_end_to_end_gate_records_formal_claim_artifact(tmp_path: Path) -> None:
    """FormalClaim artifact must be recorded by the gate regardless of claim class support.

    DSL-v2 text without a supported requirement_class produces a 'refused' formal claim;
    the artifact is still recorded so downstream tooling can inspect why dispatch fell back
    to the default system-consistency plan.
    """
    manifest, registry = _project(tmp_path)

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-FC-001",
        title="Formal claim artifact test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert "formal_claim_artifact" in {artifact.name for artifact in report.artifacts}
    assert "formal_claim" in report.statuses
    # DSL-v2 text has no requirement_class annotation — formal claim is refused,
    # gate falls back to default dispatch and remains accepted
    assert report.statuses["formal_claim"] == "refused"
    assert report.decision == "accepted"


def test_end_to_end_gate_with_v3_requirement_has_formal_claim_fragment_ids(tmp_path: Path) -> None:
    """Full gate with a DSL v3 requirement carries FormalClaim fragment IDs into the ProofObject.

    This exercises the production code path: run_end_to_end_requirement_gate → FormalClaim
    dispatch → ProofObject. It is NOT the helper-only path from
    test_build_proof_with_formal_claim_dispatch_uses_fragment_ids_for_classed_ir.

    Predicate premises become "blocked" — smt_check_formal_claim_predicate_fragments returns
    "unsupported" for named predicates (requires Apalache/Pillar B); proof_closure maps
    "unsupported" → "blocked" so the status is explicit rather than silently "open".
    rejection_order obligations also become "blocked" for the same reason.
    """
    manifest, registry = _project(tmp_path)
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-GATE-V3-001",
        title="Authorization precondition (v3 gate test)",
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when actor is not authorized then operation must reject before state_change.",
        requirement_id="AUTH-GATE-V3-001",
        title="Authorization precondition (v3 gate test)",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts-v3",
        execution=_execution(tmp_path),
        requirement_ir=ir,
    )

    assert "formal_claim_artifact" in {artifact.name for artifact in report.artifacts}
    assert report.statuses["formal_claim"] == "lowered"

    # ProofObject must contain FormalClaim fragment IDs from the normal gate flow
    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    from nlreq.proof_closure import ProofObject
    from nlreq.jsonutil import read_json
    proof = ProofObject.model_validate(read_json(proof_path))
    premise_ids = {p.premise_id for p in proof.premises}
    # All premise IDs must be formal fragment IDs (start with "formal.")
    assert all(pid.startswith("formal.") for pid in premise_ids), (
        f"Expected formal fragment IDs in ProofObject but found: {premise_ids}"
    )

    # Predicate premises are "blocked": uninterpreted predicates have no fragment-level
    # SMT content and require Apalache/Pillar B model-level checking (S∧R composition).
    # smt_check_formal_claim_predicate_fragments emits "unsupported"/evidence_level=None,
    # which proof_closure maps to "blocked" with an explicit reason.
    predicate_premises = [p for p in proof.premises if p.node_kind == "predicate"]
    rejection_order = [p for p in proof.premises if p.node_kind == "rejection_order"]
    assert all(p.status == "blocked" for p in predicate_premises), (
        f"Predicate premises must be blocked (uninterpreted predicates require Apalache): "
        f"{predicate_premises}"
    )
    assert all(p.status == "blocked" for p in rejection_order), (
        f"rejection_order premises must be blocked (not silently open) without Apalache: "
        f"{rejection_order}"
    )

    # No producer-mapping blockers from intentionally-unsupported fragments.
    # Unsupported BackendResults must carry evidence_level=None so _producer_blockers
    # skips them, rather than emitting spurious "producer is not allowed to emit this
    # evidence level" blockers for core_smt / apalache backends.
    producer_mapping_blockers = [
        b for b in proof.blockers if b.category == "producer_mapping"
    ]
    assert not producer_mapping_blockers, (
        f"No producer-mapping blockers expected for intentionally-unsupported fragments, "
        f"got: {producer_mapping_blockers}"
    )


def test_end_to_end_gate_refuses_trace_replay_violation(tmp_path: Path) -> None:
    manifest, registry = _project(tmp_path, trace_actions=["finalize_redemption"])

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-002",
        title="Requirement gate refusal",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert report.decision == "refused"
    assert report.downstream_action_allowed is False
    assert any(blocker.stage == "trace_replay" for blocker in report.blockers)


def test_end_to_end_requirement_gate_cli_writes_report(tmp_path: Path, capsys) -> None:
    manifest, registry = _project(tmp_path)
    requirement_path = tmp_path / "requirement.nlreq2"
    manifest_path = tmp_path / "source-manifest.json"
    registry_path = tmp_path / "registry.json"
    out = tmp_path / "gate-report.json"
    requirement_path.write_text(DSL)
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "requirement-gate",
            str(requirement_path),
            "--requirement-id",
            "REQ-GATE-003",
            "--title",
            "Requirement gate CLI",
            "--source-manifest",
            str(manifest_path),
            "--source-language",
            "python",
            "--symbol",
            "finalize_redemption",
            "--registry",
            str(registry_path),
            "--project-root",
            str(tmp_path),
            "--artifact-dir",
            str(tmp_path / "gate-artifacts"),
            "--out",
            str(out),
            "--checker-id",
            "custom",
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Requirement gate report:" in output
    assert read_json(out)["decision"] == "accepted"


def test_gate_single_source_ir_yields_needs_review_not_agreed(tmp_path: Path) -> None:
    """When a single pre-parsed IR is supplied, translation agreement must be needs_review.

    The old implementation fabricated two identical candidates so the agreement was
    trivially 'agreed'. A single source cannot produce ensemble agreement — it should
    be 'needs_review' instead.
    """
    manifest, registry = _project(tmp_path)
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-SINGLE-001",
        title="Single source gate test",
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when actor is not authorized then operation must reject before state_change.",
        requirement_id="GATE-SINGLE-001",
        title="Single source gate test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-single-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=ir,
    )

    # Locate the translation_agreement artifact and assert it is needs_review.
    agreement_artifact = next(
        (a for a in report.artifacts if a.name == "translation_agreement"), None
    )
    assert agreement_artifact is not None, "translation_agreement artifact must be recorded"
    from nlreq.translator_agreement import TranslationAgreementReport

    agreement = TranslationAgreementReport.model_validate(read_json(Path(agreement_artifact.path)))
    assert agreement.status == "needs_review", (
        f"Single-source IR must yield needs_review, not {agreement.status!r}"
    )


def test_gate_refuses_on_disagreeing_translation_agreement_input(tmp_path: Path) -> None:
    """When a TranslationAgreementInput with genuinely different candidates is supplied,
    the gate must produce decision='refused' (not 'unknown' or 'accepted') and record
    a translation_refusal artifact with NLR-REFUSED-AMBIGUOUS.

    This exercises the full refuse_ambiguous_ensemble wiring: the gate calls it on
    disagreement and the decision propagates as a blocker.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    manifest, registry = _project(tmp_path)

    auth_req = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-DISAGREE-001",
        title="Auth candidate",
    )
    # A structurally distinct requirement (numeric_invariant has different claim_class).
    numeric_req = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\nscope reserve\nwhen reserve is confirmed\nthen keep collateral >= 100\n",
        requirement_id="GATE-DISAGREE-001",
        title="Numeric candidate",
    )
    disagreeing_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="candidate-auth",
                method="deterministic",
                requirement=auth_req,
                provenance={"source": "test"},
            ),
            TranslationCandidate(
                translator_id="candidate-numeric",
                method="deterministic",
                requirement=numeric_req,
                provenance={"source": "test"},
            ),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text="when actor is not authorized then operation must reject before state_change.",
        requirement_id="GATE-DISAGREE-001",
        title="Disagree gate test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-disagree-artifacts",
        execution=_execution(tmp_path),
        requirement_ir=auth_req,
        translation_agreement=disagreeing_input,
    )

    # Gate must be refused, not unknown or accepted.
    assert report.decision == "refused", (
        f"Disagreeing translation must produce refused decision, got {report.decision!r}"
    )
    assert report.downstream_action_allowed is False

    # A translation_refusal artifact with NLR-REFUSED-AMBIGUOUS must be recorded.
    refusal_artifact = next(
        (a for a in report.artifacts if a.name == "translation_refusal"), None
    )
    assert refusal_artifact is not None, "translation_refusal artifact must be recorded on disagreement"
    from nlreq.semantic_translation import SemanticTranslationReport

    refusal = SemanticTranslationReport.model_validate(read_json(Path(refusal_artifact.path)))
    assert refusal.refusal_code == "NLR-REFUSED-AMBIGUOUS", (
        f"Expected NLR-REFUSED-AMBIGUOUS, got {refusal.refusal_code!r}"
    )
    assert len(refusal.clarification_questions) >= 1

    # Provenance: gate must set a gate-scoped translation_id and carry input hashes.
    assert refusal.translation_id == "gate-translation-GATE-DISAGREE-001", (
        f"Gate refusal must carry gate-scoped translation_id, got {refusal.translation_id!r}"
    )
    assert "controlled_text" in refusal.input_hashes, (
        "Gate refusal must carry controlled_text hash in input_hashes"
    )
    assert "requirement_ir" in refusal.input_hashes, (
        "Gate refusal must carry requirement_ir hash in input_hashes"
    )

    # Fail-fast: no downstream artifacts must be produced after a disagreed translation.
    artifact_names = {a.name for a in report.artifacts}
    for downstream in ("formal_claim_artifact", "proof_object", "closure_gate", "lowered_formal"):
        assert downstream not in artifact_names, (
            f"Downstream artifact '{downstream}' must not be produced when translation disagreed"
        )


def test_gate_z3_neg_r_plus_s_refuses_on_counterexample(tmp_path: Path) -> None:
    """Z3 gate refusal: ¬R + S(pred=TRUE) → counterexample → gate refused.

    Mirrors test_z3_gate_neg_r_plus_s_returns_counterexample but drives the full
    run_end_to_end_requirement_gate.  ¬R has Pred_not_authorized; S assigns it TRUE.
    Z3 returns counterexample → system_consistency blocker → decision 'refused'.

    The translation_agreement supplies two matching candidates so the agreement is
    'agreed' and the solver refusal is the sole blocker (not masked as 'unknown').
    """
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "redemption.py").write_text(
        "def finalize_redemption(wallet):\n    return 'rejected'\n"
    )
    # S: Pred_not_authorized(a) == TRUE — ¬R's obligation predicate is TRUE, Z3 → counterexample.
    # SafetyInvariant makes S declare an invariant so the gate treats S ∧ R as applicable and
    # runs the solver; the Z3 in-process path decides from the Pred_* assignment, not the
    # invariant body.
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "SafetyInvariant == TRUE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1",
        "adapter_id": "raw-python",
        "source_hash": "sha256:x",
        "events": [
            {"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
             "action": "finalize_redemption", "post_state": {}},
        ],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1",
        "adapter": "python-source",
        "language": "python",
        "runtime": "cpython",
        "modules": [{
            "module_id": "redemption",
            "path": "src/redemption.py",
            "symbols": ["finalize_redemption"],
            "trace_sources": ["traces.json"],
        }],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{
            "spec_id": "spec:redemption",
            "module_ids": ["redemption"],
            "formalism": "tla",
            "path": "specs/SystemConstraint.tla",
            "version": "1",
            "review_status": "reviewed",
            "freshness": "fresh",
            "invariants": ["SafetyInvariant"],
        }],
    })
    neg_r_ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is not authorized then finalize_redemption must reject before rejected.",
        requirement_id="GATE-Z3-NEG-001",
        title="Negation gate Z3 test",
    )
    # Two matching candidates so translation_agreement status is 'agreed', not 'needs_review'.
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="neg-r-primary",
                method="deterministic",
                requirement=neg_r_ir,
                provenance={"source": "test"},
            ),
            TranslationCandidate(
                translator_id="neg-r-reparse",
                method="deterministic",
                requirement=neg_r_ir,
                provenance={"source": "test"},
            ),
        ]
    )

    # execution=None so self-consistency uses the default unsupported path (no TLA binary);
    # solver_execution="z3" drives the solver-backed S∧R check in-process via Z3.
    report = run_end_to_end_requirement_gate(
        controlled_text="when wallet is not authorized then finalize_redemption must reject before rejected.",
        requirement_id="GATE-Z3-NEG-001",
        title="Negation gate Z3 test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-z3-neg-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=neg_r_ir,
        translation_agreement=agreement,
    )

    assert report.decision == "refused", (
        f"¬R + Z3 S(pred=TRUE) must refuse; got decision={report.decision!r}, "
        f"blockers={[b.model_dump() for b in report.blockers]}"
    )
    system_blockers = [b for b in report.blockers if b.stage == "system_consistency"]
    assert system_blockers, (
        "Gate refusal must carry a system_consistency blocker"
    )
    assert system_blockers[0].status == "refused"


def test_gate_z3_execution_adds_smt_checked_solver_result_to_proof_object(tmp_path: Path) -> None:
    """Gate with Z3 positive path: solver returns valid/SMT_CHECKED and ProofObject carries it.

    Mirrors test_z3_gate_r_plus_s_returns_valid through the full gate.  The authorization_
    precondition IR has Pred_authorized; S assigns Pred_authorized(a) == FALSE (conservative
    constraint).  Z3 returns "valid" → evidence_level=SMT_CHECKED (in-process propositional
    check, not bounded model checking).  The result must appear in ProofObject.backend_results.
    """
    from nlreq.formal_backend import FormalBackendExecution
    from nlreq.proof_closure import ProofObject
    from nlreq.models import EvidenceLevel
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text(
        "def operation(actor):\n    return 'rejected'\n"
    )
    # Fixture: "when actor is not authorized then operation must reject" → predicate is
    # Pred_not_authorized.  S assigns Pred_not_authorized(a) == FALSE so the obligation
    # antecedent is never triggered → no violation reachable → Z3 UNSAT → "valid".
    # SafetyInvariant makes S declare an invariant so the gate runs the solver; the Z3
    # in-process path decides from the Pred_* assignment, not the invariant body.
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == FALSE\n"
        "SafetyInvariant == TRUE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh",
                   "invariants": ["SafetyInvariant"]}],
    })
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-Z3-POS-001",
        title="Z3 positive gate test",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="z3-pos-p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="z3-pos-r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=(FIXTURES / "authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-Z3-POS-001",
        title="Z3 positive gate test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-z3-pos-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    # The consolidated, solver-backed system-consistency artifact must be recorded.
    artifact_names = {a.name for a in report.artifacts}
    assert "system_consistency" in artifact_names, (
        "system_consistency artifact must be recorded (solver-backed when solver_execution='z3')"
    )

    # ProofObject must contain a valid solver_system_checker result with SMT_CHECKED.
    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    proof = ProofObject.model_validate(read_json(proof_path))
    solver_results = [r for r in proof.backend_results if r.backend == "solver_system_checker"]
    assert solver_results, (
        "ProofObject must carry at least one solver_system_checker backend result"
    )
    valid_solver = [r for r in solver_results if r.status == "valid"]
    assert valid_solver, (
        f"solver_system_checker result must be 'valid' for R + S(pred=FALSE); "
        f"got {[r.status for r in solver_results]}"
    )
    # Z3 in-process is propositional SMT — SMT_CHECKED, not BOUNDED_CHECKED.
    assert all(r.evidence_level == EvidenceLevel.SMT_CHECKED for r in valid_solver), (
        f"Valid solver results must carry SMT_CHECKED: {valid_solver}"
    )


def test_solver_status_recorded_in_gate_statuses(tmp_path: Path) -> None:
    """Solver status is recorded in report.statuses['system_consistency'].

    System consistency is solver-backed by default, so the base gate records the solver
    result status under the consolidated 'system_consistency' key (not a separate
    'solver_system_consistency' key) so the extended gate and callers can read it directly.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text("def operation(actor):\n    return 'rejected'\n")
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh",
                   "invariants": ["SafetyInvariant"]}],
    })
    # SafetyInvariant makes S declare an invariant so the gate treats S ∧ R as applicable and
    # runs the solver; with no Pred_* assignment for R's obligation predicate, the Z3 path
    # reports 'unsupported' — a recognized solver outcome recorded in report.statuses.
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-STATUS-001",
        title="Solver status recording test",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-STATUS-001",
        title="Solver status recording test",
        source_adapter=__import__("nlreq.python_source_adapter", fromlist=["PythonSourceLanguageAdapter"]).PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-status-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    assert "system_consistency" in report.statuses, (
        "report.statuses must contain 'system_consistency' (solver-backed by default)"
    )
    assert report.statuses["system_consistency"] in {"valid", "counterexample", "unsupported", "timeout", "not_applicable"}, (
        f"system_consistency must be a recognized solver outcome, "
        f"got {report.statuses['system_consistency']!r}"
    )


def test_solver_unsupported_produces_unknown_decision(tmp_path: Path) -> None:
    """Solver returning 'unsupported' produces an 'unknown' gate decision, not 'accepted'.

    An inconclusive solver run must NOT silently pass through to acceptance.
    The gate decision is 'unknown' so downstream consumers know checking was inconclusive
    and cannot treat the requirement as cleared.
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text("def operation(actor):\n    return 'rejected'\n")
    # S declares the InvariantHolds invariant (so the gate treats S ∧ R as applicable and
    # runs the solver) but defines no Pred_*(...) assignment for the Z3 in-process path to
    # ground R's obligation predicate on — so the Z3 checker returns 'unsupported'.
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "InvariantHolds == TRUE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh",
                   "invariants": ["InvariantHolds"]}],
    })
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-UNKNOWN-001",
        title="Solver unsupported → unknown decision",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-UNKNOWN-001",
        title="Solver unsupported → unknown decision",
        source_adapter=__import__("nlreq.python_source_adapter", fromlist=["PythonSourceLanguageAdapter"]).PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-unknown-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    system_status = report.statuses.get("system_consistency")
    # The spec has no Pred_* assignments → Z3 gate returns unsupported (predicates not assigned).
    assert system_status == "unsupported", (
        f"Expected system_consistency='unsupported' for spec without Pred_* assignments; "
        f"got {system_status!r}"
    )
    assert report.decision == "unknown", (
        f"Gate must be 'unknown' when solver returns 'unsupported'; got {report.decision!r}"
    )
    assert report.downstream_action_allowed is False, (
        "downstream_action_allowed must be False when gate is unknown"
    )
    unknown_blocker = next(
        (b for b in report.blockers if b.stage == "system_consistency"), None
    )
    assert unknown_blocker is not None, "Must have a system_consistency blocker"
    assert unknown_blocker.status == "unknown", (
        f"system_consistency blocker must be 'unknown'; got {unknown_blocker.status!r}"
    )


def test_extended_gate_s_and_r_composition_reads_solver_backed_system_consistency(
    tmp_path: Path,
) -> None:
    """_extended_gate_default_statuses maps s_and_r_composition from the consolidated,
    solver-backed system_consistency status.

    System consistency is solver-backed by default — there is no separate marker vs solver
    split to reconcile. The extended gate therefore reads s_and_r_composition directly from
    the single system_consistency status, surfacing whatever the solver produced
    (valid / counterexample / unsupported / timeout / not_applicable). No weaker marker
    result can mask a real solver outcome.
    """
    from nlreq.end_to_end_gate import (
        EndToEndRequirementGateReport,
        _extended_gate_default_statuses,
    )

    def _gate(system_consistency: str, *, decision: str) -> EndToEndRequirementGateReport:
        return EndToEndRequirementGateReport(
            requirement_id=f"TEST-{system_consistency.upper()}",
            decision=decision,
            downstream_action="merge",
            downstream_action_allowed=decision == "accepted",
            proof_status="closed" if decision == "accepted" else "blocked",
            closure_result="passed" if decision == "accepted" else "blocked",
            statuses={
                "system_consistency": system_consistency,
                "translation_agreement": "agreed",
                "requirement_self_consistency": "valid",
            },
        )

    # A solver counterexample is surfaced verbatim — never masked by a weaker result.
    assert (
        _extended_gate_default_statuses(_gate("counterexample", decision="refused"))[
            "s_and_r_composition"
        ]
        == "counterexample"
    )
    # An inconclusive run (unsupported) is surfaced as-is, not silently passed.
    assert (
        _extended_gate_default_statuses(_gate("unsupported", decision="unknown"))[
            "s_and_r_composition"
        ]
        == "unsupported"
    )
    # A verified 'valid' is surfaced as valid.
    assert (
        _extended_gate_default_statuses(_gate("valid", decision="accepted"))[
            "s_and_r_composition"
        ]
        == "valid"
    )
    # 'not_applicable' (no reviewed S relevant to the impact declares an invariant) is
    # surfaced as-is — a passing, non-blocking outcome distinct from a verified 'valid'.
    assert (
        _extended_gate_default_statuses(_gate("not_applicable", decision="accepted"))[
            "s_and_r_composition"
        ]
        == "not_applicable"
    )


def test_system_consistency_floor_baseline_only_for_consistent_outcomes() -> None:
    """_system_consistency_floor_baseline emits a system_checker / CONSISTENCY_CHECKED baseline
    only when the consolidated S ∧ R stage concluded consistency (valid) or that there is no
    obligation to discharge (not_applicable); a non-consistent verdict yields no baseline.

    The default proof dispatch routes system-consistency premises to the system_checker
    producer at the CONSISTENCY_CHECKED floor. A solver verdict is emitted under
    solver_system_checker at SMT_CHECKED / BOUNDED_CHECKED — a stronger level that does not
    match the floor route — so the baseline lets those premises close on the weaker claim the
    solver verdict subsumes. A counterexample / unsupported / timeout must NOT produce a
    baseline: the premises stay open so the gate blocks on the real result.
    """
    from nlreq.end_to_end_gate import _system_consistency_floor_baseline
    from nlreq.models import EvidenceLevel

    for consistent in ("valid", "not_applicable"):
        baseline = _system_consistency_floor_baseline(consistent)
        assert baseline is not None, f"{consistent} must yield a floor baseline"
        assert baseline.backend == "system_checker"
        assert baseline.status == "valid"
        assert baseline.evidence_level == EvidenceLevel.CONSISTENCY_CHECKED
        assert baseline.details["mode"] == (
            "not_applicable" if consistent == "not_applicable" else "solver_backed_baseline"
        )

    for non_consistent in ("counterexample", "unsupported", "timeout", "invalid", "needs_review"):
        assert _system_consistency_floor_baseline(non_consistent) is None, (
            f"{non_consistent} must NOT yield a floor baseline"
        )


def test_solver_result_carries_related_fragment_ids_and_predicates_stay_blocked(tmp_path: Path) -> None:
    """Solver S∧R result carries related_fragment_ids; predicate routes stay blocked.

    The solver result (backend='solver_system_checker') must carry the fragment IDs of
    all formal claim fragments as traceability metadata ('related', not 'covered' —
    the solver encodes obligation predicate names, not each fragment class independently).
    Predicate and rejection_order fragment routes must remain blocked — adding
    related_fragment_ids must NOT discharge those routes (wrong backend + wrong evidence
    level vs the core_smt/apalache routes that formal_claim routing requires).
    """
    from nlreq.dsl_v3 import DslV3Parser
    from nlreq.proof_closure import ProofObject
    from nlreq.jsonutil import read_json
    from nlreq.translator_agreement import TranslationAgreementInput, TranslationCandidate
    from nlreq.python_source_adapter import PythonSourceLanguageAdapter

    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "operation.py").write_text("def operation(actor):\n    return 'rejected'\n")
    (specs / "SystemConstraint.tla").write_text(
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps([{
        "trace_id": "T1", "adapter_id": "raw-python", "source_hash": "sha256:x",
        "events": [{"event_id": "e1", "timestamp": "2026-06-01T00:00:01Z",
                    "action": "operation", "post_state": {}}],
    }]))
    manifest = SourceManifest.model_validate({
        "schema_version": "0.1", "adapter": "python-source",
        "language": "python", "runtime": "cpython",
        "modules": [{"module_id": "redemption", "path": "src/operation.py",
                     "symbols": ["operation"], "trace_sources": ["traces.json"]}],
    })
    registry = SystemSpecRegistry.model_validate({
        "schema_version": "0.1",
        "specs": [{"spec_id": "spec:redemption", "module_ids": ["redemption"],
                   "formalism": "tla", "path": "specs/SystemConstraint.tla",
                   "version": "1", "review_status": "reviewed", "freshness": "fresh"}],
    })
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-FRAG-001",
        title="Fragment binding test",
    )
    agreement = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(translator_id="p", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
            TranslationCandidate(translator_id="r", method="deterministic",
                                 requirement=ir, provenance={"source": "test"}),
        ]
    )

    report = run_end_to_end_requirement_gate(
        controlled_text=FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="GATE-FRAG-001",
        title="Fragment binding test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["operation"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-frag-artifacts",
        solver_execution=FormalBackendExecution(checker_id="z3"),
        requirement_ir=ir,
        translation_agreement=agreement,
    )

    proof_path = Path(next(a.path for a in report.artifacts if a.name == "proof_object"))
    proof = ProofObject.model_validate(read_json(proof_path))

    # Solver result must carry related_fragment_ids (provenance traceability).
    solver_results = [r for r in proof.backend_results if r.backend == "solver_system_checker"]
    assert solver_results, "ProofObject must carry solver_system_checker backend result"
    solver_with_ids = [r for r in solver_results if "related_fragment_ids" in r.details]
    assert solver_with_ids, (
        "Solver result must carry related_fragment_ids for provenance traceability"
    )
    fragment_ids_in_solver = solver_with_ids[0].details["related_fragment_ids"]
    assert len(fragment_ids_in_solver) > 0, "related_fragment_ids must be non-empty"

    # Predicate and rejection_order premises must stay blocked — not discharged by the solver.
    # formal_claim routes require an exact backend match (core_smt/apalache) so
    # solver_system_checker results cannot discharge them.
    predicate_premises = [
        p for p in proof.premises
        if p.node_kind in {"predicate", "rejection_order"}
    ]
    for premise in predicate_premises:
        assert premise.status == "blocked", (
            f"Predicate/rejection_order premise {premise.premise_id!r} must stay 'blocked' "
            f"even with solver result present; got {premise.status!r}. "
            "Solver results must not discharge formal_claim-routed premises via related_fragment_ids."
        )


def _project(
    tmp_path: Path,
    *,
    trace_actions: list[str] | None = None,
) -> tuple[SourceManifest, SystemSpecRegistry]:
    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "redemption.py").write_text(
        "def finalize_redemption(wallet):\n"
        "    if wallet.authorized:\n"
        "        return 'redemption_finalized'\n"
        "    return 'rejected'\n"
    )
    (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\n====\n")
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps(_trace_payload(trace_actions or [
        "finalize_redemption",
        "redemption_finalized",
    ])))
    manifest = SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "redemption",
                    "path": "src/redemption.py",
                    "symbols": ["finalize_redemption"],
                    "trace_sources": ["traces.json"],
                }
            ],
        }
    )
    registry = SystemSpecRegistry.model_validate(
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
    return manifest, registry


def _trace_payload(actions: list[str]) -> list[dict[str, object]]:
    return [
        {
            "trace_id": "TRACE-GATE-001",
            "adapter_id": "raw-python",
            "source_hash": "sha256:source",
            "events": [
                {
                    "event_id": f"evt-{index}",
                    "timestamp": f"2026-06-01T00:00:0{index}Z",
                    "action": action,
                    "post_state": (
                        {"collateral": 150, "reserve_floor": 100}
                        if action == "redemption_finalized"
                        else {}
                    ),
                }
                for index, action in enumerate(actions, start=1)
            ],
        }
    ]


def _execution(tmp_path: Path) -> FormalBackendExecution:
    return FormalBackendExecution(
        checker_id="custom",
        command=[sys.executable, "-c", "print('verification successful')"],
        artifact_dir=(tmp_path / "formal-self-check").as_posix(),
    )
