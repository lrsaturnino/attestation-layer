"""PA-10 refusal UX hardening.

Every Pillar A drafting/translation refusal must carry actionable next_actions plus
EITHER a real source span OR an explicit no_span_reason — never a bare
"broken, try again". These tests pin that invariant across each refusal mode, the
parse-error span enrichment, exact code preservation, and the CLI inline rendering.
"""

from __future__ import annotations

import pytest

from nlreq.cli import main
from nlreq.formal_claim import FormalClaimLoweringReport, FormalClaimUnsupportedFragment
from nlreq.jsonutil import sha256_text
from nlreq.models import SourceSpan
from nlreq.refusal import (
    ProductRefusalFinding,
    build_refusal_report_from_semantic_translation,
)
from nlreq.semantic_translation import (
    SemanticAmbiguityFinding,
    SemanticTranslationReport,
    SemanticTranslationStage,
    refuse_ambiguous_ensemble,
    translate_controlled_requirement_to_formal_claim,
)
from nlreq.translator_agreement import TranslationDisagreement


STATE_PRECONDITION = (
    "requirement state_precondition:\n"
    "scope operation\n"
    "when actor is approved\n"
    "then operation must succeed\n"
)


def _assert_actionable(finding: ProductRefusalFinding) -> None:
    """A product refusal finding is never a dead end: it must localize OR explain why not."""
    assert finding.next_actions, f"{finding.code} carries no next_actions"
    has_span = bool(finding.source_spans)
    has_reason = finding.no_span_reason is not None
    assert has_span != has_reason, (
        f"{finding.code} must carry exactly one of source_spans / no_span_reason"
    )


def _unapproved_report() -> SemanticTranslationReport:
    return translate_controlled_requirement_to_formal_claim(
        controlled_text=STATE_PRECONDITION,
        requirement_id="R-UNAPP",
        title="x",
        require_approved_controlled_text=True,
    )


def _parse_report() -> SemanticTranslationReport:
    return translate_controlled_requirement_to_formal_claim(
        controlled_text="Approve whatever the deployer says.",
        requirement_id="R-PARSE",
        title="x",
    )


def _ambiguous_report() -> SemanticTranslationReport:
    return refuse_ambiguous_ensemble(
        requirement_id="R-AMBIG",
        disagreements=[
            TranslationDisagreement(
                path="premise",
                reason="candidates disagree on premise polarity",
                left_translator_id="a",
                right_translator_id="b",
                source_spans=[
                    SourceSpan(
                        document="controlled_requirement",
                        start_char=0,
                        end_char=5,
                        text="actor",
                    )
                ],
            )
        ],
    )


def _semantic_unsupported_report() -> SemanticTranslationReport:
    lowering = FormalClaimLoweringReport(
        requirement_id="R-UNSUP",
        result="refused",
        source_ir_hash="sha256:deadbeef",
        unsupported_fragments=[
            FormalClaimUnsupportedFragment(
                node_id="n1",
                kind="root",
                reason="semantic root does not declare a supported requirement_class",
                source_spans=[
                    SourceSpan(
                        document="controlled_requirement",
                        start_char=0,
                        end_char=11,
                        text="requirement",
                    )
                ],
                next_actions=["Use a supported DSL v3 requirement class."],
            )
        ],
        refusal_code="NLR-SEMANTIC-UNSUPPORTED",
    )
    return SemanticTranslationReport(
        translation_id="t",
        requirement_id="R-UNSUP",
        result="refused",
        syntactically_valid=True,
        refusal_code="NLR-SEMANTIC-UNSUPPORTED",
        formal_claim_report=lowering,
        stages=[
            SemanticTranslationStage(
                stage="lower_formal_claim", status="failed", message="formal claim lowering refused"
            )
        ],
    )


def _process_blocker_report(code: str) -> SemanticTranslationReport:
    return SemanticTranslationReport(
        translation_id="t",
        requirement_id="R-PROC",
        result="needs_review",
        syntactically_valid=True,
        refusal_code=code,
        clarification_questions=["Supply the missing audit/agreement evidence."],
        stages=[
            SemanticTranslationStage(
                stage="lower_formal_claim", status="needs_review", message="process blocker"
            )
        ],
    )


@pytest.mark.parametrize(
    "report_factory",
    [
        _parse_report,
        _unapproved_report,
        _ambiguous_report,
        _semantic_unsupported_report,
        lambda: _process_blocker_report("NLR-UNAUDITED-DECOMPOSITION"),
        lambda: _process_blocker_report("NLR-TRANSLATION-AGREEMENT-BLOCKED"),
    ],
)
def test_every_refusal_mode_is_actionable(report_factory) -> None:
    report = report_factory()
    refusal = build_refusal_report_from_semantic_translation(report)
    assert refusal.decision in {"refused", "unknown"}
    assert refusal.findings, "a refusal must surface at least one finding"
    for finding in refusal.findings:
        _assert_actionable(finding)


def test_parse_refusal_carries_real_offending_fragment_span() -> None:
    report = _parse_report()
    assert report.refusal_code == "NLR-PARSE-UNSUPPORTED"
    refusal = build_refusal_report_from_semantic_translation(report)
    finding = refusal.findings[0]
    assert finding.code == "NLR-PARSE-UNSUPPORTED"
    assert finding.source_spans, "parse refusal must localize the offending fragment"
    span = finding.source_spans[0]
    assert span.text == "Approve whatever the deployer says."
    assert span.start_char == 0
    assert span.end_char == len(span.text)


def test_hash_level_refusal_uses_no_span_reason_not_a_fake_span() -> None:
    report = _unapproved_report()
    assert report.refusal_code == "NLR-UNAPPROVED-CONTROLLED-TEXT"
    finding = build_refusal_report_from_semantic_translation(report).findings[0]
    assert finding.source_spans == []
    assert finding.no_span_reason is not None
    assert "hash" in finding.no_span_reason


def test_refusal_code_is_preserved_not_remapped() -> None:
    # The product surface keeps the exact emitted code (honest provenance), not a
    # lossy near-synonym from the end-to-end gate vocabulary.
    report = _process_blocker_report("NLR-UNAUDITED-DECOMPOSITION")
    finding = build_refusal_report_from_semantic_translation(report).findings[0]
    assert finding.code == "NLR-UNAUDITED-DECOMPOSITION"
    assert finding.category == "unknown"  # needs_review surfaces as the unknown decision


def test_accepted_report_yields_accepted_decision_no_findings() -> None:
    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=STATE_PRECONDITION, requirement_id="R-OK", title="x"
    )
    refusal = build_refusal_report_from_semantic_translation(report)
    assert refusal.decision == "accepted"
    assert refusal.findings == []


def test_cli_semantic_translate_renders_offending_fragment_inline(tmp_path, capsys) -> None:
    controlled = tmp_path / "bad.nlreq3"
    controlled.write_text("Approve whatever the deployer says.")
    out = tmp_path / "translation.json"
    exit_code = main(
        [
            "semantic-translate",
            str(controlled),
            "--requirement-id",
            "REQ-CLI-REFUSE",
            "--title",
            "CLI refusal render",
            "--out",
            str(out),
        ]
    )
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "NLR-PARSE-UNSUPPORTED" in err
    assert 'Fragment: "Approve whatever the deployer says."' in err
    assert "Next:" in err
