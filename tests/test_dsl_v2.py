import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2ParseError, DslV2Parser, normalize_dsl_v2_text
from nlreq.models import RequirementIRV2
from nlreq.parser import RequirementParser


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_dsl_v2_parses_multi_premise_temporal_requirement_to_ir_v2() -> None:
    ir = DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-DSL-V2-001",
        title="Redemption finalization is timely and reserve-safe",
    )

    assert ir.ir_version == "0.2"
    assert ir.semantic_ir.kind == "rule"
    assert ir.semantic_ir.scope[0].name == "redemption"
    assert ir.semantic_ir.premise is not None
    assert len(ir.semantic_ir.premise.children) == 3
    assert ir.semantic_ir.obligation is not None
    assert ir.semantic_ir.obligation.action is not None
    assert ir.semantic_ir.obligation.action.name == "finalize_redemption"
    assert ir.semantic_ir.obligation.must is not None
    assert ir.semantic_ir.obligation.must.kind == "and"
    assert {child.kind for child in ir.semantic_ir.obligation.must.children} == {"within", "gte"}


def test_dsl_v2_source_spans_and_provenance_are_deterministic() -> None:
    parser = DslV2Parser()
    text = (FIXTURES / "dsl_v2_redemption.nlreq2").read_text()

    first = parser.parse_ir(text, requirement_id="REQ-DSL-V2-001", title="Title")
    second = parser.parse_ir(text, requirement_id="REQ-DSL-V2-001", title="Title")

    assert first.model_dump(mode="json", exclude_none=True) == second.model_dump(
        mode="json",
        exclude_none=True,
    )
    premise = first.semantic_ir.premise.children[0]  # type: ignore[union-attr]
    assert premise.source_spans[0].text == "wallet is authorized"
    assert premise.provenance.method == "deterministic_parse"
    assert premise.confidence == "deterministic_parse"


def test_dsl_v2_refuses_unsupported_fragment_with_location() -> None:
    with pytest.raises(DslV2ParseError, match="dsl_v2_parse_error at line 2"):
        DslV2Parser().parse_ir(
            "For every redemption:\n"
            "when wallet has access\n"
            "then finalize_redemption must emit redemption_finalized within 6 hours.\n",
            requirement_id="REQ-BAD",
            title="Bad",
        )


def test_dsl_v2_cli_outputs_canonical_ir_v2(capsys) -> None:
    exit_code = main(
        [
            "ir-v2",
            str(FIXTURES / "dsl_v2_redemption.nlreq2"),
            "--requirement-id",
            "REQ-DSL-V2-CLI-001",
            "--title",
            "DSL v2 CLI",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["ir_version"] == "0.2"
    assert output["semantic_ir"]["kind"] == "rule"


def test_dsl_v2_does_not_change_phase_0_parser_normalization() -> None:
    raw = "\n  For every operation request:\n    if actor is approved\n    then operation must succeed.\n\n"

    assert normalize_dsl_v2_text(raw) == (
        "For every operation request:\n"
        "if actor is approved\n"
        "then operation must succeed.\n"
    )
    ir = RequirementParser().parse_ir(
        raw,
        requirement_id="REQ-STATE-001",
        title="State postcondition",
        claim_kind="state_postcondition",
    )
    assert ir.ir_version == "0.1"


def test_dsl_v2_output_validates_as_requirement_ir_v2() -> None:
    ir = DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-DSL-V2-001",
        title="Redemption finalization is timely and reserve-safe",
    )

    assert RequirementIRV2.model_validate(ir.model_dump(mode="json")).ir_version == "0.2"
