import json
from pathlib import Path

from nlreq.backend_agreement import build_backend_agreement_report
from nlreq.cli import main
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.dsl_v2 import DslV2Parser
from nlreq.formal_backend import FormalBackendResponse
from nlreq.jsonutil import read_json
from nlreq.models import BackendResult, EvidenceLevel
from nlreq.proof_closure import build_proof_dispatch_plan, build_proof_object


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_backend_agreement_passes_matching_overlapping_results() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner"),
            _bounded_result("alloy-runner"),
        ]
    )

    assert report.status == "agreed"
    assert report.closure_effect == "allow"
    assert report.comparisons[0].status == "agreed"


def test_backend_agreement_blocks_status_and_bound_disagreement() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", max_depth=8),
            _bounded_result("alloy-runner", status="counterexample", max_depth=6),
        ]
    )

    assert report.status == "disagreed"
    assert report.closure_effect == "block"
    assert report.comparisons[0].status == "disagreed"
    assert "status differs" in report.comparisons[0].reasons[0]
    assert "bounds differ" in report.comparisons[0].reasons


def test_backend_agreement_blocks_counterexample_disagreement() -> None:
    report = build_backend_agreement_report(
        [
            _bounded_result(
                "tla-runner",
                status="counterexample",
                counterexample={"state": "wallet_authorized"},
            ),
            _bounded_result(
                "alloy-runner",
                status="counterexample",
                counterexample={"state": "wallet_locked"},
            ),
        ]
    )

    assert report.status == "disagreed"
    assert "counterexamples differ" in report.comparisons[0].reasons


def test_backend_agreement_records_non_overlap_without_comparison() -> None:
    """Two backends that declare different questions (different overlap_keys) do not overlap. That
    is the absence of a shared question, not a disagreement, so the report is non-blocking
    (closure_effect="allow") with no blockers — the reason lives on the comparison itself."""
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", overlap_key="bounded-safety"),
            _bounded_result("lean-runner", overlap_key="inductive-safety"),
        ]
    )

    assert report.status == "non_overlap"
    assert report.closure_effect == "allow"
    assert report.blockers == []
    assert report.comparisons[0].status == "non_overlap"
    assert "overlap_key differs" in report.comparisons[0].reasons[0]


def test_report_only_policy_downgrades_disagreement_to_report() -> None:
    """Under report_only, even a real disagreement does not block: closure_effect is "report_only"
    rather than "block", so a consumer that honors closure_effect records it without refusing."""
    report = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", max_depth=8),
            _bounded_result("alloy-runner", status="counterexample", max_depth=6),
        ],
        policy="report_only",
    )

    assert report.status == "disagreed"
    assert report.closure_effect == "report_only"
    assert report.blockers  # the disagreement reasons are still recorded for the report


def test_backend_agreement_cli_writes_report_from_formal_responses(
    tmp_path: Path, capsys
) -> None:
    left = FormalBackendResponse(
        backend_id="tla-runner",
        target="tla",
        result=_bounded_result("tla-runner"),
    )
    right = FormalBackendResponse(
        backend_id="alloy-runner",
        target="alloy",
        result=_bounded_result("alloy-runner"),
    )
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    out = tmp_path / "agreement.json"
    left_path.write_text(json.dumps(left.model_dump(mode="json"), indent=2))
    right_path.write_text(json.dumps(right.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "backend-agreement",
            "--formal-backend-response",
            str(left_path),
            "--formal-backend-response",
            str(right_path),
            "--overlap-key",
            "bounded-safety",
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Backend agreement report:" in output
    assert read_json(out)["status"] == "agreed"


def test_proof_object_blocks_supplied_backend_disagreement() -> None:
    ir = DslV2Parser().parse_ir(DSL, requirement_id="REQ-BACKEND-AGREE", title="Backend agree")
    disagreement = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", status="valid"),
            _bounded_result("alloy-runner", status="counterexample"),
        ]
    )

    # Isolate the agreement gate: the legacy single-backend plan (requested explicitly) discharges
    # the premises on the one system_checker verdict, so the proof blocks specifically on the
    # backend-agreement disagreement, not on incidentally-open per-kind premises.
    proof = build_proof_object(
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
        backend_agreement=disagreement,
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )

    assert proof.status == "blocked"
    assert proof.backend_agreement is not None
    assert any(blocker.category == "backend_agreement" for blocker in proof.blockers)


def _proof_with_agreement(requirement_id: str, agreement):
    """A proof object built over the DSL requirement with a passing context and the given
    agreement report supplied — isolating whether the agreement gates closure.

    The legacy single-backend plan is requested explicitly so the premises discharge on the one
    system_checker verdict: whether the proof closes then turns solely on the agreement report,
    not on incidentally-open per-kind premises (the closure default now routes by kind)."""
    ir = DslV2Parser().parse_ir(DSL, requirement_id=requirement_id, title="Agreement policy")
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
        backend_agreement=agreement,
        dispatch=build_proof_dispatch_plan(ir, backend_id="system_checker"),
    )


def test_proof_object_does_not_block_non_overlap_backend_agreement() -> None:
    """A non_overlap agreement report must NOT block proof closure (PB-6.T3 production policy).

    A non_overlap report (the pair declared no shared question) is the absence of a cross-backend
    question, not a disagreement, so build_backend_agreement_report marks it closure_effect="allow".
    A requirement with no comparison/membership premise poses no cross-backend question — its
    overlap_key is None — and refusing it for that would over-block every such requirement. Only an
    opposite-verdict "disagreed" gates closure; this is the deliberate mirror of
    test_proof_object_blocks_supplied_backend_disagreement."""
    non_overlap = build_backend_agreement_report(
        [
            _bounded_result("tla-runner", overlap_key="left-question"),
            _bounded_result("alloy-runner", overlap_key="right-question"),
        ]
    )
    assert non_overlap.status == "non_overlap"
    assert non_overlap.closure_effect == "allow"

    proof = _proof_with_agreement("REQ-NON-OVERLAP", non_overlap)

    assert proof.backend_agreement is not None
    assert not any(blocker.category == "backend_agreement" for blocker in proof.blockers)
    assert proof.status == "closed"


def test_proof_object_does_not_block_needs_review_backend_agreement() -> None:
    """A needs_review agreement report (fewer than two backends decided — e.g. cvc5 is not
    installed) must NOT block proof closure. There is no second opinion to cross-check, which is
    not a disagreement; the single backend's per-premise results still flow through normal
    closure, so the absent cross-check is additive, not a missing discharge."""
    needs_review = build_backend_agreement_report([_bounded_result("tla-runner")])
    assert needs_review.status == "needs_review"
    assert needs_review.closure_effect == "allow"

    proof = _proof_with_agreement("REQ-NEEDS-REVIEW", needs_review)

    assert proof.backend_agreement is not None
    assert not any(blocker.category == "backend_agreement" for blocker in proof.blockers)
    assert proof.status == "closed"


def test_verdict_mode_agrees_on_matching_verdict() -> None:
    """Two backends that decide the same question the same way (both valid) agree and allow closure —
    even though they are different backends with different evidence metadata."""
    report = build_backend_agreement_report(
        [_verdict_result("core_smt", "valid"), _verdict_result("cvc5", "valid")],
        mode="verdict",
    )
    assert report.status == "agreed"
    assert report.closure_effect == "allow"
    assert report.comparisons[0].compared_fields == ["status"]


def test_verdict_mode_blocks_opposite_verdict() -> None:
    """The PB-6.T3 gate: opposite verdicts on the same question (the same overlap_key) is a real
    encoder divergence — it blocks, and the reason is the verdict mismatch, nothing else."""
    report = build_backend_agreement_report(
        [_verdict_result("core_smt", "valid"), _verdict_result("cvc5", "invalid")],
        mode="verdict",
    )
    assert report.status == "disagreed"
    assert report.closure_effect == "block"
    assert report.comparisons[0].status == "disagreed"
    assert "verdict differs" in report.comparisons[0].reasons[0]
    assert report.comparisons[0].compared_fields == ["status"]


def test_verdict_mode_ignores_evidence_and_bounds_when_verdict_agrees() -> None:
    """Verdict-first: when the verdict agrees, an evidence-level or bounds difference does NOT block.

    The same two observations under the bounded comparison DO block on those differences — so this
    pins that the gate fails only on a semantic verdict mismatch, not on encoder incidentals, which
    is the whole point of judging two independent SMT encoders on the same decidable question."""
    left = _verdict_result(
        "core_smt", "valid", evidence=EvidenceLevel.SMT_CHECKED, bounds={"max_depth": 5}
    )
    right = _verdict_result(
        "cvc5", "valid", evidence=EvidenceLevel.CONSISTENCY_CHECKED, bounds={"max_depth": 99}
    )

    verdict = build_backend_agreement_report([left, right], mode="verdict")
    assert verdict.status == "agreed"
    assert verdict.closure_effect == "allow"

    bounded = build_backend_agreement_report([left, right], mode="bounded")
    assert bounded.status == "disagreed"
    assert any("evidence_level differs" in reason for reason in bounded.comparisons[0].reasons)
    assert "bounds differ" in bounded.comparisons[0].reasons


def test_verdict_mode_non_overlap_when_a_backend_did_not_decide() -> None:
    """A backend that did not decide a verdict (needs_review / unsupported) is not a disagreement —
    there is nothing to agree about, so the pair is non_overlap, never a false block."""
    report = build_backend_agreement_report(
        [_verdict_result("core_smt", "valid"), _verdict_result("cvc5", "unsupported", evidence=None)],
        mode="verdict",
    )
    assert report.comparisons[0].status == "non_overlap"
    assert "did not decide a verdict" in report.comparisons[0].reasons[0]


def _verdict_result(
    backend: str,
    status: str,
    *,
    overlap_key: str = "premise-consistency-question",
    evidence: EvidenceLevel | None = EvidenceLevel.SMT_CHECKED,
    bounds: dict[str, int] | None = None,
) -> BackendResult:
    details: dict = {
        "overlap_key": overlap_key,
        "agreement_compare": "verdict",
        "check": "premise_consistency",
    }
    if bounds is not None:
        details["bounds"] = bounds
    return BackendResult(
        backend=backend,
        status=status,  # type: ignore[arg-type]
        evidence_level=evidence,
        details=details,
    )


def _bounded_result(
    backend: str,
    *,
    status: str = "valid",
    overlap_key: str = "bounded-safety",
    max_depth: int = 8,
    counterexample: dict[str, str] | None = None,
) -> BackendResult:
    details = {
        "overlap_key": overlap_key,
        "bounds": {"max_depth": max_depth},
        # A BOUNDED_CHECKED result carries its full run backing (bounds + command + a
        # run-recorded version); these are real backed results compared for agreement.
        "command": ["apalache-mc", "check", "Model.tla"],
        "tool_version": "apalache 0.58.0",
        "unsupported_constructs": [],
    }
    if counterexample is not None:
        details["counterexample"] = counterexample
    return BackendResult(
        backend=backend,
        status=status,  # type: ignore[arg-type]
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details=details,
    )
