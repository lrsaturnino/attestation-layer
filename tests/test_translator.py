import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_lowering import (
    LoweredDiscriminationResult,
    Z3DiscriminationResult,
    generate_minimal_discriminating_s_module,
    parse_obligation_predicates,
    validate_authorization_precondition_shape,
    z3_discriminate_authorization_precondition,
    z3_discriminate_lowered_requirements,
)
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
    """Non-vacuous lowering produces a two-step state machine with accepted as the violation boundary.

    rejects_before semantics: when the premise holds (actor NOT authorized), the action
    must be rejected — reaching "accepted" is the violation, not the subsequent
    state_changed. Checking at "accepted" directly encodes "the action must be rejected
    before any state transition can occur."
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
    # Obligation checks "accepted" directly — the first violation boundary.
    obligation_line = next(
        (line for line in content.splitlines() if line.startswith("Obligation ==")), ""
    )
    assert "accepted" in obligation_line
    assert "state_changed" not in obligation_line


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


def test_validate_authorization_precondition_shape_catches_nameless_predicate() -> None:
    """Predicate nodes without a name must refuse — _premise_predicates would silently skip them."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    nameless_pred = root.premise.children[0].model_copy(update={"name": None})
    bad_premise = root.premise.model_copy(update={"children": [nameless_pred]})
    bad_root = root.model_copy(update={"premise": bad_premise})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "nameless_predicate" in kinds


def test_validate_authorization_precondition_shape_catches_nameless_state_ref_child() -> None:
    """'before' second child without a name must refuse — _obligation_components would raise."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    nameless_state = root.obligation.must.children[1].model_copy(update={"name": None})
    bad_must = root.obligation.must.model_copy(
        update={"children": [root.obligation.must.children[0], nameless_state]}
    )
    bad_obl = root.obligation.model_copy(update={"must": bad_must})
    bad_root = root.model_copy(update={"obligation": bad_obl})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "nameless_state_ref" in kinds


def test_validate_authorization_precondition_shape_catches_empty_predicate_args() -> None:
    """Predicate nodes with no identifier args must refuse — TLA+ arity would be inconsistent."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    # Strip the identifier args from the first premise predicate
    argless_pred = root.premise.children[0].model_copy(update={"args": []})
    bad_premise = root.premise.model_copy(update={"children": [argless_pred]})
    bad_root = root.model_copy(update={"premise": bad_premise})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "empty_predicate_args" in kinds


def test_validate_authorization_precondition_shape_catches_invalid_reject_child_kind() -> None:
    """'before' first child must be a predicate node named 'rejects'."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    # Replace the first child with a wrong kind
    wrong_reject = root.obligation.must.children[0].model_copy(update={"kind": "action"})
    bad_must = root.obligation.must.model_copy(
        update={"children": [wrong_reject, root.obligation.must.children[1]]}
    )
    bad_obl = root.obligation.model_copy(update={"must": bad_must})
    bad_root = root.model_copy(update={"obligation": bad_obl})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "invalid_reject_child" in kinds


def test_validate_authorization_precondition_shape_catches_invalid_state_ref_kind() -> None:
    """'before' second child must have kind 'state_ref'."""
    ir = _auth_precondition_ir()
    root = ir.semantic_ir
    # Replace second child with a non-state_ref node
    wrong_state = root.obligation.must.children[1].model_copy(update={"kind": "action", "name": "some_state"})
    bad_must = root.obligation.must.model_copy(
        update={"children": [root.obligation.must.children[0], wrong_state]}
    )
    bad_obl = root.obligation.model_copy(update={"must": bad_must})
    bad_root = root.model_copy(update={"obligation": bad_obl})

    problems = validate_authorization_precondition_shape(bad_root)

    kinds = {k for k, _, _ in problems}
    assert "invalid_state_ref_kind" in kinds


def test_lowering_tla_predicate_arity_matches_declaration() -> None:
    """Generated TLA+ CONSTANT declaration arity must match the invocation arity.

    A 1-arg predicate must produce 'CONSTANT Pred_name(_)' and 'Pred_name(arg)'
    with the same arity — a mismatch causes Apalache type errors.
    """
    ir = _auth_precondition_ir()
    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    lines = artifact.content.splitlines()
    # Find CONSTANT declarations for predicates
    const_lines = [l for l in lines if l.startswith("CONSTANT Pred_")]
    assert const_lines, "no CONSTANT Pred_ declarations found"
    for const_line in const_lines:
        # Extract the predicate operator name and arity from declaration
        # e.g. "CONSTANT Pred_not_authorized(_)" → arity 1
        pred_part = const_line[len("CONSTANT "):]
        if "(" in pred_part:
            decl_params = pred_part.split("(", 1)[1].rstrip(")")
            decl_arity = len(decl_params.split(",")) if decl_params.strip() else 0
        else:
            decl_arity = 0
        pred_name = pred_part.split("(")[0]
        # Find the invocation of this predicate in premise_parts
        premise_lines = [l for l in lines if l.startswith("Premise ==")]
        assert premise_lines, "no Premise == line found"
        premise_expr = premise_lines[0][len("Premise == "):]
        if pred_name in premise_expr:
            if "(" + pred_name + "(" in premise_expr or premise_expr.startswith(pred_name + "("):
                # Count commas in the invocation args
                inv_start = premise_expr.index(pred_name + "(") + len(pred_name) + 1
                inv_end = premise_expr.index(")", inv_start)
                inv_args = premise_expr[inv_start:inv_end]
                inv_arity = len(inv_args.split(",")) if inv_args.strip() else 0
                assert decl_arity == inv_arity, (
                    f"{pred_name}: declaration arity {decl_arity} != invocation arity {inv_arity}"
                )


def test_lower_authorization_precondition_obligation_checks_accepted_not_state_changed() -> None:
    """rejects_before: the violation is reaching 'accepted', not state_changed.

    Checking at 'accepted' directly encodes the obligation — once the action reaches
    accepted the state_changed transition is inevitable. state_changed is unreachable
    as a consequence, not as the primary invariant.
    """
    ir = _auth_precondition_ir()
    artifact = lower_ir_v2_to_tla(ir)

    assert artifact.status == "lowered"
    obligation_line = next(
        (line for line in artifact.content.splitlines() if line.startswith("Obligation ==")), ""
    )
    assert "accepted" in obligation_line
    assert "state_changed" not in obligation_line


def test_lower_authorization_precondition_discrimination_with_s_module() -> None:
    """Modules R and ¬R are checker-distinguishable: Z3 confirms R holds and ¬R fails under S.

    S assigns: requirement_pred (not_authorized) = FALSE, negation_pred (authorized) = TRUE.

    R+S:   Z3 checks whether the violation query is SAT → UNSAT (R holds under S).
    ¬R+S:  Z3 checks whether (neg_pred=TRUE ∧ reached_accepted=TRUE) is SAT → SAT (¬R fails).

    Predicate names are extracted from the parsed IR (not hardcoded) to anchor the check
    to the actual requirement structure.

    Scope note: z3_discriminate_authorization_precondition operates on predicate name strings
    and discriminates the authorization_precondition template under an explicit S. This is
    test-only — it is not wired into the gate pipeline. system_checker still stubs
    SystemSpecAssumptions==TRUE so no ProofObject route is closed by this check.
    The TLA+ S module (generate_minimal_discriminating_s_module) documents the same reasoning
    for the eventual Apalache run.
    """
    ir_pos = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is not authorized then operation must reject before state_change.",
        requirement_id="DISCRIM-POS",
        title="Not authorized",
    )
    ir_neg = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is authorized then operation must reject before state_change.",
        requirement_id="DISCRIM-NEG",
        title="Authorized",
    )

    art_pos = lower_ir_v2_to_tla(ir_pos)
    art_neg = lower_ir_v2_to_tla(ir_neg)

    assert art_pos.status == "lowered"
    assert art_neg.status == "lowered"
    assert art_pos.content != art_neg.content

    pos_obligation = next(
        (line for line in art_pos.content.splitlines() if line.startswith("Obligation ==")), ""
    )
    neg_obligation = next(
        (line for line in art_neg.content.splitlines() if line.startswith("Obligation ==")), ""
    )

    # Each module has its own premise predicate — the obligations differ in polarity
    assert "Pred_not_authorized" in pos_obligation
    assert "Pred_authorized" in neg_obligation
    assert "Pred_not_authorized" not in neg_obligation

    # The step is unconstrained — checker can reach "accepted" for any predicate assignment
    for line in art_pos.content.splitlines():
        if line.startswith("Step_") or line.startswith("Next =="):
            assert "Pred_" not in line, f"predicate in step: {line!r}"

    # S module: Pred_not_authorized = FALSE, Pred_authorized = TRUE
    s_module = generate_minimal_discriminating_s_module(
        requirement_pred_name="not_authorized",
        negation_pred_name="authorized",
    )
    # S makes Pred_not_authorized = FALSE: R obligation = FALSE => ... = TRUE (vacuous, no CE)
    assert "Pred_not_authorized(a) == FALSE" in s_module
    # S makes Pred_authorized = TRUE: ¬R obligation = TRUE => NLRState /= "accepted"
    assert "Pred_authorized(a) == TRUE" in s_module
    # S names the discrimination explicitly — the checker would find no CE for R+S, CE for ¬R+S
    assert "no counterexample" in s_module
    assert "counterexample exists" in s_module

    # Real Z3 discrimination: predicate names extracted from parsed IR, not hardcoded.
    # This anchors the check to the actual requirement structure, not string literals.
    # Scope: discriminates the template under S; test-only; not wired into the gate.
    # system_checker still stubs SystemSpecAssumptions==TRUE so no ProofObject is closed here.
    from nlreq.formal_lowering import _premise_predicates
    pos_pred_names = [name for name, _ in _premise_predicates(ir_pos.semantic_ir)]
    neg_pred_names = [name for name, _ in _premise_predicates(ir_neg.semantic_ir)]
    assert len(pos_pred_names) >= 1 and len(neg_pred_names) >= 1, (
        "Both IRs must have at least one predicate to discriminate"
    )
    z3_result = z3_discriminate_authorization_precondition(
        requirement_pred_name=pos_pred_names[0],
        negation_pred_name=neg_pred_names[0],
    )
    assert isinstance(z3_result, Z3DiscriminationResult)
    assert z3_result.r_plus_s_outcome == "unsat", (
        f"R+S must be UNSAT (R holds under S), got {z3_result.r_plus_s_outcome!r}"
    )
    assert z3_result.neg_r_plus_s_outcome == "sat", (
        f"¬R+S must be SAT (counterexample: ¬R fails under S), got {z3_result.neg_r_plus_s_outcome!r}"
    )
    assert z3_result.discriminated, (
        "Z3 discrimination must hold: R+S=UNSAT and ¬R+S=SAT prove R ≠ ¬R"
    )


def test_z3_discrimination_negative_control_same_pred_not_discriminated() -> None:
    """z3_discriminate(R, R) must return discriminated=False.

    When the same predicate name is used for both requirement and negation, S is
    self-contradictory (req_pred=FALSE AND neg_pred=TRUE resolve to the same Bool →
    FALSE AND TRUE → UNSAT). Both checks become UNSAT so discriminated=False.
    A real discriminator must fail here; a vacuous p∧¬p discriminator would still
    return discriminated=True since s1=UNSAT (correct) but s2 would wrongly be SAT.
    """
    result = z3_discriminate_authorization_precondition(
        requirement_pred_name="authorized",
        negation_pred_name="authorized",
    )
    assert not result.discriminated, (
        "z3_discriminate(R, R) must return discriminated=False; "
        f"got r_plus_s={result.r_plus_s_outcome!r}, neg_r_plus_s={result.neg_r_plus_s_outcome!r}"
    )
    assert result.neg_r_plus_s_outcome == "unsat", (
        "when the same predicate is used for both R and ¬R, ¬R+S must also be UNSAT "
        "(S is self-contradictory), proving the discriminator depends on req≠neg"
    )


def test_z3_discriminate_lowered_requirements_consumes_real_ir() -> None:
    """z3_discriminate_lowered_requirements derives Z3 constraints from parsed module text.

    Unlike z3_discriminate_authorization_precondition (which takes predicate name strings
    and never reads a module), this function produces lowered TLA+ modules and then
    parses their CONSTANT Pred_* declarations to build the Z3 Bool variables.  The module
    text is the solver's input — the predicate names come from _parse_module_pred_constants,
    not from _premise_predicates(ir).

    Scope: Z3 boolean encoding of the TLA+ obligation semantics.  Apalache binary absent;
    full S∧R gate evidence blocked on PB-4 + apalache.  This is an anchoring improvement
    over the name-string check — module-parsed names, not test-string arguments.
    """
    ir_pos = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is not authorized then operation must reject before state_change.",
        requirement_id="LOWERED-DISCRIM-POS",
        title="Not authorized (lowered)",
    )
    ir_neg = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is authorized then operation must reject before state_change.",
        requirement_id="LOWERED-DISCRIM-NEG",
        title="Authorized (lowered)",
    )

    result = z3_discriminate_lowered_requirements(ir_pos, ir_neg)

    assert isinstance(result, LoweredDiscriminationResult)

    # The lowered modules are non-empty TLA+ text — the Z3 inputs.
    assert "MODULE Req_LOWERED_DISCRIM_POS" in result.requirement_module, (
        "requirement_module must be the lowered TLA+ text for ir_pos"
    )
    assert "MODULE Req_LOWERED_DISCRIM_NEG" in result.negation_module, (
        "negation_module must be the lowered TLA+ text for ir_neg"
    )

    # requirement_pred_names are parsed from the module's CONSTANT Pred_* declarations,
    # not from the IR.  They are the full TLA+ operator names (e.g. "Pred_not_authorized").
    assert result.requirement_pred_names, "requirement_pred_names must not be empty"
    assert result.negation_pred_names, "negation_pred_names must not be empty"
    assert all(n.startswith("Pred_") for n in result.requirement_pred_names), (
        "requirement_pred_names must be Pred_* names parsed from the module CONSTANT declarations"
    )
    assert all(n.startswith("Pred_") for n in result.negation_pred_names), (
        "negation_pred_names must be Pred_* names parsed from the module CONSTANT declarations"
    )
    assert result.requirement_pred_names != result.negation_pred_names, (
        "requirement and negation must declare different Pred_* constants "
        "(Pred_not_authorized vs Pred_authorized)"
    )
    # The Pred_* names from the modules must appear in the module text itself.
    for pred_name in result.requirement_pred_names:
        assert f"CONSTANT {pred_name}" in result.requirement_module, (
            f"{pred_name!r} parsed as a requirement predicate but not found in requirement_module"
        )
    for pred_name in result.negation_pred_names:
        assert f"CONSTANT {pred_name}" in result.negation_module, (
            f"{pred_name!r} parsed as a negation predicate but not found in negation_module"
        )

    assert result.r_plus_s_outcome == "unsat", (
        f"R+S must be UNSAT (R holds under S), got {result.r_plus_s_outcome!r}"
    )
    assert result.neg_r_plus_s_outcome == "sat", (
        f"¬R+S must be SAT (counterexample: ¬R fails under S), got {result.neg_r_plus_s_outcome!r}"
    )
    assert result.discriminated, (
        "z3_discriminate_lowered_requirements must report discriminated=True for R≠¬R"
    )


def test_z3_discriminate_lowered_requirements_negative_control_same_ir() -> None:
    """z3_discriminate_lowered_requirements(R, R) must return discriminated=False.

    When the same IR is used for both R and ¬R, the predicate names are identical.
    Z3 sees the same Bool forced FALSE and TRUE simultaneously → both checks UNSAT
    → discriminated=False.  This mirrors the negative control in the name-string version.
    """
    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is authorized then operation must reject before state_change.",
        requirement_id="LOWERED-SAME",
        title="Same IR negative control",
    )

    result = z3_discriminate_lowered_requirements(ir, ir)

    assert not result.discriminated, (
        f"z3_discriminate_lowered_requirements(R, R) must return discriminated=False; "
        f"got r_plus_s={result.r_plus_s_outcome!r}, neg_r_plus_s={result.neg_r_plus_s_outcome!r}"
    )
    assert result.neg_r_plus_s_outcome == "unsat", (
        "when the same IR is used for both R and ¬R, ¬R+S must also be UNSAT "
        "(same predicate name → same Z3 Bool → S self-contradictory)"
    )


def test_parse_obligation_predicates_finds_pred_names_in_real_module() -> None:
    """parse_obligation_predicates returns the Pred_* names from the Obligation == line.

    The non-vacuous lowered module has exactly the predicate name(s) declared in the
    obligation, not ALL CONSTANT names.  This is the function that anchors the Z3
    discriminator to the actual obligation semantics.
    """
    from nlreq.formal_lowering import lower_authorization_precondition_tla
    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is authorized then operation must reject before state_change.",
        requirement_id="PARSE-OBL-001",
        title="Parse obligation predicates",
    )
    module_text = lower_authorization_precondition_tla(ir)
    preds = parse_obligation_predicates(module_text)
    assert preds, "Real module must have at least one Pred_* in Obligation"
    assert all(p.startswith("Pred_") for p in preds), (
        f"All obligation predicate names must start with 'Pred_', got {preds}"
    )
    assert "Pred_authorized" in preds, (
        f"Expected 'Pred_authorized' in obligation predicates, got {preds}"
    )


def test_parse_obligation_predicates_returns_empty_for_vacuous_obligation() -> None:
    """parse_obligation_predicates returns [] when Obligation == TRUE (vacuous regression).

    Mutation: replacing Obligation with TRUE removes all Pred_* references.
    The Z3 discriminator raises ValueError when it gets an empty list, catching
    regressions where CONSTANT declarations remain but the obligation is stubbed.
    """
    import re
    from nlreq.formal_lowering import lower_authorization_precondition_tla
    ir = DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope op "
        "when actor is authorized then operation must reject before state_change.",
        requirement_id="PARSE-OBL-VACUOUS",
        title="Vacuous obligation mutation",
    )
    module_text = lower_authorization_precondition_tla(ir)

    # Sanity: real module has predicates in Obligation
    assert parse_obligation_predicates(module_text), "Pre-condition: real module has obligation predicates"

    # Mutate: replace the Obligation line with TRUE
    vacuous = re.sub(r"^Obligation == .*$", "Obligation == TRUE", module_text, flags=re.MULTILINE)
    preds = parse_obligation_predicates(vacuous)
    assert not preds, (
        f"Vacuous obligation (Obligation == TRUE) must produce empty list, got {preds!r}"
    )



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
