from __future__ import annotations

from .models import RequirementIRV2, SemanticNode


FORMAL_LOWERING_VERSION = "0.2"


def validate_authorization_precondition_shape(
    root: SemanticNode,
) -> list[tuple[str, str, SemanticNode | None]]:
    """Return (kind, reason, offending_node) triples for unsupported shapes.

    Returns an empty list when the shape is fully supported. Callers must refuse
    lowering when the list is non-empty — never silently emit TRUE or fall back
    to defaults. The third element is the offending SemanticNode (for source span
    propagation) or None when no specific node is implicated.
    """
    problems: list[tuple[str, str, SemanticNode | None]] = []

    if root.premise is None:
        problems.append(("missing_premise", "authorization_precondition requires a premise clause (when ...)", None))
        return problems

    premise = root.premise
    nodes = premise.children if premise.kind == "and" else [premise]

    if not nodes:
        problems.append((
            "empty_premise",
            "authorization_precondition premise must contain at least one predicate node",
            premise,
        ))
    else:
        for node in nodes:
            if node.kind != "predicate":
                problems.append((
                    node.kind,
                    (
                        f"unsupported premise node kind '{node.kind}' in "
                        f"authorization_precondition; only named predicate nodes are supported "
                        f"(e.g. 'when actor is authorized'), not comparisons or membership checks"
                    ),
                    node,
                ))
            elif not node.name:
                problems.append((
                    "nameless_predicate",
                    "authorization_precondition premise predicate requires a name",
                    node,
                ))

    if root.obligation is None:
        problems.append(("missing_obligation", "authorization_precondition requires an obligation clause (must ...)", None))
    else:
        action_node = root.obligation.action
        if action_node is None or not action_node.name:
            problems.append((
                "missing_action",
                "authorization_precondition obligation requires a named action node",
                action_node if action_node is not None else root.obligation,
            ))
        must = root.obligation.must
        if must is None:
            problems.append(("missing_must", "authorization_precondition obligation requires a must clause", None))
        elif must.kind != "before":
            problems.append((
                must.kind,
                (
                    f"authorization_precondition obligation must be 'reject before <state>'; "
                    f"got must node kind '{must.kind}' — unsupported obligation shape"
                ),
                must,
            ))
        else:
            if len(must.children) < 2:
                problems.append((
                    "missing_state_ref",
                    "authorization_precondition 'before' clause requires a rejects(action) child and a state_ref child",
                    must,
                ))
            elif not must.children[1].name:
                problems.append((
                    "nameless_state_ref",
                    "authorization_precondition 'before' state_ref child must have a name",
                    must.children[1],
                ))

    return problems


def lower_authorization_precondition_tla(
    ir: RequirementIRV2,
    *,
    bounds_json: str = "[]",
) -> str:
    """Produce a non-vacuous TLA+ module for authorization_precondition.

    Predicates are CONSTANT uninterpreted operators so a model checker can explore
    all boolean assignments. The state machine is UNCONSTRAINED with respect to the
    premise — Step_{action} nondeterministically chooses "rejected" or "accepted"
    without consulting the predicate. The obligation is an independent safety
    invariant over the reached state.

    This makes the module checker-distinguishable: with Pred_*(arg) = TRUE a
    checker finds a counterexample trace where Step_{action} reaches "accepted"
    while the obligation forbids it. The premise predicate does NOT appear in
    any Step_* or Next definition — only in Obligation.

    Caller must invoke validate_authorization_precondition_shape first and refuse
    if any problems are returned; this function assumes a supported shape.
    """
    root = ir.semantic_ir
    module_name = "Req_" + _safe_name(ir.requirement_id)

    predicates = _premise_predicates(root)
    action_name, state_ref_name = _obligation_components(root)
    const_identifiers = sorted(_scope_identifiers(root))

    # Apalache @type annotations (https://apalache-mc.org/docs/adr/002adr-types.html).
    # These are consumed by Apalache's type-checker; TLC ignores them.
    # Identifiers: abstract Str (safe default — Apalache treats unknown args as uninterpreted).
    # Predicates: (Str) => Bool — one argument, uninterpreted boolean relation.
    pred_decls = "\n".join(
        f"\\* @type: (Str) => Bool;\nCONSTANT {_pred_name(name)}(_)"
        for name, _ in predicates
    )

    premise_parts = [
        f"{_pred_name(name)}({', '.join(args)})" if args else _pred_name(name)
        for name, args in predicates
    ]
    premise_expr = " /\\ ".join(premise_parts) if premise_parts else "TRUE"

    # Separate per-identifier CONSTANT declarations with Apalache Str type annotations.
    const_line = (
        "\n".join(f"\\* @type: Str;\nCONSTANT {ident}" for ident in const_identifiers) + "\n\n"
        if const_identifiers
        else ""
    )

    safe_action = _safe_name(action_name)
    safe_state = _safe_name(state_ref_name)

    # Safety obligation: when premise holds, NLRState must never reach "accepted".
    # "accepted" is the first violation boundary — once the action is accepted,
    # state_changed follows automatically. Checking at "accepted" directly encodes
    # "the action must be rejected, not accepted" for rejects_before semantics.
    # The obligation is defined without the premise predicate in the transition
    # relation, so the checker is not self-satisfied.
    obligation_expr = f"{premise_expr} => NLRState /= \"accepted\""

    return (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"\\* Non-vacuous authorization_precondition lowering.\n"
        f"\\* Generated by nlreq translator {FORMAL_LOWERING_VERSION}; semantics: non_vacuous.\n"
        f"\\* Requirement: {ir.requirement_id}\n"
        f"\\* Temporal bounds: {bounds_json}\n\n"
        f"{const_line}"
        f"{pred_decls}\n\n"
        f"\\* @type: Str;\n"
        f"VARIABLE NLRState\n\n"
        f"Init == NLRState = \"idle\"\n\n"
        f"\\* Unconstrained: outcome is not gated by the premise predicate.\n"
        f"\\* The checker explores both \"rejected\" and \"accepted\" for any predicate assignment.\n"
        f"Step_{safe_action} ==\n"
        f"  /\\ NLRState = \"idle\"\n"
        f"  /\\ NLRState' \\in {{\"rejected\", \"accepted\"}}\n\n"
        f"Step_{safe_state} ==\n"
        f"  /\\ NLRState = \"accepted\"\n"
        f"  /\\ NLRState' = \"state_changed\"\n\n"
        f"Next == Step_{safe_action} \\/ Step_{safe_state} \\/ UNCHANGED NLRState\n\n"
        f"Premise == {premise_expr}\n\n"
        f"Obligation == {obligation_expr}\n\n"
        f"RequirementHolds == Premise => Obligation\n\n"
        f"====\n"
    )


def generate_minimal_discriminating_s_module(
    requirement_pred_name: str,
    negation_pred_name: str,
) -> str:
    """Return a minimal TLA+ system-constraint module that discriminates R from ¬R.

    S assigns requirement_pred_name = FALSE and negation_pred_name = TRUE.
    Under S:
      R (obligation premise = requirement_pred_name): FALSE => ... = TRUE (vacuous, no CE).
      ¬R (obligation premise = negation_pred_name): TRUE => NLRState /= "accepted"
          and Step_{action} can reach "accepted" (unconstrained) → counterexample exists.

    This S cannot be used directly by TlaRunnerBackend until PB-4 wires S∧R composition.
    It is provided as a documentation artifact showing what system model discriminates
    the two requirement variants — the real-run evidence requires the Apalache binary.
    """
    r_pred = _pred_name(requirement_pred_name)
    n_pred = _pred_name(negation_pred_name)
    return (
        f"---- MODULE MinimalSystemConstraint ----\n"
        f"\\* Minimal system constraint S for authorization_precondition discrimination.\n"
        f"\\* Under S: {r_pred}(actor) = FALSE, {n_pred}(actor) = TRUE\n"
        f"\\* R + S: obligation premise is FALSE → obligation is vacuously true → no counterexample.\n"
        f"\\* ¬R + S: obligation premise is TRUE → obligation fires; Step_action can reach\n"
        f"\\*          'accepted' (unconstrained) → counterexample exists.\n"
        f"\\* Checker-distinguishable: against S, R holds and ¬R fails.\n"
        f"\\* Real-run evidence requires Apalache binary + PB-4 S∧R composition.\n"
        f"CONSTANT actor\n\n"
        f"\\* @type: (Str) => Bool;\n"
        f"{r_pred}(a) == FALSE\n\n"
        f"\\* @type: (Str) => Bool;\n"
        f"{n_pred}(a) == TRUE\n"
        f"====\n"
    )


def _premise_predicates(root: SemanticNode) -> list[tuple[str, list[str]]]:
    """Return (predicate_name, [identifier_arg_names]) from the premise node.

    Caller must invoke validate_authorization_precondition_shape first; this function
    assumes every predicate node has a non-empty name and raises otherwise.
    """
    if root.premise is None:
        return []
    premise = root.premise
    nodes = premise.children if premise.kind == "and" else [premise]
    result: list[tuple[str, list[str]]] = []
    for node in nodes:
        if node.kind == "predicate":
            if not node.name:
                raise ValueError(
                    "_premise_predicates: predicate node has no name — "
                    "validate_authorization_precondition_shape must be called first"
                )
            args = [str(arg.value) for arg in node.args if arg.kind == "identifier"]
            result.append((node.name, args))
    return result


def _obligation_components(root: SemanticNode) -> tuple[str, str]:
    """Return (action_name, state_ref_name) from the action_obligation node.

    Caller must invoke validate_authorization_precondition_shape first; this function
    assumes a validated shape and raises on any missing/nameless node rather than
    silently falling back to placeholder strings.
    """
    if root.obligation is None:
        raise ValueError(
            "_obligation_components: no obligation node — "
            "validate_authorization_precondition_shape must be called first"
        )
    action_node = root.obligation.action
    if action_node is None or not action_node.name:
        raise ValueError(
            "_obligation_components: action node is missing or nameless — "
            "validate_authorization_precondition_shape must be called first"
        )
    action_name = action_node.name
    must = root.obligation.must
    if must is None or must.kind != "before" or len(must.children) < 2:
        raise ValueError(
            "_obligation_components: 'before' obligation is missing or malformed — "
            "validate_authorization_precondition_shape must be called first"
        )
    state_node = must.children[1]
    if not state_node.name:
        raise ValueError(
            "_obligation_components: state_ref child has no name — "
            "validate_authorization_precondition_shape must be called first"
        )
    return (action_name, state_node.name)


def _scope_identifiers(root: SemanticNode) -> set[str]:
    """Collect identifier names from scope nodes and premise predicate args."""
    identifiers: set[str] = set()
    for scope_node in root.scope:
        if scope_node.name:
            identifiers.add(scope_node.name)
    if root.premise is not None:
        premise = root.premise
        nodes = premise.children if premise.kind == "and" else [premise]
        for node in nodes:
            for arg in node.args:
                if arg.kind == "identifier":
                    identifiers.add(str(arg.value))
    return identifiers


def _pred_name(name: str) -> str:
    return "Pred_" + _safe_name(name)


def _safe_name(value: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in value)
    if not cleaned:
        return "Unnamed"
    if cleaned[0].isdigit():
        return "_" + cleaned
    return cleaned
