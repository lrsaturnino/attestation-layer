import json
from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.dsl_v3 import DslV3Parser
from nlreq.models import Approval, RequirementIRV2
from nlreq.translator_agreement import (
    TranslationAgreementInput,
    TranslationCandidate,
    build_translation_agreement_report,
    structural_signature_json,
)


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_translation_agreement_accepts_structurally_equal_candidates() -> None:
    agreement_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="parser-a",
                method="deterministic",
                requirement=_ir(),
            ),
            TranslationCandidate(
                translator_id="parser-b",
                method="manual",
                requirement=_ir(),
            ),
        ]
    )

    report = build_translation_agreement_report(agreement_input)

    assert report.status == "agreed"
    assert report.disagreements == []
    assert sorted(report.candidate_hashes) == ["parser-a", "parser-b"]


def test_translation_agreement_refuses_material_disagreement() -> None:
    agreement_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="parser-a",
                method="deterministic",
                requirement=_ir(),
            ),
            TranslationCandidate(
                translator_id="parser-b",
                method="deterministic",
                requirement=_ir_with_temporal_bound(7),
            ),
        ]
    )

    report = build_translation_agreement_report(agreement_input)

    assert report.status == "disagreed"
    assert "temporal_bound.value" in report.disagreements[0].path
    assert report.clarifications[0].translator_ids == ["parser-a", "parser-b"]


def test_translation_agreement_blocks_unapproved_llm_candidate() -> None:
    agreement_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="parser",
                method="deterministic",
                requirement=_ir(),
            ),
            TranslationCandidate(
                translator_id="llm",
                method="llm",
                requirement=_ir(),
            ),
        ]
    )

    report = build_translation_agreement_report(agreement_input)

    assert report.status == "needs_review"
    assert report.blockers == ["LLM candidate llm requires explicit approval"]


def test_translation_agreement_allows_reviewed_llm_candidate() -> None:
    agreement_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="parser",
                method="deterministic",
                requirement=_ir(),
            ),
            TranslationCandidate(
                translator_id="llm",
                method="llm",
                requirement=_ir(),
                approval=Approval(
                    status="approved",
                    approved_by="reviewer@example.invalid",
                    approved_at="2026-06-01T00:00:00Z",
                ),
            ),
        ]
    )

    report = build_translation_agreement_report(agreement_input)

    assert report.status == "agreed"


def test_translation_agreement_cli_writes_report(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "agreement-input.json"
    out = tmp_path / "agreement-report.json"
    agreement_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="parser-a",
                method="deterministic",
                requirement=_ir(),
            ),
            TranslationCandidate(
                translator_id="parser-b",
                method="manual",
                requirement=_ir(),
            ),
        ]
    )
    input_path.write_text(agreement_input.model_dump_json())

    exit_code = main(["translator-agreement", str(input_path), "--out", str(out)])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Translator agreement report:" in output
    assert json.loads(out.read_text())["status"] == "agreed"


def test_structural_signature_ignores_provenance_noise() -> None:
    first = TranslationCandidate(
        translator_id="first",
        method="deterministic",
        requirement=_ir(),
    )
    second = TranslationCandidate(
        translator_id="second",
        method="deterministic",
        requirement=_ir(),
        provenance={"note": "different provenance"},
    )

    assert structural_signature_json(first) == structural_signature_json(second)


# ---------------------------------------------------------------------------
# FormalClaim-signature based comparison (PA-5)
# Uses DSL v3 requirements that lower to a FormalClaim for alpha+commutative comparison.
# ---------------------------------------------------------------------------


_DSL_V3_AUTH = (
    "requirement authorization_precondition:\n"
    "scope operation\n"
    "when actor is not authorized\n"
    "then operation must reject before state_change\n"
)

# Same scope/action/target structure as _DSL_V3_AUTH; only the operand identifier
# names differ (actor→user, state_change→state_update). alpha_identifiers=True
# normalises operand identifiers to positional placeholders, so these are alpha-equivalent.
_DSL_V3_AUTH_OPERAND_RENAMED = (
    "requirement authorization_precondition:\n"
    "scope operation\n"
    "when user is not authorized\n"
    "then operation must reject before state_update\n"
)


def test_translation_agreement_agrees_on_alpha_equivalent_formal_claims() -> None:
    """Two v3 requirements that differ only in operand identifier names produce equal signatures.

    alpha_identifiers=True normalises operand identifier values to positional
    placeholders (id1, id2, …). Requirements that share scope/action/target
    but use different identifier names in predicate operand positions should agree.
    """
    req_a = DslV3Parser().parse_ir(_DSL_V3_AUTH, requirement_id="REQ-SIG-001", title="Auth A")
    req_b = DslV3Parser().parse_ir(
        _DSL_V3_AUTH_OPERAND_RENAMED, requirement_id="REQ-SIG-001", title="Auth B"
    )
    from nlreq.formal_claim import build_formal_claim, formal_claim_signature

    claim_a = build_formal_claim(req_a)
    claim_b = build_formal_claim(req_b)
    # Both must lower successfully for the test to be valid.
    assert claim_a.result == "lowered", f"Expected claim A to lower, got {claim_a.result}"
    assert claim_b.result == "lowered", f"Expected claim B to lower, got {claim_b.result}"
    # Signatures must be equal under alpha-renaming.
    sig_a = formal_claim_signature(claim_a.formal_claim, alpha_identifiers=True, commutative=True)
    sig_b = formal_claim_signature(claim_b.formal_claim, alpha_identifiers=True, commutative=True)
    assert sig_a == sig_b, "Alpha-equivalent formal claims should have equal signatures"

    # Now verify the agreement report agrees on these two candidates.
    report = build_translation_agreement_report(
        TranslationAgreementInput(
            candidates=[
                TranslationCandidate(
                    translator_id="parser-a",
                    method="deterministic",
                    requirement=req_a,
                ),
                TranslationCandidate(
                    translator_id="parser-b",
                    method="deterministic",
                    requirement=req_b,
                ),
            ]
        )
    )
    assert report.status == "agreed", (
        f"Alpha-equivalent formal claims must agree, got {report.status!r}: {report.disagreements}"
    )


def test_translation_agreement_uses_formal_claim_signature_for_v3_requirements() -> None:
    """Two structurally distinct v3 requirements with different claim classes disagree.

    Uses a numeric_invariant vs. authorization_precondition — different claim_class
    values produce different FormalClaim signatures, so the signature-based comparator
    detects disagreement.
    """
    _DSL_V3_NUMERIC = (
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when reserve is confirmed\n"
        "then keep collateral >= 100\n"
    )
    req_auth = DslV3Parser().parse_ir(
        _DSL_V3_AUTH, requirement_id="REQ-SIG-002", title="Auth"
    )
    req_num = DslV3Parser().parse_ir(
        _DSL_V3_NUMERIC, requirement_id="REQ-SIG-002", title="Numeric"
    )
    report = build_translation_agreement_report(
        TranslationAgreementInput(
            candidates=[
                TranslationCandidate(
                    translator_id="candidate-auth",
                    method="deterministic",
                    requirement=req_auth,
                ),
                TranslationCandidate(
                    translator_id="candidate-numeric",
                    method="deterministic",
                    requirement=req_num,
                ),
            ]
        )
    )
    assert report.status == "disagreed", (
        f"Semantically distinct requirements must disagree, got {report.status!r}"
    )
    assert len(report.disagreements) >= 1
    # The disagreement reason must mention the formal-claim signature diff.
    assert any("formal-claim" in d.reason or "differ" in d.reason for d in report.disagreements), (
        f"Expected formal-claim signature context in disagreement reason, got: {report.disagreements}"
    )
    # Clarification questions must be generated for the disagreeing paths.
    assert len(report.clarifications) >= 1


def test_refuse_ambiguous_ensemble_emits_refused_ambiguous_code() -> None:
    """refuse_ambiguous_ensemble returns a SemanticTranslationReport with NLR-REFUSED-AMBIGUOUS.

    A disagreement that carries no span of its own still localizes: the controlled requirement
    text supplies the whole-requirement fallback, so the PA-10 product finding renders a real
    span and never a spanless "unavailable" finding.
    """
    from nlreq.refusal import build_refusal_report_from_semantic_translation
    from nlreq.semantic_translation import refuse_ambiguous_ensemble
    from nlreq.translator_agreement import TranslationDisagreement

    controlled_text = "requirement state_precondition:\n  actor must be authorized\n"
    disagreements = [
        TranslationDisagreement(
            left_translator_id="t1",
            right_translator_id="t2",
            path="semantic_ir.premise",
            reason="formal-claim signatures differ: baseline=abc… candidate=def…",
        )
    ]
    report = refuse_ambiguous_ensemble(
        requirement_id="REQ-AMBIG-001",
        disagreements=disagreements,
        controlled_text=controlled_text,
    )

    assert report.result == "refused"
    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS"
    assert report.syntactically_valid is True
    assert len(report.ambiguity_findings) == 1
    assert len(report.clarification_questions) == 1
    assert "t1" in report.clarification_questions[0]
    assert "t2" in report.clarification_questions[0]

    # PA-10: the documented compatibility mode cannot render a spanless product finding.
    refusal = build_refusal_report_from_semantic_translation(report)
    finding = refusal.findings[0]
    assert finding.source_spans, "ambiguous-ensemble refusal must localize a real span"
    assert finding.no_span_reason is None
    assert finding.source_spans[0].text == controlled_text.rstrip("\n")
    assert finding.next_actions


def test_refuse_ambiguous_ensemble_without_localizable_source_raises() -> None:
    """PA-10: with no per-disagreement span, no requirement_ir, and no controlled_text, the
    helper refuses to emit a mute, spanless product finding and raises rather than guessing a
    source location."""
    import pytest

    from nlreq.semantic_translation import refuse_ambiguous_ensemble
    from nlreq.translator_agreement import TranslationDisagreement

    disagreements = [
        TranslationDisagreement(
            left_translator_id="t1",
            right_translator_id="t2",
            path="semantic_ir.premise",
            reason="formal-claim signatures differ",
        )
    ]
    with pytest.raises(ValueError, match="cannot localize"):
        refuse_ambiguous_ensemble(
            requirement_id="REQ-AMBIG-002",
            disagreements=disagreements,
        )


def test_refuse_ambiguous_ensemble_controlled_text_insures_empty_ir_root_spans() -> None:
    """PA-10 gate-shape insurance: requirement_ir alone does not guarantee a span — its root
    spans can be empty, and a remapped disagreement can carry no span of its own. The
    end-to-end gate also passes controlled_text, which guarantees a non-empty whole-requirement
    fallback so the refusal localizes and never raises in that shape.
    """
    from nlreq.refusal import build_refusal_report_from_semantic_translation
    from nlreq.semantic_translation import refuse_ambiguous_ensemble
    from nlreq.translator_agreement import TranslationDisagreement

    data = _ir().model_dump(mode="json")
    data["semantic_ir"]["source_spans"] = []
    ir_no_root_spans = RequirementIRV2.model_validate(data)
    controlled_text = (FIXTURES / "dsl_v2_redemption.nlreq2").read_text()

    report = refuse_ambiguous_ensemble(
        requirement_id="REQ-AGREE-001",
        disagreements=[
            TranslationDisagreement(
                left_translator_id="t1",
                right_translator_id="t2",
                path="semantic_ir.premise",
                reason="formal-claim signatures differ",
            )
        ],
        requirement_ir=ir_no_root_spans,
        controlled_text=controlled_text,
    )

    finding = build_refusal_report_from_semantic_translation(report).findings[0]
    assert finding.source_spans, "controlled_text must localize when IR root spans are empty"
    assert finding.no_span_reason is None
    assert finding.source_spans[0].text == controlled_text.rstrip("\n")


def test_translation_agreement_unapproved_llm_with_different_ir_blocks_as_needs_review() -> None:
    """An unapproved LLM candidate with a different IR must yield needs_review, not disagreed.

    This is the PA-5 status-precedence regression test: before the fix, an
    unapproved LLM candidate whose IR differed from the baseline would produce
    status='disagreed'.  After the fix, the blocker (unapproved approval) wins
    and the status is 'needs_review'.
    """
    agreement_input = TranslationAgreementInput(
        candidates=[
            TranslationCandidate(
                translator_id="parser",
                method="deterministic",
                requirement=_ir(),
            ),
            TranslationCandidate(
                translator_id="llm",
                method="llm",
                requirement=_ir_with_temporal_bound(7),  # intentionally different IR
                # No approval — this is the unapproved case.
            ),
        ]
    )

    report = build_translation_agreement_report(agreement_input)

    assert report.status == "needs_review", (
        f"Unapproved LLM candidate with different IR must block as needs_review, "
        f"got {report.status!r} with disagreements: {report.disagreements}"
    )
    assert any("requires explicit approval" in b for b in report.blockers), (
        f"Expected approval blocker, got: {report.blockers}"
    )
    # Unapproved candidate's IR must not surface as a semantic disagreement.
    assert report.disagreements == [], (
        f"Unapproved candidate must not drive semantic disagreement, got: {report.disagreements}"
    )


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-AGREE-001",
        title="Translator agreement",
    )


def _ir_with_temporal_bound(value: int) -> RequirementIRV2:
    data = _ir().model_dump(mode="json")
    data["semantic_ir"]["obligation"]["must"]["children"][0]["temporal_bound"]["value"] = value
    return RequirementIRV2.model_validate(data)
