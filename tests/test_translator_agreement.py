import json
from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
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
