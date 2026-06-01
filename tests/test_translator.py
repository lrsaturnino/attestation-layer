import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.models import RequirementIRV2
from nlreq.translator import (
    ControlledDraft,
    approve_controlled_draft,
    create_controlled_draft,
    lower_ir_v2_to_tla,
    parse_approved_draft_ir_v2,
)


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_controlled_draft_records_original_suggestion_diff_and_provenance() -> None:
    draft = _draft()

    assert draft.approval.status == "needs_review"
    assert draft.metadata.method == "manual"
    assert draft.metadata.timestamp == "2026-06-01T00:00:00Z"
    assert "--- original" in draft.diff
    assert "+++ suggested" in draft.diff


def test_unapproved_draft_cannot_be_parsed() -> None:
    with pytest.raises(ValueError, match="must be approved"):
        parse_approved_draft_ir_v2(
            _draft(),
            requirement_id="REQ-DRAFT-001",
            title="Draft",
        )


def test_approved_draft_parses_to_ir_v2_with_original_text_and_approval() -> None:
    approved = approve_controlled_draft(
        _draft(),
        approved_by="reviewer@example.invalid",
        approved_at="2026-06-01T00:01:00Z",
    )

    ir = parse_approved_draft_ir_v2(
        approved,
        requirement_id="REQ-DRAFT-001",
        title="Approved draft",
    )

    assert ir.ir_version == "0.2"
    assert ir.source.original_text == _original_text()
    assert ir.source.controlled_text_approval is not None
    assert ir.source.controlled_text_approval.approved_by == "reviewer@example.invalid"


def test_lower_ir_v2_to_tla_skeleton_records_temporal_bounds_without_evidence() -> None:
    ir = _dsl_v2_ir()

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    assert artifact.content is not None
    assert "RequirementHolds == Premise => Obligation" in artifact.content
    assert 'Within(Event_redemption_finalized, 6, "hour")' in artifact.content
    assert artifact.content_hash is not None
    assert artifact.temporal_bounds[0].value == 6
    assert artifact.metadata["evidence"] == "not_checked"


def test_lowering_refuses_unsupported_nodes_with_fragment_diagnostics() -> None:
    ir = RequirementIRV2.model_validate_json(
        (FIXTURES / "compositional_ir_v02_multi_premise.json").read_text()
    )

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "refused"
    assert any(diagnostic.kind == "invariant" for diagnostic in artifact.diagnostics)
    assert artifact.content is None


def test_lowering_is_deterministic() -> None:
    ir = _dsl_v2_ir()

    first = lower_ir_v2_to_tla(ir)
    second = lower_ir_v2_to_tla(ir)

    assert first.model_dump(mode="json", exclude_none=True) == second.model_dump(
        mode="json",
        exclude_none=True,
    )


def test_translator_cli_draft_approve_parse_and_lower(tmp_path: Path, capsys) -> None:
    original = tmp_path / "original.txt"
    suggested = FIXTURES / "dsl_v2_redemption.nlreq2"
    draft_path = tmp_path / "draft.json"
    approved_path = tmp_path / "approved.json"
    lowered_path = tmp_path / "lowered.json"
    original.write_text(_original_text())

    draft_exit = main(
        [
            "draft-controlled",
            str(original),
            "--suggested",
            str(suggested),
            "--out",
            str(draft_path),
        ]
    )
    approve_exit = main(
        [
            "approve-draft",
            str(draft_path),
            "--approved-by",
            "reviewer@example.invalid",
            "--out",
            str(approved_path),
        ]
    )
    capsys.readouterr()
    ir_exit = main(
        [
            "ir-v2-from-draft",
            str(approved_path),
            "--requirement-id",
            "REQ-DRAFT-CLI-001",
            "--title",
            "Draft CLI",
        ]
    )
    ir_output = json.loads(capsys.readouterr().out)
    ir_path = tmp_path / "requirement.ir.json"
    ir_path.write_text(json.dumps(ir_output))
    lower_exit = main(["lower-ir-v2", str(ir_path), "--out", str(lowered_path)])

    output = capsys.readouterr().out

    assert draft_exit == 0
    assert approve_exit == 0
    assert ir_exit == 0
    assert lower_exit == 0
    assert "Lowered formal artifact:" in output
    assert ControlledDraft.model_validate_json(approved_path.read_text()).approval.status == "approved"
    assert json.loads(lowered_path.read_text())["status"] == "lowered"


def _draft() -> ControlledDraft:
    return create_controlled_draft(
        original_text=_original_text(),
        suggested_text=(FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        timestamp="2026-06-01T00:00:00Z",
    )


def _dsl_v2_ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-DSL-V2-001",
        title="Redemption finalization is timely and reserve-safe",
    )


def _original_text() -> str:
    return "Redemptions should finalize within six hours and keep collateral above the floor.\n"
