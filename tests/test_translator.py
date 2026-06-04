import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_lowering import validate_authorization_precondition_shape
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


def test_lower_authorization_precondition_is_non_vacuous() -> None:
    ir = _auth_precondition_ir()

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    assert artifact.content is not None
    assert "CONSTANT Pred_not_authorized(_)" in artifact.content
    assert "Pred_not_authorized(actor)" in artifact.content
    assert "== TRUE" not in artifact.content
    assert "== 0" not in artifact.content
    assert artifact.metadata.get("semantics") == "non_vacuous"
    assert artifact.metadata.get("evidence") == "lowered"


def test_lower_authorization_precondition_obligation_references_correct_predicate() -> None:
    """The Obligation expression must reference the actual predicate, not a vacuous TRUE.

    This verifies that the predicate name (Pred_not_authorized vs Pred_authorized)
    reaches the Obligation expression — the formal module is non-vacuous. It does NOT
    assert checker-distinguishability between the two requirements: each module has an
    independent uninterpreted CONSTANT predicate, so a real Apalache run would find the
    same violation (predicate=TRUE, action reaches accepted) for both. True functional
    distinction between requirement and negation requires linked domain constraints (PB-4).
    """
    ir_pos = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is not authorized then operation must reject before state_change.",
        requirement_id="AUTH-POS",
        title="Not authorized",
    )
    ir_neg = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is authorized then operation must reject before state_change.",
        requirement_id="AUTH-NEG",
        title="Authorized",
    )

    art_pos = lower_ir_v2_to_tla(ir_pos)
    art_neg = lower_ir_v2_to_tla(ir_neg)

    assert art_pos.status == "lowered"
    assert art_neg.status == "lowered"
    assert art_pos.content != art_neg.content
    # The Obligation line must be conditioned on the actual predicate name,
    # not TRUE. Extract the Obligation line and check the predicate appears in it.
    pos_obligation_line = next(
        (line for line in art_pos.content.splitlines() if line.startswith("Obligation ==")), ""
    )
    neg_obligation_line = next(
        (line for line in art_neg.content.splitlines() if line.startswith("Obligation ==")), ""
    )
    assert "Pred_not_authorized" in pos_obligation_line
    assert "Pred_authorized" in neg_obligation_line
    assert "Pred_not_authorized" not in neg_obligation_line


def test_dsl_v2_redemption_still_uses_skeleton_lowering() -> None:
    """Routing to non-vacuous path must not affect the legacy DSL-v2 skeleton path."""
    ir = _dsl_v2_ir()

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.metadata.get("evidence") == "not_checked"
    assert artifact.status == "lowered"


def test_lower_authorization_precondition_refuses_comparison_premise() -> None:
    """Comparison premises in authorization_precondition must refuse, not silently emit TRUE.

    DSL v3 allows comparison clauses (e.g. balance >= 5) under any claim kind.
    formal_lowering only supports predicate nodes; silently skipping a comparison
    and emitting Premise == TRUE would violate the non-vacuous contract.
    """
    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when balance >= 5 then operation must reject before state_change.",
        requirement_id="AUTH-COMP-PREM",
        title="Comparison premise",
    )

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "refused"
    assert artifact.content is None
    assert any(d.kind == "gte" for d in artifact.diagnostics)
    assert any("unsupported premise node kind" in d.reason for d in artifact.diagnostics)
    assert artifact.metadata.get("refusal_code") == "NLR-LOWERING-UNSUPPORTED-SHAPE"


def test_lower_authorization_precondition_refuses_non_before_obligation() -> None:
    """Obligation shapes other than 'before' in authorization_precondition must refuse.

    _obligation_components() previously fell back silently to ("action", "state_change")
    when must.kind != "before", which hides bad inputs. The validator must catch this.
    """
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    bad_must = root.obligation.must.model_copy(update={"kind": "always"})
    bad_obl = root.obligation.model_copy(update={"must": bad_must})
    bad_root = root.model_copy(update={"obligation": bad_obl})
    bad_ir = ir.model_copy(update={"semantic_ir": bad_root})

    artifact = lower_ir_v2_to_tla(bad_ir)

    assert artifact.status == "refused"
    assert artifact.content is None
    assert any(d.kind == "always" for d in artifact.diagnostics)
    assert any("reject before" in d.reason for d in artifact.diagnostics)


def test_lower_authorization_precondition_two_step_state_machine() -> None:
    """Non-vacuous lowering produces a two-step state machine with state_changed boundary.

    The obligation is reachable-state safety: state_changed is only reachable via
    accepted, which requires the premise to be false. When the premise holds,
    state_changed is unreachable — the obligation models rejects_before semantics.
    """
    ir = _auth_precondition_ir()

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    assert artifact.content is not None
    content = artifact.content
    # Both steps must be present
    assert "Step_operation ==" in content
    assert "Step_state_change ==" in content
    # State machine covers both step kinds and unchanged
    assert "Next == Step_operation \\/ Step_state_change \\/ UNCHANGED NLRState" in content
    # Obligation uses state_changed (not accepted) — semantics: state boundary unreachable
    obligation_line = next(
        (line for line in content.splitlines() if line.startswith("Obligation ==")), ""
    )
    assert "state_changed" in obligation_line
    assert "accepted" not in obligation_line


def test_validate_authorization_precondition_shape_catches_all_errors() -> None:
    """Validator returns problems for both premise and obligation in a single call."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    # Synthesize bad premise (comparison) AND bad obligation (not before) simultaneously
    premise_node = root.premise
    bad_child = premise_node.children[0].model_copy(update={"kind": "gte"}) if premise_node.children else premise_node
    bad_premise = premise_node.model_copy(update={"children": [bad_child]})
    bad_must = root.obligation.must.model_copy(update={"kind": "always"})
    bad_obl = root.obligation.model_copy(update={"must": bad_must})
    bad_root = root.model_copy(update={"premise": bad_premise, "obligation": bad_obl})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "gte" in kinds
    assert "always" in kinds


def test_validate_authorization_precondition_shape_catches_empty_premise() -> None:
    """Empty 'and' premise must refuse — no predicates means premise_expr would silently become TRUE."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    empty_and = root.premise.model_copy(update={"kind": "and", "children": []})
    bad_root = root.model_copy(update={"premise": empty_and})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "empty_premise" in kinds


def test_validate_authorization_precondition_shape_catches_before_missing_state_ref() -> None:
    """'before' clause with fewer than 2 children must refuse — state_ref is required."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    bad_must = root.obligation.must.model_copy(update={"children": []})
    bad_obl = root.obligation.model_copy(update={"must": bad_must})
    bad_root = root.model_copy(update={"obligation": bad_obl})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "missing_state_ref" in kinds


def test_validate_authorization_precondition_shape_catches_missing_action_name() -> None:
    """Obligation with a nameless action node must refuse — 'Step_action' is a silent fallback."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    bad_action = root.obligation.action.model_copy(update={"name": None})
    bad_obl = root.obligation.model_copy(update={"action": bad_action})
    bad_root = root.model_copy(update={"obligation": bad_obl})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "missing_action" in kinds


def test_lower_authorization_precondition_refuses_nameless_action_node() -> None:
    """lower_ir_v2_to_tla must refuse (not emit Step_action) when action name is missing."""
    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is not authorized then operation must reject before state_change.",
        requirement_id="AUTH-NO-ACTION",
        title="No action name",
    )
    root = ir.semantic_ir
    bad_action = root.obligation.action.model_copy(update={"name": None})
    bad_obl = root.obligation.model_copy(update={"action": bad_action})
    bad_ir = ir.model_copy(update={"semantic_ir": root.model_copy(update={"obligation": bad_obl})})

    artifact = lower_ir_v2_to_tla(bad_ir)

    assert artifact.status == "refused"
    assert artifact.content is None
    assert any(d.kind == "missing_action" for d in artifact.diagnostics)


def test_lower_authorization_precondition_has_apalache_type_annotations() -> None:
    """Generated module must include Apalache @type annotations for type-checked runs.

    Annotations are string-match only — no Apalache binary is available.
    The convention follows https://apalache-mc.org/docs/adr/002adr-types.html:
    predicates get '(Str) => Bool', state variable and identifier constants get 'Str'.
    """
    ir = _auth_precondition_ir()
    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    assert artifact.content is not None
    # State variable annotation
    assert "\\* @type: Str;" in artifact.content
    assert "VARIABLE NLRState" in artifact.content
    # Predicate constant annotation
    assert "\\* @type: (Str) => Bool;" in artifact.content


def test_lower_authorization_precondition_step_is_unconstrained() -> None:
    """Step action must not gate on the premise predicate.

    If the predicate appears in Step_* or Next definitions, the state machine
    is self-satisfying: it encodes behavior that avoids violating the obligation
    by construction. An unconstrained step lets the checker find the violation.
    """
    ir = _auth_precondition_ir()
    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    assert artifact.content is not None
    for line in artifact.content.splitlines():
        if line.startswith("Step_") or line.startswith("Next =="):
            assert "Pred_" not in line, f"predicate appeared in action step: {line!r}"


def test_lowering_diagnostic_carries_offending_node_span() -> None:
    """Refusal diagnostics must carry the offending node's ID and spans, not the root's."""
    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when balance >= 5 then operation must reject before state_change.",
        requirement_id="AUTH-COMP-SPAN",
        title="Comparison span test",
    )

    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "refused"
    comp_diag = next((d for d in artifact.diagnostics if d.kind == "gte"), None)
    assert comp_diag is not None
    # The offending node is the 'gte' premise child, not the root rule node
    assert comp_diag.node_id != ir.semantic_ir.node_id


def _auth_precondition_ir() -> RequirementIRV2:
    return DslV3Parser().parse_ir(
        (FIXTURES / "authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-001",
        title="Authorization precondition",
    )


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
