from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .models import RequirementIRV2, SemanticNode, ValueRef


FORMAL_LOWERING_VERSION = "0.2"


# Premise node kinds an authorization_precondition accepts but PROJECTS OUT of the S ∧ R
# obligation: comparisons (eq/neq/lt/lte/gt/gte) and set-membership. They introduce only
# R-side constants that are disconnected from a reviewed S's transition system, so the model
# check gains nothing from them; they are discharged instead by the theory-aware SMT backends
# (smt-theories / cvc5) per the PB-7 per-premise routing. See
# validate_authorization_precondition_shape for the soundness and non-vacuity rationale.
_PROJECTED_PREMISE_KINDS = frozenset({"eq", "neq", "lt", "lte", "gt", "gte", "membership"})


@dataclass
class Z3DiscriminationResult:
    """Outcome of a Z3 reachability check that discriminates R from ¬R under system constraint S.

    Scope: operates on predicate NAME STRINGS, not a parsed IR or lowered module.
    `discriminated=True` means: for distinct predicate names (req≠neg), the
    authorization_precondition TEMPLATE admits a system constraint S that separates R from ¬R.
    It does NOT mean this specific requirement's ProofObject has been closed — it is a
    name-string template check. The grounded S ∧ R composition that a model checker runs
    lives in compose_s_and_r_module; this helper is test-only and not called from the gate.

    Under S (req_pred=FALSE, neg_pred=TRUE):
      R+S   → UNSAT: violation state (req_pred=TRUE ∧ reached=TRUE) is unreachable.
      ¬R+S  → SAT:   violation state (neg_pred=TRUE ∧ reached=TRUE) is reachable.
    """

    discriminated: bool
    r_plus_s_outcome: Literal["unsat", "sat", "unknown"]
    neg_r_plus_s_outcome: Literal["unsat", "sat", "unknown"]
    requirement_pred_name: str
    negation_pred_name: str


@dataclass
class LoweredDiscriminationResult:
    """Outcome of Z3 discrimination on actual lowered TLA+ requirement modules.

    Unlike Z3DiscriminationResult (which takes predicate name strings and does not
    consume a lowered module), this result is produced by
    z3_discriminate_lowered_requirements, which:
      1. Validates both RequirementIRV2 shapes.
      2. Produces lowered TLA+ modules for R and ¬R via lower_authorization_precondition_tla.
      3. Parses Pred_* names from the Obligation == line of each module (not just CONSTANTs).
         Raises ValueError if the Obligation is vacuous (no Pred_* references) — this
         catches regressions where Obligation == TRUE but CONSTANT Pred_* still exist.
      4. Encodes the obligation semantics in Z3 using those obligation-derived names.
      5. Checks S∧R (should be UNSAT) and S∧¬R (should be SAT).

    requirement_module and negation_module are the evidence artifacts that anchor
    the Z3 check to the real IR, not to arbitrary name strings.

    Under S (req preds=FALSE, neg preds=TRUE):
      R+S   → UNSAT: violation state (req_pred=TRUE ∧ reached=TRUE) unreachable.
      ¬R+S  → SAT:   violation state (neg_pred=TRUE ∧ reached=TRUE) reachable.
    """

    discriminated: bool
    r_plus_s_outcome: Literal["unsat", "sat", "unknown"]
    neg_r_plus_s_outcome: Literal["unsat", "sat", "unknown"]
    requirement_module: str          # lowered TLA+ text for R
    negation_module: str             # lowered TLA+ text for ¬R
    requirement_pred_names: list[str] = field(default_factory=list)
    negation_pred_names: list[str] = field(default_factory=list)


def z3_discriminate_authorization_precondition(
    requirement_pred_name: str,
    negation_pred_name: str,
) -> Z3DiscriminationResult:
    """Z3 reachability check that discriminates the authorization_precondition requirement R from ¬R.

    S assigns: requirement_pred = FALSE (conservative), negation_pred = TRUE (fires the obligation).

    R+S check (requirement_pred=FALSE):
      Violation query: can (requirement_pred=TRUE AND reached_accepted=TRUE)?
      Under S requirement_pred is FALSE → cannot simultaneously be TRUE → UNSAT.
      UNSAT means: under S, R holds (no counterexample possible).

    ¬R+S check (negation_pred=TRUE):
      Violation query: can (negation_pred=TRUE AND reached_accepted=TRUE)?
      Under S negation_pred is TRUE and Step_action is unconstrained → reached_accepted
      can be TRUE (the action is not guarded by the predicate in the transition relation).
      SAT means: under S, ¬R fails (counterexample: pred=TRUE, state=accepted).

    NOTE: Operates on predicate name strings from the IR, not the lowered module.
    Discriminates the template under an explicit S; does not close the ProofObject and
    is independent of the grounded compose_s_and_r_module path.  Test-only; not wired into the gate.
    """
    from z3 import Bool, BoolVal, Solver, sat, unsat

    # Symbolic variables. When req==neg name both resolve to the same Z3 Bool (Z3
    # uses the name as identity), making S self-contradictory (negative control).
    req_pred = Bool(f"Pred_{_safe_name(requirement_pred_name)}")
    neg_pred = Bool(f"Pred_{_safe_name(negation_pred_name)}")
    reached = Bool("nlr_reached_accepted")

    # R+S check: can violation state (req_pred=TRUE ∧ reached=TRUE) coexist with S?
    # S forces req_pred=FALSE; violation requires req_pred=TRUE → contradiction → UNSAT.
    # UNSAT proves R holds under S (its precondition cannot fire when S applies).
    # Both S halves are asserted so the same-name negative control propagates to s2.
    s1 = Solver()
    s1.add(req_pred == BoolVal(False))  # S: requirement pred = FALSE
    s1.add(neg_pred == BoolVal(True))   # S: negation pred = TRUE
    s1.add(req_pred)   # violation premise: req_pred = TRUE
    s1.add(reached)    # violation outcome: reached "accepted"
    r_check = s1.check()
    r_plus_s: Literal["unsat", "sat", "unknown"] = (
        "unsat" if r_check == unsat else ("sat" if r_check == sat else "unknown")
    )

    # ¬R+S check: can violation state (neg_pred=TRUE ∧ reached=TRUE) coexist with S?
    # Under S neg_pred=TRUE (consistent) and reached is unconstrained → SAT.
    # When req==neg: S also has neg_pred=FALSE (from req side) → contradiction → UNSAT.
    # This is the negative control: a requirement cannot be discriminated from itself.
    s2 = Solver()
    s2.add(req_pred == BoolVal(False))  # S: same constraint set as s1
    s2.add(neg_pred == BoolVal(True))   # S
    s2.add(neg_pred)   # violation premise: neg_pred = TRUE (consistent with S when req≠neg)
    s2.add(reached)    # violation outcome: reached = TRUE (unconstrained → SAT when S consistent)
    neg_check = s2.check()
    neg_r_plus_s: Literal["unsat", "sat", "unknown"] = (
        "sat" if neg_check == sat else ("unsat" if neg_check == unsat else "unknown")
    )

    discriminated = (r_plus_s == "unsat") and (neg_r_plus_s == "sat")
    return Z3DiscriminationResult(
        discriminated=discriminated,
        r_plus_s_outcome=r_plus_s,
        neg_r_plus_s_outcome=neg_r_plus_s,
        requirement_pred_name=requirement_pred_name,
        negation_pred_name=negation_pred_name,
    )


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
        predicate_count = 0
        for node in nodes:
            if node.kind == "predicate":
                predicate_count += 1
                if not node.name:
                    problems.append((
                        "nameless_predicate",
                        "authorization_precondition premise predicate requires a name",
                        node,
                    ))
                elif not any(arg.kind == "identifier" for arg in node.args):
                    problems.append((
                        "empty_predicate_args",
                        (
                            f"authorization_precondition premise predicate '{node.name}' must have "
                            f"at least one identifier argument — the TLA+ declaration requires it "
                            f"(e.g. 'when actor is authorized', not 'when is_authorized')"
                        ),
                        node,
                    ))
            elif node.kind in _PROJECTED_PREMISE_KINDS:
                # Comparison and set-membership premises are accepted but PROJECTED OUT of the
                # S ∧ R obligation rather than lowered into the TLA+ module. The
                # authorization_precondition obligation stays `<predicate conjunction> => ~outcome`;
                # these fragments are discharged independently by the theory-aware SMT backends
                # (comparison -> smt-theories, set-membership -> cvc5) per the PB-7 routing.
                # Projecting them is sound: under any witness that satisfies them,
                # `(auth /\ extra) => ~outcome` follows a fortiori from `auth => ~outcome`, and the
                # SMT backends confirm the extra antecedents are realizable. They lower to R-side
                # CONSTANTs disconnected from S's transitions, so encoding them into the module
                # would add no checkable content to S ∧ R — only a vacuity-risk surface (pin the
                # witness wrong -> a false `valid`). Faithful comparison lowering is deferred to
                # obligations whose comparison ranges over S's OWN state (PB-4.T2, e.g.
                # numeric_invariant), where the comparison interacts with S's transitions and
                # projection is impossible; that path has no S ∧ R consumer today.
                continue
            else:
                problems.append((
                    node.kind,
                    (
                        f"unsupported premise node kind '{node.kind}' in "
                        f"authorization_precondition; supported premise nodes are named predicates "
                        f"(e.g. 'when actor is authorized'), comparisons, and set-membership checks"
                    ),
                    node,
                ))
        if predicate_count == 0:
            # Non-vacuity guard: the projected S ∧ R obligation is
            # `<predicate conjunction> => ~outcome`. With no predicate premise the antecedent is
            # TRUE and the obligation degenerates to "the forbidden outcome is never reachable" — a
            # vacuous/over-strong check that does not encode the requirement. A premise built only
            # from comparison/membership clauses carries no authorization predicate for S ∧ R to
            # discharge, so refuse rather than emit a meaningless module; the SMT backends still
            # check those clauses on their own route.
            problems.append((
                "no_predicate_premise",
                (
                    "authorization_precondition premise has no named predicate clause; the S ∧ R "
                    "obligation would be vacuous. At least one predicate premise is required "
                    "(e.g. 'when actor is not authorized') — comparison and set-membership premises "
                    "are discharged by the SMT backends and do not constrain S ∧ R."
                ),
                premise,
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
            else:
                reject_child = must.children[0]
                state_child = must.children[1]
                # DSL v3 parser emits: children[0] = predicate("rejects", args=[action]),
                # children[1] = state_ref(name=<state>).
                if reject_child.kind != "predicate" or reject_child.name != "rejects":
                    problems.append((
                        "invalid_reject_child",
                        (
                            f"authorization_precondition 'before' first child must be a "
                            f"predicate node with name 'rejects', got kind='{reject_child.kind}' "
                            f"name='{reject_child.name}'"
                        ),
                        reject_child,
                    ))
                if state_child.kind != "state_ref":
                    problems.append((
                        "invalid_state_ref_kind",
                        (
                            f"authorization_precondition 'before' second child must have "
                            f"kind 'state_ref', got '{state_child.kind}'"
                        ),
                        state_child,
                    ))
                elif not state_child.name:
                    problems.append((
                        "nameless_state_ref",
                        "authorization_precondition 'before' state_ref child must have a name",
                        state_child,
                    ))

    return problems


def validate_state_postcondition_shape(
    root: SemanticNode,
) -> list[tuple[str, str, SemanticNode | None]]:
    """Return (kind, reason, offending_node) triples for unsupported state_postcondition shapes.

    Returns an empty list when the shape is fully supported. Mirrors
    validate_authorization_precondition_shape's contract: callers must refuse lowering when the
    list is non-empty. The supported shape is ``forall scope: <named predicate premise> implies
    post_state(<state>, <value>)`` — the premise carries at least one named predicate with an
    identifier argument (the operator a reviewed S interprets), and the obligation is a
    ``post_state`` clause naming a state and a string/number value. Comparison/membership premises
    are projected out as in the authorization lowering (discharged by the SMT backends).
    """
    problems: list[tuple[str, str, SemanticNode | None]] = []

    if root.premise is None:
        problems.append(
            ("missing_premise", "state_postcondition requires a premise clause (when ...)", None)
        )
    else:
        premise = root.premise
        nodes = premise.children if premise.kind == "and" else [premise]
        predicate_count = 0
        for node in nodes:
            if node.kind == "predicate":
                predicate_count += 1
                if not node.name:
                    problems.append(
                        ("nameless_predicate", "state_postcondition premise predicate requires a name", node)
                    )
                elif not any(arg.kind == "identifier" for arg in node.args):
                    problems.append((
                        "empty_predicate_args",
                        (
                            f"state_postcondition premise predicate '{node.name}' must have at least "
                            "one identifier argument (e.g. 'when actor is approved')"
                        ),
                        node,
                    ))
            elif node.kind in _PROJECTED_PREMISE_KINDS:
                # Comparison/membership premises are discharged by the SMT backends, not the S ∧ R
                # model check — projected out exactly as in the authorization lowering.
                continue
            else:
                problems.append((
                    node.kind,
                    (
                        f"unsupported premise node kind '{node.kind}' in state_postcondition; "
                        "supported premise nodes are named predicates, comparisons, and set-membership"
                    ),
                    node,
                ))
        if predicate_count == 0:
            # Non-vacuity guard: without a named predicate premise the narrowing antecedent is TRUE
            # and the obligation degenerates to "the post-state holds in every reachable state",
            # which does not encode the requirement. A reviewed S must interpret the premise
            # predicate for S ∧ R to couple premise and post-state.
            problems.append((
                "no_predicate_premise",
                (
                    "state_postcondition premise has no named predicate clause; the S ∧ R obligation "
                    "would be vacuous. At least one predicate premise is required (e.g. 'when actor "
                    "is approved')"
                ),
                premise,
            ))

    if root.obligation is None:
        problems.append(
            ("missing_obligation", "state_postcondition requires an obligation clause", None)
        )
    else:
        must = root.obligation.must
        if must is None:
            problems.append(
                ("missing_must", "state_postcondition obligation requires a post-state clause", None)
            )
        elif must.kind != "post_state":
            problems.append((
                must.kind,
                (
                    f"state_postcondition obligation must be a post-state ('then state X must be V'); "
                    f"got must node kind '{must.kind}' — unsupported obligation shape"
                ),
                must,
            ))
        elif not must.name:
            problems.append(
                ("nameless_post_state", "state_postcondition post-state requires a state name", must)
            )
        elif must.value is None:
            problems.append(
                ("missing_post_state_value", "state_postcondition post-state requires a required value", must)
            )
        elif must.value.kind not in {"string", "number"}:
            problems.append((
                "unsupported_post_state_value",
                (
                    f"state_postcondition post-state value must be a string or number literal; got "
                    f"kind '{must.value.kind}' — no faithful TLA+ literal form"
                ),
                must,
            ))

    return problems


def validate_state_precondition_shape(
    root: SemanticNode,
) -> list[tuple[str, str, SemanticNode | None]]:
    """Return (kind, reason, offending_node) triples for unsupported state_precondition shapes.

    Returns an empty list when the shape is fully supported. Mirrors the other shape validators'
    contract: callers must refuse lowering when the list is non-empty — never silently emit a
    skeleton. The supported shape is ``forall scope: <named predicate premise> implies <action>
    succeeds`` — the premise carries at least one named predicate with an identifier argument (the
    operator a reviewed S interprets), and the obligation is a ``succeed`` clause (``then <action>
    must succeed``) naming the action. This is the AFFIRMATIVE dual of authorization_precondition:
    where the authorization obligation forbids the action's accepted outcome, a state_precondition
    requires the action to succeed when its precondition holds. Comparison/membership premises are
    projected out as in the authorization lowering (discharged by the SMT backends), so a premise
    built only from them refuses for vacuity.
    """
    problems: list[tuple[str, str, SemanticNode | None]] = []

    if root.premise is None:
        problems.append(
            ("missing_premise", "state_precondition requires a premise clause (when ...)", None)
        )
    else:
        premise = root.premise
        nodes = premise.children if premise.kind == "and" else [premise]
        predicate_count = 0
        for node in nodes:
            if node.kind == "predicate":
                predicate_count += 1
                if not node.name:
                    problems.append(
                        ("nameless_predicate", "state_precondition premise predicate requires a name", node)
                    )
                elif not any(arg.kind == "identifier" for arg in node.args):
                    problems.append((
                        "empty_predicate_args",
                        (
                            f"state_precondition premise predicate '{node.name}' must have at least "
                            "one identifier argument (e.g. 'when actor is approved')"
                        ),
                        node,
                    ))
            elif node.kind in _PROJECTED_PREMISE_KINDS:
                # Comparison/membership premises are discharged by the SMT backends, not the S ∧ R
                # model check — projected out exactly as in the authorization lowering.
                continue
            else:
                problems.append((
                    node.kind,
                    (
                        f"unsupported premise node kind '{node.kind}' in state_precondition; "
                        "supported premise nodes are named predicates, comparisons, and set-membership"
                    ),
                    node,
                ))
        if predicate_count == 0:
            # Non-vacuity guard (same rationale as authorization/post_state): without a named
            # predicate premise the antecedent is TRUE and the obligation degenerates to "the action
            # never fails in any reachable state" — a check S ∧ R cannot couple to a reviewed S. A
            # premise built only from comparison/membership clauses carries no predicate for S to
            # interpret, so refuse rather than emit a meaningless module; the SMT backends still
            # check those clauses on their own route.
            problems.append((
                "no_predicate_premise",
                (
                    "state_precondition premise has no named predicate clause; the S ∧ R obligation "
                    "would be vacuous. At least one predicate premise is required (e.g. 'when actor "
                    "is approved')"
                ),
                premise,
            ))

    if root.obligation is None:
        problems.append(
            ("missing_obligation", "state_precondition requires an obligation clause (must succeed)", None)
        )
    else:
        action_node = root.obligation.action
        if action_node is None or not action_node.name:
            problems.append((
                "missing_action",
                "state_precondition obligation requires a named action node",
                action_node if action_node is not None else root.obligation,
            ))
        must = root.obligation.must
        if must is None:
            problems.append(("missing_must", "state_precondition obligation requires a must clause", None))
        elif must.kind != "predicate" or must.name != "succeeds":
            # The DSL v3 ``succeed`` obligation lowers to a predicate node named ``succeeds``. Any
            # other must-node (e.g. a ``before`` rejection, a ``post_state``, a ``within`` event)
            # is a different claim shape with its own lowering; refuse here rather than misencode it
            # as a success obligation.
            problems.append((
                must.kind,
                (
                    f"state_precondition obligation must be 'must succeed'; got must node kind "
                    f"'{must.kind}'"
                    + (f" name '{must.name}'" if must.name else "")
                    + " — unsupported obligation shape"
                ),
                must,
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
    # Predicates: arity is inferred from the identifier arg list so the CONSTANT declaration
    # and the invocation expression always have the same arity.
    pred_decls = "\n".join(
        f"\\* @type: {_pred_type_annotation(args)};\nCONSTANT {pred_name(name)}({', '.join('_' for _ in args)})"
        for name, args in predicates
        if args  # validation must have refused empty-arg predicates before reaching here
    )

    premise_parts = [
        f"{pred_name(name)}({', '.join(args)})"
        for name, args in predicates
        if args
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


def lower_state_postcondition_tla(
    ir: RequirementIRV2,
    *,
    bounds_json: str = "[]",
) -> str:
    """Produce a non-vacuous TLA+ module for state_postcondition.

    Premises are CONSTANT uninterpreted operators a reviewed S interprets; the obligation is the
    AFFIRMED post-state re-expressed over a harness variable (``Premise => NLRState =
    "nlr_post_state"``). Like the authorization lowering, this standalone module is
    checker-distinguishable — with the premise predicate TRUE the harness can leave NLRState
    unmet, so a checker finds a counterexample — but it is auxiliary: it is NOT the S ∧ R evidence.
    The real evidence comes from the stateful-S narrowing (compose_s_and_r_module), which discards
    this abstract harness entirely and instead checks the post-state as a NEXT-STEP transition
    obligation over S's own Init/Next (a ghost history bit ``nlr_prev_premise => Pred_<state>(<value>)``
    — see _compose_system_narrowing). The concrete required value is carried by
    :class:`PostStateObligation` into that narrowing, not by this harness, so a numeric or string
    post-state value never has to typecheck against the harness variable here.

    Caller must invoke validate_state_postcondition_shape first and refuse if any problems are
    returned; this function assumes a supported shape.
    """
    root = ir.semantic_ir
    module_name = "Req_" + _safe_name(ir.requirement_id)

    predicates = _premise_predicates(root)
    const_identifiers = sorted(_scope_identifiers(root))

    pred_decls = "\n".join(
        f"\\* @type: {_pred_type_annotation(args)};\nCONSTANT {pred_name(name)}({', '.join('_' for _ in args)})"
        for name, args in predicates
        if args  # validation refused empty-arg predicates before reaching here
    )

    premise_parts = [
        f"{pred_name(name)}({', '.join(args)})"
        for name, args in predicates
        if args
    ]
    premise_expr = " /\\ ".join(premise_parts) if premise_parts else "TRUE"

    const_line = (
        "\n".join(f"\\* @type: Str;\nCONSTANT {ident}" for ident in const_identifiers) + "\n\n"
        if const_identifiers
        else ""
    )

    return (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"\\* Non-vacuous state_postcondition lowering.\n"
        f"\\* Generated by nlreq translator {FORMAL_LOWERING_VERSION}; semantics: non_vacuous.\n"
        f"\\* Requirement: {ir.requirement_id}\n"
        f"\\* Temporal bounds: {bounds_json}\n\n"
        f"{const_line}"
        f"{pred_decls}\n\n"
        f"\\* @type: Str;\n"
        f"VARIABLE NLRState\n\n"
        f"Init == NLRState = \"nlr_init\"\n\n"
        f"\\* Harness: the premise does not gate the post-state, so the checker explores both\n"
        f"\\* reaching it (\"nlr_post_state\") and not (\"nlr_unmet\"). The concrete post-state value\n"
        f"\\* is checked against S's own state by the stateful-S narrowing; here it is an abstract\n"
        f"\\* reached/unmet boundary so the standalone module stays checker-distinguishable.\n"
        f"Step_reach ==\n"
        f"  /\\ NLRState = \"nlr_init\"\n"
        f"  /\\ NLRState' \\in {{\"nlr_post_state\", \"nlr_unmet\"}}\n\n"
        f"Next == Step_reach \\/ UNCHANGED NLRState\n\n"
        f"Premise == {premise_expr}\n\n"
        f"Obligation == {premise_expr} => NLRState = \"nlr_post_state\"\n\n"
        f"RequirementHolds == Premise => Obligation\n\n"
        f"====\n"
    )


def lower_state_precondition_tla(
    ir: RequirementIRV2,
    *,
    bounds_json: str = "[]",
) -> str:
    """Produce a non-vacuous TLA+ module for state_precondition.

    state_precondition is the AFFIRMATIVE dual of authorization_precondition: ``when <predicate>
    then <action> must succeed``. Premises are CONSTANT uninterpreted operators a reviewed S
    interprets; the harness state machine is UNCONSTRAINED with respect to the premise — the action
    nondeterministically reaches ``"succeeded"`` or ``"failed"`` without consulting the predicate —
    and the obligation is the safety invariant ``Premise => NLRState /= "failed"`` (when the
    precondition holds the action must not fail, i.e. it must succeed). Where authorization forbids
    the ``"accepted"`` outcome, this forbids the ``"failed"`` one.

    Like the authorization lowering, this module is checker-distinguishable and composes through the
    stateless-S product (Case A) of :func:`compose_s_and_r_module`: with a reviewed S that pins the
    premise predicate TRUE the harness can still reach ``"failed"``, so the conjoined
    ``RequirementHolds`` invariant has a counterexample; with S pinning it FALSE the obligation is
    vacuously satisfied and the run is ``valid``. The premise predicate never appears in any
    ``Step_*``/``Next`` definition, so the checker is not self-satisfied.

    Caller must invoke validate_state_precondition_shape first and refuse if any problems are
    returned; this function assumes a supported shape.
    """
    root = ir.semantic_ir
    module_name = "Req_" + _safe_name(ir.requirement_id)

    predicates = _premise_predicates(root)
    const_identifiers = sorted(_scope_identifiers(root))

    if root.obligation is None or root.obligation.action is None or not root.obligation.action.name:
        raise ValueError(
            "lower_state_precondition_tla: obligation action is missing or nameless — "
            "validate_state_precondition_shape must be called first"
        )
    safe_action = _safe_name(root.obligation.action.name)

    pred_decls = "\n".join(
        f"\\* @type: {_pred_type_annotation(args)};\nCONSTANT {pred_name(name)}({', '.join('_' for _ in args)})"
        for name, args in predicates
        if args  # validation refused empty-arg predicates before reaching here
    )

    premise_parts = [
        f"{pred_name(name)}({', '.join(args)})"
        for name, args in predicates
        if args
    ]
    premise_expr = " /\\ ".join(premise_parts) if premise_parts else "TRUE"

    const_line = (
        "\n".join(f"\\* @type: Str;\nCONSTANT {ident}" for ident in const_identifiers) + "\n\n"
        if const_identifiers
        else ""
    )

    # Safety obligation: when the premise holds, NLRState must never reach "failed".
    # The obligation is defined without the premise predicate in the transition relation,
    # so the checker is not self-satisfied — it explores "failed" for any predicate assignment.
    obligation_expr = f"{premise_expr} => NLRState /= \"failed\""

    return (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"\\* Non-vacuous state_precondition lowering.\n"
        f"\\* Generated by nlreq translator {FORMAL_LOWERING_VERSION}; semantics: non_vacuous.\n"
        f"\\* Requirement: {ir.requirement_id}\n"
        f"\\* Temporal bounds: {bounds_json}\n\n"
        f"{const_line}"
        f"{pred_decls}\n\n"
        f"\\* @type: Str;\n"
        f"VARIABLE NLRState\n\n"
        f"Init == NLRState = \"idle\"\n\n"
        f"\\* Unconstrained: the outcome is not gated by the premise predicate.\n"
        f"\\* The checker explores both \"succeeded\" and \"failed\" for any predicate assignment.\n"
        f"Step_{safe_action} ==\n"
        f"  /\\ NLRState = \"idle\"\n"
        f"  /\\ NLRState' \\in {{\"succeeded\", \"failed\"}}\n\n"
        f"Next == Step_{safe_action} \\/ UNCHANGED NLRState\n\n"
        f"Premise == {premise_expr}\n\n"
        f"Obligation == {obligation_expr}\n\n"
        f"RequirementHolds == Premise => Obligation\n\n"
        f"====\n"
    )


# Comparison node kind -> TLA+ relational operator. The lowering emits the operator the IR records
# exactly (``gte`` -> ``>=``, never a weaker ``>``), so a requirement and a sibling that differ only
# in the obligation's operator or literal lower to DISTINCT invariants a model checker tells apart.
_COMPARISON_TLA_OPERATORS = {
    "eq": "=",
    "neq": "/=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
}


def _render_comparison_operand(value: ValueRef) -> str:
    """Render one comparison operand as a TLA+ term: an identifier bare, a literal via its rule."""
    if value.kind == "identifier":
        return str(value.value)
    return _render_value_literal(value)


def _render_comparison_tla(node: SemanticNode) -> str:
    """Render a binary comparison node (``gte``/``lte``/…) as a TLA+ relation over its operands.

    e.g. ``gte(collateral, 10)`` -> ``collateral >= 10``. Caller must have validated the shape
    (exactly two operands, a known comparison kind); raises otherwise so a malformed node never
    silently lowers to a partial expression.
    """
    symbol = _COMPARISON_TLA_OPERATORS.get(node.kind)
    if symbol is None or len(node.args) != 2:
        raise ValueError(
            f"_render_comparison_tla: node kind {node.kind!r} with {len(node.args)} args is not a "
            "binary comparison; validate_numeric_invariant_shape must reject it first"
        )
    return f"{_render_comparison_operand(node.args[0])} {symbol} {_render_comparison_operand(node.args[1])}"


def _comparison_nodes(premise: SemanticNode | None) -> list[SemanticNode]:
    """Return the comparison clauses of a premise (the children of an ``and``, or the lone node)."""
    if premise is None:
        return []
    return list(premise.children) if premise.kind == "and" else [premise]


def validate_numeric_invariant_shape(
    root: SemanticNode,
) -> list[tuple[str, str, SemanticNode | None]]:
    """Return (kind, reason, offending_node) triples for unsupported numeric_invariant shapes.

    Returns an empty list when the shape is fully supported. Mirrors the other shape validators:
    callers must refuse lowering when the list is non-empty. The supported shape is ``[when
    <comparisons>] then keep <comparison>`` — every premise clause and the obligation are binary
    comparisons (``>=``/``<=``/``=``/…) over a state variable a reviewed S declares and at least one
    numeric/identifier bound. Unlike the authorization/post_state lowerings, comparisons are NOT
    projected out here: they ARE the antecedent and consequent of the invariant the S ∧ R narrowing
    checks (``Premise => Obligation``) over S's own state, so the obligation comparison must name a
    variable the reviewed S evolves (the narrowing enforces that binding; see _compose_system_narrowing).
    """
    problems: list[tuple[str, str, SemanticNode | None]] = []

    for node in _comparison_nodes(root.premise):
        if node.kind not in _COMPARISON_TLA_OPERATORS:
            problems.append((
                node.kind,
                (
                    f"unsupported numeric_invariant premise node kind '{node.kind}'; the antecedent "
                    "must be comparisons over a state variable (e.g. 'when collateral >= 10')"
                ),
                node,
            ))
        elif len(node.args) != 2 or not any(arg.kind == "identifier" for arg in node.args):
            problems.append((
                "premise_comparison_without_variable",
                (
                    "numeric_invariant premise comparison must relate a state variable identifier to "
                    "a bound (e.g. 'when collateral >= 10')"
                ),
                node,
            ))

    if root.obligation is None:
        problems.append(
            ("missing_obligation", "numeric_invariant requires an obligation clause (then keep ...)", None)
        )
    else:
        must = root.obligation.must
        if must is None:
            problems.append(
                ("missing_must", "numeric_invariant obligation requires a 'keep <comparison>' clause", None)
            )
        elif must.kind not in _COMPARISON_TLA_OPERATORS:
            problems.append((
                must.kind,
                (
                    f"numeric_invariant obligation must be a comparison ('then keep X >= V'); got must "
                    f"node kind '{must.kind}' — unsupported obligation shape"
                ),
                must,
            ))
        elif len(must.args) != 2 or not any(arg.kind == "identifier" for arg in must.args):
            problems.append((
                "obligation_comparison_without_variable",
                (
                    "numeric_invariant obligation comparison must relate a state variable identifier to "
                    "a bound (e.g. 'then keep collateral >= 1'); without a variable the invariant binds "
                    "to no reviewed S state"
                ),
                must,
            ))

    return problems


@dataclass(frozen=True)
class NumericInvariantObligation:
    """The numeric state invariant a numeric_invariant narrows a reviewed S with.

    ``premise_expr`` is the antecedent comparisons rendered and conjoined (``collateral >= 10 /\\
    collateral <= 50``), or ``TRUE`` for a premise-less global invariant. ``obligation_expr`` is the
    consequent comparison the system must keep (``collateral >= 1``). ``variables`` are every state
    variable identifier the premise or obligation names — the narrowing refuses unless a reviewed S
    DECLARES each one, so ``R_Requirement == Premise => Obligation`` ranges over S's real state and a
    counterexample is a genuine S behavior, not two disconnected uses of the same bare name.
    """

    premise_expr: str
    obligation_expr: str
    variables: tuple[str, ...]


def derive_numeric_invariant_obligation(root: SemanticNode) -> NumericInvariantObligation:
    """Derive the numeric state invariant ``Premise => Obligation`` from the IR.

    Caller must invoke validate_numeric_invariant_shape first; raises on a malformed shape.
    """
    if root.obligation is None or root.obligation.must is None:
        raise ValueError(
            "derive_numeric_invariant_obligation: no obligation comparison — "
            "validate_numeric_invariant_shape must be called first"
        )
    premise_nodes = _comparison_nodes(root.premise)
    premise_parts = [_render_comparison_tla(node) for node in premise_nodes]
    premise_expr = " /\\ ".join(premise_parts) if premise_parts else "TRUE"
    obligation_expr = _render_comparison_tla(root.obligation.must)

    variables: list[str] = []
    for node in [*premise_nodes, root.obligation.must]:
        for arg in node.args:
            if arg.kind == "identifier" and str(arg.value) not in variables:
                variables.append(str(arg.value))
    return NumericInvariantObligation(
        premise_expr=premise_expr,
        obligation_expr=obligation_expr,
        variables=tuple(variables),
    )


def lower_numeric_invariant_tla(
    ir: RequirementIRV2,
    *,
    bounds_json: str = "[]",
) -> str:
    """Produce a non-vacuous TLA+ module for numeric_invariant.

    The obligation is a numeric invariant ``Premise => Obligation`` over a state variable. Like the
    state_postcondition lowering, this standalone module is auxiliary, NOT the S ∧ R evidence: its
    ``Next`` moves the variable freely so the module stays checker-distinguishable, but the real
    evidence comes from the stateful-S narrowing (compose_s_and_r_module), which discards this harness
    and checks ``Premise => Obligation`` as a SAME-STATE invariant over S's own Init/Next — S declares
    and evolves the variable, so a counterexample is a reachable S state that satisfies the premise
    bounds yet violates the kept obligation. The narrowing reuses this module's ``Premise ==`` line as
    the antecedent and binds the variable to S's declaration.

    Caller must invoke validate_numeric_invariant_shape first and refuse if any problems are returned;
    this function assumes a supported shape.
    """
    root = ir.semantic_ir
    module_name = "Req_" + _safe_name(ir.requirement_id)
    obligation = derive_numeric_invariant_obligation(root)
    variables = obligation.variables  # validated non-empty: the obligation comparison names a variable

    var_decls = "\n".join(f"VARIABLE {name}" for name in variables)
    init_expr = " /\\ ".join(f"{name} = 0" for name in variables)
    step_expr = " /\\ ".join(f"{name}' \\in Nat" for name in variables)
    unchanged = (
        f"UNCHANGED {variables[0]}"
        if len(variables) == 1
        else f"UNCHANGED <<{', '.join(variables)}>>"
    )

    return (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"\\* Non-vacuous numeric_invariant lowering.\n"
        f"\\* Generated by nlreq translator {FORMAL_LOWERING_VERSION}; semantics: non_vacuous.\n"
        f"\\* Requirement: {ir.requirement_id}\n"
        f"\\* Temporal bounds: {bounds_json}\n"
        f"\\* Auxiliary harness: the premise/obligation range over a state variable a reviewed S owns.\n"
        f"\\* The real S ∧ R evidence is the stateful-S narrowing (compose_s_and_r_module), which\n"
        f"\\* discards this harness and checks Premise => Obligation over S's own Init/Next. Here Next\n"
        f"\\* moves the variable freely so the standalone module is not self-satisfied.\n\n"
        f"{var_decls}\n\n"
        f"Init == {init_expr}\n\n"
        f"Step_evolve == {step_expr}\n\n"
        f"Next == Step_evolve \\/ {unchanged}\n\n"
        f"Premise == {obligation.premise_expr}\n\n"
        f"Obligation == ({obligation.premise_expr}) => {obligation.obligation_expr}\n\n"
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

    This minimal S is a documentation artifact showing what system model discriminates
    the two requirement variants. The grounded, model-checkable composition lives in
    compose_s_and_r_module, which inlines a reviewed spec's predicate definitions and
    invariants; real-run evidence comes from running that composed module under Apalache.
    """
    r_pred = pred_name(requirement_pred_name)
    n_pred = pred_name(negation_pred_name)
    return (
        f"---- MODULE MinimalSystemConstraint ----\n"
        f"\\* Minimal system constraint S for authorization_precondition discrimination.\n"
        f"\\* Under S: {r_pred}(actor) = FALSE, {n_pred}(actor) = TRUE\n"
        f"\\* R + S: obligation premise is FALSE → obligation is vacuously true → no counterexample.\n"
        f"\\* ¬R + S: obligation premise is TRUE → obligation fires; Step_action can reach\n"
        f"\\*          'accepted' (unconstrained) → counterexample exists.\n"
        f"\\* Checker-distinguishable: against S, R holds and ¬R fails.\n"
        f"\\* Real-run evidence comes from compose_s_and_r_module under Apalache.\n"
        f"CONSTANT actor\n\n"
        f"\\* @type: (Str) => Bool;\n"
        f"{r_pred}(a) == FALSE\n\n"
        f"\\* @type: (Str) => Bool;\n"
        f"{n_pred}(a) == TRUE\n"
        f"====\n"
    )


def _parse_module_pred_constants(module_text: str) -> list[str]:
    """Parse CONSTANT Pred_* names declared in a lowered TLA+ module.

    The lowered module format is:
      \\* @type: (Str, ...) => Bool;
      CONSTANT Pred_{name}(_, ...)

    This function returns the Pred_* operator names in declaration order.  The
    Z3 discrimination uses these names as Bool() identifiers so the solver's
    constraints are derived from the module text, not from the IR directly.
    Non-Pred CONSTANT lines (e.g. identifier constants like `CONSTANT actor`)
    are skipped.
    """
    import re
    return re.findall(r"^CONSTANT (Pred_\w+)", module_text, re.MULTILINE)


def parse_obligation_predicates(module_text: str) -> list[str]:
    """Parse Pred_* names referenced in the Obligation == line of a lowered module.

    Returns the Pred_* names that appear in the Obligation definition.
    An empty return means the obligation is absent or vacuous (e.g. Obligation == TRUE);
    callers should treat this as a lowering regression and refuse discrimination.

    The lowered module format produced by lower_authorization_precondition_tla is:
      Obligation == Pred_{name}({args}) /\\ ... => NLRState /= "accepted"

    This function anchors the Z3 encoding to the actual Obligation definition — not
    just to the CONSTANT declarations.  A regression that emits Obligation == TRUE
    while preserving CONSTANT Pred_* declarations is caught here (returns []).
    """
    import re
    match = re.search(r"^Obligation == (.*)$", module_text, re.MULTILINE)
    if not match:
        return []
    return re.findall(r"Pred_\w+", match.group(1))


def obligation_consequent_is_real(module_text: str) -> bool:
    """True when the Obligation definition has a non-vacuous state-constraint consequent.

    Catches regressions where the obligation consequent is replaced with TRUE while
    the Pred_* predicate name is preserved, e.g. Obligation == Pred_foo(a) => TRUE.
    The expected form from lower_authorization_precondition_tla is:
      Obligation == Pred_foo(a) => NLRState /= "accepted"
    Returns False for vacuous consequents (=> TRUE) or missing Obligation lines.

    Exported so both system_checker (gate Z3 path) and formal_lowering
    (z3_discriminate_lowered_requirements) can apply the same guard.
    """
    import re
    match = re.search(r"^Obligation == (.*)$", module_text, re.MULTILINE)
    if not match:
        return False
    body = match.group(1)
    return "NLRState" in body and "/=" in body


def next_has_steps(module_text: str) -> bool:
    """True when the Next definition includes at least one Step_* action.

    Catches regressions where Next == UNCHANGED NLRState (no real transitions),
    which would make the obligation trivially true regardless of the S assignment.
    Returns False when the Next line is missing or contains no Step_* references.

    Exported so both system_checker (gate Z3 path) and formal_lowering
    (z3_discriminate_lowered_requirements) can apply the same guard.
    """
    import re
    match = re.search(r"^Next == (.+)$", module_text, re.MULTILINE)
    if not match:
        return False
    return "Step_" in match.group(1)


def z3_discriminate_lowered_requirements(
    requirement_ir: RequirementIRV2,
    negation_ir: RequirementIRV2,
) -> LoweredDiscriminationResult:
    """Z3 discrimination that uses lowered TLA+ module text as the solver input.

    Unlike z3_discriminate_authorization_precondition (which takes predicate name
    strings and never reads a module), this function:
      1. Validates both IR shapes via validate_authorization_precondition_shape.
      2. Produces lowered TLA+ modules for R and ¬R via lower_authorization_precondition_tla.
      3. Parses the CONSTANT Pred_* declarations from each module text — the module is
         the Z3 solver's input, not the IR.
      4. Builds Z3 Bools from those parsed names and encodes the obligation semantics.
      5. Checks S∧R (UNSAT) and S∧¬R (SAT) under S that assigns R's preds=FALSE/¬R's preds=TRUE.

    Scope: no Apalache binary is required (Apalache is absent in this environment).
    The Z3 check is a boolean encoding of the TLA+ obligation semantics, not a model-
    checker run over the full TLA+ module.  This is an evidence-level improvement over
    the name-string check; closing the full S∧R gate still requires PB-4 + Apalache.

    When requirement and negation share the same predicate name, Z3 sees the same Bool
    forced FALSE and TRUE simultaneously → both checks are UNSAT → discriminated=False.
    This preserves the negative-control property of the name-string version.

    Raises ValueError if either IR has an unsupported shape, or if the lowered module's
    Obligation line is vacuous (Obligation == TRUE or no Pred_* in Obligation) — this
    catches regressions where CONSTANT declarations remain but the obligation is empty.
    """
    from z3 import Bool, BoolVal, Solver, sat, unsat

    r_problems = validate_authorization_precondition_shape(requirement_ir.semantic_ir)
    if r_problems:
        raise ValueError(
            f"requirement_ir is not a valid authorization_precondition: {r_problems}"
        )
    neg_problems = validate_authorization_precondition_shape(negation_ir.semantic_ir)
    if neg_problems:
        raise ValueError(
            f"negation_ir is not a valid authorization_precondition: {neg_problems}"
        )

    # Produce lowered modules — the module text is the Z3 solver's input.
    requirement_module = lower_authorization_precondition_tla(requirement_ir)
    negation_module = lower_authorization_precondition_tla(negation_ir)

    # Parse Pred_* names from the Obligation == line of each module.
    # This anchors the Z3 encoding to the actual Obligation definition, not merely
    # the CONSTANT declarations.  A regression that emits Obligation == TRUE while
    # preserving CONSTANT Pred_* declarations is caught here — parse_obligation_predicates
    # returns [] and we raise ValueError before encoding any Z3 constraints.
    req_pred_z3_names = parse_obligation_predicates(requirement_module)
    neg_pred_z3_names = parse_obligation_predicates(negation_module)

    if not req_pred_z3_names:
        raise ValueError(
            "requirement_module Obligation is vacuous (no Pred_* references) — "
            "lowering defect or regression; expected non-vacuous obligation"
        )
    if not neg_pred_z3_names:
        raise ValueError(
            "negation_module Obligation is vacuous (no Pred_* references) — "
            "lowering defect or regression; expected non-vacuous obligation"
        )

    # Structural integrity guards — same checks as the gate Z3 path (_z3_check_obligation_under_s).
    # Without these, a mutation that changes the obligation consequent to => TRUE or strips
    # all Step_* transitions from Next would still produce a discrimination result, making
    # this function weaker than the gate path it is used to validate.
    if not obligation_consequent_is_real(requirement_module):
        raise ValueError(
            "requirement_module has a vacuous obligation consequent (missing NLRState /= constraint) "
            "— lowering defect or regression"
        )
    if not obligation_consequent_is_real(negation_module):
        raise ValueError(
            "negation_module has a vacuous obligation consequent (missing NLRState /= constraint) "
            "— lowering defect or regression"
        )
    if not next_has_steps(requirement_module):
        raise ValueError(
            "requirement_module Next definition has no Step_* transitions "
            "— lowering defect or regression"
        )
    if not next_has_steps(negation_module):
        raise ValueError(
            "negation_module Next definition has no Step_* transitions "
            "— lowering defect or regression"
        )

    # Z3 Bools are named after the module's CONSTANT declarations.
    # Z3 uses Bool() name as identity: shared names (negative control) map to the same var.
    req_pred_bools = [Bool(n) for n in req_pred_z3_names]
    neg_pred_bools = [Bool(n) for n in neg_pred_z3_names]
    reached = Bool("nlr_reached_accepted")

    # R+S: S forces all R predicates = FALSE.
    # Obligation: Premise => NLRState /= "accepted".
    # Violation query: req_pred=TRUE ∧ reached=TRUE (obligation holds if premise is FALSE).
    # Under S req_pred=FALSE; violation requires req_pred=TRUE → contradiction → UNSAT.
    s1 = Solver()
    for v in req_pred_bools:
        s1.add(v == BoolVal(False))  # S: R's predicates = FALSE (obligation vacuously TRUE)
    for v in neg_pred_bools:
        s1.add(v == BoolVal(True))   # S: ¬R's predicates = TRUE (makes ¬R's obligation fire)
    for v in req_pred_bools:
        s1.add(v)                    # violation premise: req_pred = TRUE (contradicts S)
    s1.add(reached)                  # violation outcome: NLRState = "accepted"
    r_check = s1.check()
    r_plus_s: Literal["unsat", "sat", "unknown"] = (
        "unsat" if r_check == unsat else ("sat" if r_check == sat else "unknown")
    )

    # ¬R+S: S has neg preds = TRUE (consistent with violation).
    # Violation query: neg_pred=TRUE ∧ reached=TRUE.
    # Under S neg_pred=TRUE (consistent); reached is unconstrained → SAT.
    # When req==neg: the req side of S forces the same var = FALSE; neg_pred=TRUE contradicts
    # → UNSAT (negative control: same requirement cannot be discriminated from itself).
    s2 = Solver()
    for v in req_pred_bools:
        s2.add(v == BoolVal(False))  # S: same constraint set as s1
    for v in neg_pred_bools:
        s2.add(v == BoolVal(True))   # S: ¬R's predicates = TRUE
    for v in neg_pred_bools:
        s2.add(v)                    # violation premise: neg_pred = TRUE (consistent with S)
    s2.add(reached)                  # violation outcome: NLRState = "accepted"
    neg_check = s2.check()
    neg_r_plus_s: Literal["unsat", "sat", "unknown"] = (
        "sat" if neg_check == sat else ("unsat" if neg_check == unsat else "unknown")
    )

    return LoweredDiscriminationResult(
        discriminated=(r_plus_s == "unsat") and (neg_r_plus_s == "sat"),
        r_plus_s_outcome=r_plus_s,
        neg_r_plus_s_outcome=neg_r_plus_s,
        requirement_module=requirement_module,
        negation_module=negation_module,
        requirement_pred_names=req_pred_z3_names,
        negation_pred_names=neg_pred_z3_names,
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


@dataclass(frozen=True)
class OutcomePredicate:
    """The forbidden post-state of an authorization_precondition, as a shared predicate.

    The obligation ``<action> must reject before <state>`` forbids S from *accepting*
    (executing) the action while the premise holds. ``name`` is ``Pred_<action>`` (e.g.
    ``Pred_finalize_redemption``) — "the action was accepted/executed" — which a reviewed
    system spec S must interpret over its own state. ``args`` are the subject identifiers
    the premise binds (e.g. ``("wallet",)``) so the narrowing invariant
    ``Premise => ~name(args)`` couples premise and outcome over the same actor. The
    stateful-S composition (Case B) conjoins this invariant into ``Inv`` over S's real
    ``Init``/``Next``; it replaces the requirement harness's literal ``NLRState = "accepted"``
    boundary, which only constrains R's own variable and never S's transitions.
    """

    name: str
    args: tuple[str, ...]


def derive_outcome_predicate(root: SemanticNode) -> OutcomePredicate:
    """Derive the forbidden-outcome predicate ``Pred_<action>(subject)`` from the IR.

    The forbidden outcome is the action being accepted/executed — the boundary the
    requirement harness checks as ``NLRState = "accepted"`` — named after the obligation's
    action operator. The subject identifiers are the premise predicate arguments, so a
    reviewed S binds premise and outcome over the same state. Caller must invoke
    validate_authorization_precondition_shape first; raises on a malformed shape.
    """
    action_name, _state_ref = _obligation_components(root)
    subject: list[str] = []
    for _name, args in _premise_predicates(root):
        for arg in args:
            if arg not in subject:
                subject.append(arg)
    return OutcomePredicate(name=pred_name(action_name), args=tuple(subject))


@dataclass(frozen=True)
class PostStateObligation:
    """The affirmed post-state of a state_postcondition, as a shared predicate over S's state.

    Where an authorization_precondition's :class:`OutcomePredicate` is a FORBIDDEN outcome the
    narrowing negates (``Premise => ~Pred_<action>``), a state postcondition is AFFIRMED:
    ``Pred_<state>(<value>)`` must hold after a premise-state. ``predicate_name`` is ``Pred_<state>``
    (e.g. ``Pred_operation_status``) — the operator a reviewed S interprets over its own state as
    "<state> equals the argument". ``value_literal`` is the required post-state value already
    rendered as a TLA+ literal (a quoted string ``"accepted"`` or a bare number ``42``); it is a
    VALUE the obligation passes to the predicate, never a scope identifier, so it is emitted inline
    and never declared as a CONSTANT the composition would have to pin (which would make it a free
    symbol the checker rejects). The stateful-S narrowing (Case B) checks this as a NEXT-STEP
    transition obligation over S's real ``Init``/``Next`` — a ghost history bit records whether the
    premise held in the pre-state and ``Inv`` requires ``Pred_<state>(<value>)`` after it — so a
    counterexample is a real S step OUT of a premise-state that fails to establish the post-state
    value (see _compose_system_narrowing).
    """

    predicate_name: str
    value_literal: str


def derive_post_state_obligation(root: SemanticNode) -> PostStateObligation:
    """Derive the affirmed post-state predicate ``Pred_<state>(<value>)`` from the IR.

    The obligation ``then state <state> must be <value>`` requires the system's ``<state>`` to
    equal ``<value>`` whenever the premise holds. ``Pred_<state>`` is the operator a reviewed S
    interprets over its own state, and ``<value>`` is rendered as a TLA+ literal passed to it.
    Caller must invoke validate_state_postcondition_shape first; raises on a malformed shape.
    """
    if root.obligation is None or root.obligation.must is None:
        raise ValueError(
            "derive_post_state_obligation: no post_state obligation node — "
            "validate_state_postcondition_shape must be called first"
        )
    post_state = root.obligation.must
    if post_state.kind != "post_state" or not post_state.name or post_state.value is None:
        raise ValueError(
            "derive_post_state_obligation: obligation is not a named post_state with a value — "
            "validate_state_postcondition_shape must be called first"
        )
    return PostStateObligation(
        predicate_name=pred_name(post_state.name),
        value_literal=_render_value_literal(post_state.value),
    )


def _render_value_literal(value: ValueRef) -> str:
    """Render a post-state value as the TLA+ literal the obligation passes to ``Pred_<state>``.

    A string becomes a quoted TLA+ string (``"accepted"``); a number is rendered bare (``42``).
    Other value kinds (e.g. an identifier) have no faithful literal form here and raise — the
    caller refuses rather than emit an ungrounded obligation.
    """
    if value.kind == "string":
        return f'"{value.value}"'
    if value.kind == "number":
        return str(value.value)
    raise ValueError(
        f"_render_value_literal: unsupported post-state value kind {value.kind!r}; "
        "validate_state_postcondition_shape must reject it first"
    )


def _scope_identifiers(root: SemanticNode) -> set[str]:
    """Collect identifier names from scope nodes and premise PREDICATE args.

    Only predicate-premise identifiers are collected. The authorization_precondition lowering
    projects comparison/membership premises out of the module (they are discharged by the SMT
    backends — see validate_authorization_precondition_shape), so their operands (e.g.
    ``requested_amount``, ``tier``) are never referenced by the emitted Premise/Obligation and
    must not be declared as unused CONSTANTs the composition would then have to pin.
    """
    identifiers: set[str] = set()
    for scope_node in root.scope:
        if scope_node.name:
            identifiers.add(scope_node.name)
    if root.premise is not None:
        premise = root.premise
        nodes = premise.children if premise.kind == "and" else [premise]
        for node in nodes:
            if node.kind != "predicate":
                continue
            for arg in node.args:
                if arg.kind == "identifier":
                    identifiers.add(str(arg.value))
    return identifiers


def pred_name(name: str) -> str:
    """The ``Pred_<safe-name>`` operator a predicate name lowers to.

    A reviewed system spec S binds this operator with a concrete definition (e.g.
    ``Pred_authorized(a) == FALSE``), and the composition reports every bound operator in
    ``ComposedSandRModule.bound_predicates``. Exposed (not ``_``-private) so a consumer can
    map a formal-claim fragment to the operator it contributes and check that operator
    against what the composition actually bound — coverage anchored to the real module, not
    a static kind table.
    """
    return "Pred_" + _safe_name(name)


def _pred_type_annotation(args: list[str]) -> str:
    """Return the Apalache @type annotation for a predicate with the given argument list."""
    types = ", ".join("Str" for _ in args)
    return f"({types}) => Bool"


def _safe_name(value: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in value)
    if not cleaned:
        return "Unnamed"
    if cleaned[0].isdigit():
        return "_" + cleaned
    return cleaned


# ---------------------------------------------------------------------------
# PB-1: real S ∧ R composition.
#
# The lowered requirement module R leaves its premise predicates abstract
# (CONSTANT Pred_*(_)). A reviewed system spec S gives those predicates a
# concrete interpretation (e.g. Pred_authorized(a) == FALSE) and declares the
# named invariants the system guarantees. compose_s_and_r_module binds S's
# concrete predicate definitions onto R's abstract predicates — the shared
# predicate IS the coupling that makes S ∧ R non-vacuous — and conjoins R's
# obligation with S's invariants into a single state invariant a model checker
# verifies. This replaces the prior `SystemSpecAssumptions == TRUE` tautology.
#
# Empirically validated against apalache-mc 0.58.0: a requirement whose premise
# S pins TRUE yields a real counterexample; its sibling whose premise S pins
# FALSE yields a real valid — against the same S. Disjoint (non-shared) state
# would make S's invariants trivially preserved, so the composition refuses an
# S that declares no invariants and an S that fails to interpret a predicate R
# depends on, rather than emitting a module that proves nothing.
# ---------------------------------------------------------------------------


@dataclass
class SystemSpecContribution:
    """One reviewed system spec's contribution to the composed S ∧ R module.

    operator_body is the spec's TLA+ operator definitions (predicate
    interpretations such as ``Pred_authorized(a) == FALSE`` and named invariant
    operators) inlined verbatim with their own names preserved. invariants names
    the operators the composition must preserve. defined_operators lists every
    operator the spec declares so the composition can detect name collisions
    with the requirement projection; defined_predicates is the ``Pred_*`` subset
    that binds the requirement's abstract premise predicates.
    """

    spec_id: str
    operator_body: str
    invariants: list[str] = field(default_factory=list)
    defined_operators: list[str] = field(default_factory=list)
    defined_predicates: list[str] = field(default_factory=list)
    # When a reviewed spec carries its own state machine (its own Init/Next), the
    # composition narrows S: S's Init/Next are the sole state machine and R contributes a
    # state invariant (Premise => ~Pred_<action>) over S's variables. init_op/next_op name
    # S's transition operators the composition uses — see _compose_system_narrowing.
    init_op: str | None = None
    next_op: str | None = None


@dataclass
class ComposedSandRModule:
    """Result of composing S ∧ R: either a checker-ready module or a refusal.

    A refusal is honest non-evidence — the composition declines rather than
    emitting a module that would prove a tautology. refusal_kind is one of
    ``unsupported_requirement_shape``, ``no_system_invariant``,
    ``operator_name_collision``, ``undefined_predicate``,
    ``undefined_invariant``, ``state_postcondition_requires_stateful_spec``, or
    ``numeric_invariant_requires_stateful_spec`` (stateless S, Case A); the
    stateful-S narrowing (Case B) additionally uses
    ``incomplete_transition_operators``, ``unsupported_spec_constant``,
    ``unsupported_spec_variable`` (a single ``@type`` over a comma-separated
    multi-name VARIABLES line, which Apalache itself rejects),
    ``variable_name_collision``, ``undefined_transition_operator``,
    ``undefined_state_variable`` (a numeric_invariant names a variable no reviewed
    S declares), ``missing_outcome_predicate``, and ``undefined_outcome_predicate``
    (the last two cover both the forbidden-outcome and affirmed post-state obligation
    predicates).
    """

    status: Literal["composed", "refused"]
    module_text: str | None = None
    refusal_kind: str | None = None
    refusal_reason: str | None = None
    preserved_invariants: list[str] = field(default_factory=list)
    bound_predicates: list[str] = field(default_factory=list)
    bound_state_invariants: list[dict[str, object]] = field(default_factory=list)


# Operators the composition itself emits; an inlined spec must not redefine them.
_COMPOSITION_RESERVED_OPERATORS = frozenset({"Inv", "ConstInit"})


def build_system_spec_contribution(
    spec_id: str,
    spec_text: str,
    invariants: list[str],
    *,
    init_op: str | None = None,
    next_op: str | None = None,
) -> SystemSpecContribution:
    """Parse one reviewed system spec into its inlinable operator contribution.

    Strips the module wrapper and any EXTENDS line (the composed module supplies
    Naturals/TLC) so only operator definitions remain, then records the operator
    and predicate names declared so the caller can bind predicates and detect
    collisions. init_op/next_op are carried through so the synchronous-product
    composition can conjoin a spec that brings its own transition system.
    """
    body = _strip_spec_operator_body(spec_text)
    defined = parse_operator_definition_names(body)
    predicates = [name for name in defined if name.startswith("Pred_")]
    return SystemSpecContribution(
        spec_id=spec_id,
        operator_body=body,
        invariants=list(invariants),
        defined_operators=defined,
        defined_predicates=predicates,
        init_op=init_op,
        next_op=next_op,
    )


def compose_s_and_r_module(
    module_name: str,
    lowered_content: str,
    contributions: list[SystemSpecContribution],
    *,
    outcome_predicate: OutcomePredicate | None = None,
    post_state_obligation: PostStateObligation | None = None,
    numeric_invariant_obligation: NumericInvariantObligation | None = None,
) -> ComposedSandRModule:
    """Compose the lowered requirement R with reviewed system specs S.

    Returns a checker-ready TLA+ module whose state invariant ``Inv`` conjoins
    the requirement obligation with every named system invariant, after
    substituting S's concrete predicate definitions for R's abstract premise
    predicates. Refuses (no module) when the composition would be vacuous or
    ill-formed; the refusal_kind names why.

    Two composition shapes, chosen by whether any spec declares its own
    transition operators (init_op/next_op):

    - Stateless S (Case A): S contributes only predicate interpretations and
      invariant operators; R supplies the single state machine (``Init``/``Next``)
      and the obligation operator is ``RequirementHolds``. ``outcome_predicate`` is
      unused — R's harness models the accepted/rejected outcome itself. A
      ``post_state_obligation`` here is refused: an affirmed post-state has no meaning
      without S's transitions to reach it.
    - Stateful S (Case B): S brings its own ``Init``/``Next`` over its own
      variables, and R *narrows* it. The composition uses S's real ``Init``/``Next``
      as the state machine and conjoins the requirement obligation into ``Inv``, so a
      counterexample is a real S behavior, not an artifact of R's own harness stepping.
      Exactly one obligation drives the narrowing, by claim class: an
      ``outcome_predicate`` (authorization_precondition) makes ``Inv`` forbid the
      accepted/executed outcome as a SAME-STATE safety invariant (``Premise =>
      ~Pred_<action>``), adding no transitions and no variable; a ``post_state_obligation``
      (state_postcondition) checks the affirmed post-state as a NEXT-STEP transition
      obligation, adding one ghost VARIABLE that records the premise in the pre-state so
      ``Inv`` can require ``Pred_<state>(<value>)`` after it; a ``numeric_invariant_obligation``
      (numeric_invariant) conjoins a SAME-STATE numeric invariant (``Premise => Obligation``,
      e.g. ``collateral >= 10 /\\ collateral <= 50 => collateral >= 1``) over a state variable
      S declares — no Pred_*, no ghost, binding by variable name. S must interpret the named
      predicate (or, for numeric, declare the named variable) or the composition refuses. See
      _compose_system_narrowing.
    """
    identifier_constants = parse_lowered_identifier_constants(lowered_content)
    abstract_predicates = _parse_module_pred_constants(lowered_content)
    variable_name = parse_lowered_variable_name(lowered_content)
    logic_body = extract_lowered_logic_body(lowered_content)

    if variable_name is None or not logic_body:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="unsupported_requirement_shape",
            refusal_reason=(
                "lowered requirement module is missing a VARIABLE declaration or a "
                "transition body; cannot compose S ∧ R"
            ),
        )

    # When any reviewed spec brings its own transition system (init_op/next_op), R narrows
    # S: S's own Init/Next are the state machine and R contributes a state invariant into Inv —
    # a same-state safety invariant (Premise => ~Pred_<action>) for authorization, or a ghost
    # history-bit next-step obligation (nlr_prev_premise => Pred_<state>(<value>)) for post_state.
    # Otherwise S is a stateless set of predicate interpretations + invariants and R supplies
    # the only state machine (Case A).
    if any(c.init_op or c.next_op for c in contributions):
        return _compose_system_narrowing(
            module_name=module_name,
            identifier_constants=identifier_constants,
            abstract_predicates=abstract_predicates,
            logic_body=logic_body,
            contributions=contributions,
            outcome_predicate=outcome_predicate,
            post_state_obligation=post_state_obligation,
            numeric_invariant_obligation=numeric_invariant_obligation,
        )

    # Case A is stateless: a post-state obligation asserts the system reaches a value, which only
    # S's transitions can establish. With no stateful S there is nothing to reach, and the Case A
    # product would evaluate the post-state over R's disconnected harness variable. Refuse rather
    # than emit that vacuous module — the honest outcome for a state_postcondition whose impacted
    # modules have no reviewed stateful S.
    if post_state_obligation is not None:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="state_postcondition_requires_stateful_spec",
            refusal_reason=(
                "a state_postcondition narrows a reviewed spec that brings its own transition "
                "system (init_op/next_op); no relevant spec declares one, so there is no S to "
                "reach the post-state and the affirmed obligation cannot be checked"
            ),
        )

    # A numeric_invariant likewise narrows S's reachable states: its variable must be one a stateful
    # S declares and evolves. With no stateful S there is nothing to evolve the variable, and the
    # Case A product would range the invariant over R's disconnected harness. Refuse honestly.
    if numeric_invariant_obligation is not None:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="numeric_invariant_requires_stateful_spec",
            refusal_reason=(
                "a numeric_invariant narrows a reviewed spec that brings its own transition system "
                "(init_op/next_op); no relevant spec declares one, so there is no S evolving the "
                "variable the invariant ranges over and the kept obligation cannot be checked"
            ),
        )

    requirement_operators = set(parse_operator_definition_names(logic_body))
    reserved = requirement_operators | _COMPOSITION_RESERVED_OPERATORS

    invariants: list[str] = []
    for contribution in contributions:
        invariants.extend(contribution.invariants)
    if not invariants:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="no_system_invariant",
            refusal_reason=(
                "no reviewed system spec declares an invariant to preserve; an S that "
                "asserts nothing cannot make S ∧ R non-trivial"
            ),
        )

    # Every operator a spec inlines must be unique and must not shadow the
    # requirement projection's operators or the composition's own operators.
    owner_of: dict[str, str] = {}
    collisions: set[str] = set()
    defined_predicates: set[str] = set()
    for contribution in contributions:
        defined_predicates.update(contribution.defined_predicates)
        for operator in contribution.defined_operators:
            if operator in reserved or operator in owner_of:
                collisions.add(operator)
            owner_of[operator] = contribution.spec_id
    if collisions:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="operator_name_collision",
            refusal_reason=(
                "system spec operators collide with requirement or composition "
                f"operators: {sorted(collisions)}"
            ),
        )

    missing_predicates = [
        predicate for predicate in abstract_predicates if predicate not in defined_predicates
    ]
    if missing_predicates:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_predicate",
            refusal_reason=(
                "reviewed system specs do not interpret premise predicates "
                f"{sorted(missing_predicates)}; cannot ground S ∧ R"
            ),
        )

    missing_invariants = [name for name in invariants if name not in owner_of]
    if missing_invariants:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_invariant",
            refusal_reason=(
                "system spec metadata names invariants that the spec body does not "
                f"define: {sorted(missing_invariants)}"
            ),
        )

    constant_block = _render_constant_block(identifier_constants)
    variable_block = _render_variable_block(variable_name)
    system_block = "\n\n".join(
        contribution.operator_body for contribution in contributions
    ).strip()
    inv_line = "Inv == RequirementHolds" + "".join(f" /\\ {name}" for name in invariants)
    const_init = _render_const_init(identifier_constants)
    bound_predicates = sorted(set(abstract_predicates) & defined_predicates)

    # Vacuity guard: the stateless-S composition couples S and R entirely through the predicates
    # S interprets for R (bound_predicates). When R binds none, the conjoined
    # Inv == RequirementHolds /\ <system invariants> leaves RequirementHolds evaluated over R's
    # own disconnected harness state, so a model check would verify S alone and say nothing about
    # the requirement. This is the shape a claim class with no non-vacuous S ∧ R lowering produces
    # (e.g. a numeric_invariant, whose comparisons range over no predicate S defines, lowers to a
    # skeleton with no CONSTANT Pred_*). Refuse rather than emit such a module: the run is vacuous
    # and its outcome — an incidental skeleton type error, or a stray `valid` for a differently
    # shaped skeleton — is not S ∧ R evidence. Comparison/membership premises are discharged by the
    # SMT backends on their own route, not here. (The narrowing path, Case B, has no analogue: it
    # refuses earlier on a missing outcome predicate, which a non-authorization claim never supplies.)
    # An authorization_precondition always binds >=1 Pred_* (its lowering refuses a predicate-free
    # premise), and a spec that fails to interpret a bound predicate already refuses above as
    # undefined_predicate — so this can only fire on a predicate-free projection, never a real auth case.
    if not bound_predicates:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="vacuous_requirement_projection",
            refusal_reason=(
                "the requirement projection binds no predicate that any reviewed system spec "
                "interprets, so S ∧ R would reduce to checking S alone; refuse rather than run a "
                "vacuous check (such requirements are discharged by the SMT backends, not S ∧ R)"
            ),
        )

    module_text = (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"{constant_block}"
        f"\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
        f"{system_block}\n\n"
        f"{variable_block}"
        f"\\* ===== Requirement projection R (transition system + obligation) =====\n"
        f"{logic_body}\n\n"
        f"\\* ===== S ∧ R: requirement obligation conjoined with system invariants =====\n"
        f"{inv_line}\n"
        f"{const_init}\n"
        f"====\n"
    )
    return ComposedSandRModule(
        status="composed",
        module_text=module_text,
        preserved_invariants=["RequirementHolds", *invariants],
        bound_predicates=bound_predicates,
    )


# Operators the narrowing composition emits itself; an inlined spec must not redefine
# them. S's own transitions are named by init_op/next_op (e.g. SInit/SNext) — never the
# bare Init/Next the composition reserves for S's transition system, nor R_Requirement,
# the obligation invariant R contributes.
_NARROWING_RESERVED_OPERATORS = frozenset({"Init", "Next", "Inv", "ConstInit", "R_Requirement"})

# The single ghost VARIABLE the state_postcondition narrowing adds to S (see
# _compose_system_narrowing): it records, after each step, whether the premise held in the
# PRE-state, so a next-relation post-state obligation can be checked as a reliable single-state
# invariant over the augmented state. A reviewed S that itself declared a variable of this name
# would conflate its own state with R's history bit, so the composition refuses rather than merge.
_NARROWING_POST_STATE_GHOST_VAR = "nlr_prev_premise"
_NARROWING_RESERVED_VARIABLES = frozenset({_NARROWING_POST_STATE_GHOST_VAR})


def _compose_system_narrowing(
    *,
    module_name: str,
    identifier_constants: list[str],
    abstract_predicates: list[str],
    logic_body: str,
    contributions: list[SystemSpecContribution],
    outcome_predicate: OutcomePredicate | None,
    post_state_obligation: PostStateObligation | None = None,
    numeric_invariant_obligation: NumericInvariantObligation | None = None,
) -> ComposedSandRModule:
    """Compose S ∧ R as a *narrowing* when S brings its own transition system (Case B).

    S's own ``Init``/``Next`` are the state machine. R contributes a single state invariant
    ``R_Requirement`` conjoined with S's named invariants into ``Inv``; a model checker then
    verifies ``Spec => []Inv`` against S's *real* transitions, so a counterexample is a genuine S
    behavior — not an artifact of a requirement harness stepping its own variable, which the prior
    synchronous product admitted. Exactly one obligation drives ``R_Requirement``, by claim class:

    - ``outcome_predicate`` (authorization_precondition): a SAME-STATE safety invariant
      ``R_Requirement == Premise => ~Pred_<action>(subject)``. R adds no transitions and no
      variable. A counterexample is a reachable state where the premise holds and S has reached
      the forbidden accepted/executed outcome. This is correctly a single-state property — "the
      forbidden outcome must never hold while the precondition does" — needing no transition
      semantics.

    - ``post_state_obligation`` (state_postcondition): a NEXT-RELATION obligation. "Then state X
      must be V" constrains S's TRANSITIONS, not a single state, so R adds one ghost VARIABLE
      ``nlr_prev_premise`` that records, after every step, whether the premise held in the
      PRE-state (``Next`` conjoins ``nlr_prev_premise' = (Premise)`` over S's unprimed state;
      ``Init`` sets it FALSE). ``R_Requirement`` is then the single-state invariant
      ``nlr_prev_premise => Pred_<state>(<value>)``, so a counterexample is a real S step OUT of a
      premise-state that fails to establish the post-state. This is the strict next-step reading:
      every transition from a premise-state must land in a value-state.

    - ``numeric_invariant_obligation`` (numeric_invariant): a SAME-STATE numeric invariant
      ``R_Requirement == Premise => Obligation`` over a state variable S declares and evolves (e.g.
      ``collateral >= 10 /\\ collateral <= 50 => collateral >= 1``). It binds NO ``Pred_*`` and adds
      NO ghost: the comparisons range over S's own variable by name, so a counterexample is a
      reachable S state inside the premise bounds that violates the kept obligation — a pure state
      property, no transition semantics needed. The variable-declaration guard below refuses unless a
      reviewed S declares every variable the invariant names.

    Why a ghost variable and not a primed-variable action invariant ``Premise => Pred_<state>' =
    <value>``: Apalache 0.58 silently SKIPS such an action invariant over a non-establishing /
    UNCHANGED transition and reports NoError — a false pass on exactly the violation this check
    must catch (verified empirically). Encoding the next-relation obligation as a history-variable
    STATE invariant is the only shape the bounded checker verifies soundly here.

    Refuses, rather than emitting a meaningless module, when: a spec declares only one of
    init_op/next_op; a named transition operator is undefined; a spec brings its own CONSTANTS
    (the composition cannot pin them in ConstInit); two specs declare the same variable; an S
    operator shadows a reserved name; a premise predicate is uninterpreted; no obligation was
    supplied or the obligation predicate is uninterpreted by S; a numeric_invariant names a state
    variable no reviewed S declares; or no invariant is declared.
    """
    incomplete = [
        c.spec_id
        for c in contributions
        if (c.init_op or c.next_op) and not (c.init_op and c.next_op)
    ]
    if incomplete:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="incomplete_transition_operators",
            refusal_reason=(
                "reviewed system specs declare only one of init_op/next_op, so their "
                f"transition system is ill-formed: {sorted(incomplete)}"
            ),
        )

    invariants: list[str] = []
    for contribution in contributions:
        invariants.extend(contribution.invariants)
    if not invariants:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="no_system_invariant",
            refusal_reason=(
                "no reviewed system spec declares an invariant to preserve; an S that "
                "asserts nothing cannot make S ∧ R non-trivial"
            ),
        )

    # The single obligation R conjoins into Inv, by polarity. An authorization_precondition's
    # forbidden outcome is NEGATED (``=> ~Pred_<action>``); a state_postcondition's post-state is
    # AFFIRMED (``=> Pred_<state>(<value>)``). Both name exactly one Pred_* the narrowing binds and
    # S must interpret. ``obligation_phrase`` is the human description inlined in the module comment
    # — its first line keeps the authorization wording byte-for-byte so that golden unchanged.
    if outcome_predicate is not None:
        outcome_call = (
            f"{outcome_predicate.name}({', '.join(outcome_predicate.args)})"
            if outcome_predicate.args
            else outcome_predicate.name
        )
        obligation_consequent = f"~{outcome_call}"
        obligation_pred_names: tuple[str, ...] = (outcome_predicate.name,)
        obligation_phrase = (
            f"forbids S reaching the accepted/executed outcome ({outcome_predicate.name})"
        )
    elif post_state_obligation is not None:
        obligation_consequent = (
            f"{post_state_obligation.predicate_name}({post_state_obligation.value_literal})"
        )
        obligation_pred_names = (post_state_obligation.predicate_name,)
        obligation_phrase = (
            f"requires every step out of a premise-state of S to establish the post-state "
            f"({post_state_obligation.predicate_name})"
        )
    elif numeric_invariant_obligation is not None:
        # A numeric_invariant is a SAME-STATE invariant over S's own variable: R_Requirement ==
        # (premise comparisons) => (obligation comparison), conjoined into Inv. Unlike the
        # predicate obligations above it binds no Pred_* — the comparisons range over a state
        # variable S declares and evolves, so obligation_pred_names is empty and the coupling is
        # checked by the variable-declaration guard below, not predicate interpretation. It slots
        # into the same-state branch (no ghost): the invariant is about the current state, so a
        # counterexample is a reachable S state inside the premise bounds that violates the
        # obligation comparison.
        obligation_consequent = numeric_invariant_obligation.obligation_expr
        obligation_pred_names = ()
        obligation_phrase = (
            f"keeps the numeric invariant ({numeric_invariant_obligation.obligation_expr}) over S's "
            "state whenever the premise bounds hold"
        )
    else:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="missing_outcome_predicate",
            refusal_reason=(
                "no obligation predicate was supplied; narrowing a stateful S needs the "
                "requirement's forbidden-outcome, affirmed post-state, or numeric invariant to "
                "constrain S's reachable states"
            ),
        )

    premise_expr = _parse_premise_expression(logic_body)
    if not premise_expr:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="unsupported_requirement_shape",
            refusal_reason=(
                "lowered requirement module declares no Premise; cannot narrow S with an "
                "obligation that has no antecedent"
            ),
        )

    system_blocks: list[str] = []
    system_variables: list[tuple[str, str | None]] = []
    seen_variables: set[str] = set()
    owner_of: dict[str, str] = {}
    collisions: set[str] = set()
    defined_predicates: set[str] = set()
    init_ops: list[str] = []
    next_ops: list[str] = []

    for contribution in contributions:
        constants, variables, body = _split_declarations(contribution.operator_body)
        if constants:
            return ComposedSandRModule(
                status="refused",
                refusal_kind="unsupported_spec_constant",
                refusal_reason=(
                    f"reviewed system spec {contribution.spec_id!r} declares CONSTANTS "
                    f"{[name for name, _ in constants]}; the composition cannot pin them in "
                    "ConstInit, so it refuses rather than leaving them unconstrained"
                ),
            )
        for var_name, var_type in variables:
            if var_type == _AMBIGUOUS_MULTI_NAME_TYPE:
                return ComposedSandRModule(
                    status="refused",
                    refusal_kind="unsupported_spec_variable",
                    refusal_reason=(
                        f"system spec variable {var_name!r} shares a single '\\* @type:' "
                        "annotation with other names on a comma-separated VARIABLES line; one "
                        "annotation cannot type several names (Apalache rejects it: 'Expected a "
                        "type annotation for VARIABLE ...'). Declare each variable on its own "
                        "single-line VARIABLE declaration immediately preceded by its own @type "
                        "comment, e.g. '\\* @type: Int;' then 'VARIABLE collateral'"
                    ),
                )
            if var_name in _NARROWING_RESERVED_VARIABLES:
                return ComposedSandRModule(
                    status="refused",
                    refusal_kind="variable_name_collision",
                    refusal_reason=(
                        f"system spec variable {var_name!r} collides with the narrowing's "
                        "reserved ghost variable; the post-state history bit would be conflated "
                        "with S's own state — rename the spec variable"
                    ),
                )
            if var_name in seen_variables:
                return ComposedSandRModule(
                    status="refused",
                    refusal_kind="variable_name_collision",
                    refusal_reason=(
                        f"system spec variable {var_name!r} collides with another spec's "
                        "variable; the composed state would conflate two machines"
                    ),
                )
            seen_variables.add(var_name)
            system_variables.append((var_name, var_type))
        system_blocks.append(body)
        defined_predicates.update(contribution.defined_predicates)
        for operator in contribution.defined_operators:
            if operator in _NARROWING_RESERVED_OPERATORS or operator in owner_of:
                collisions.add(operator)
            owner_of[operator] = contribution.spec_id
        if contribution.init_op:
            init_ops.append(contribution.init_op)
        if contribution.next_op:
            next_ops.append(contribution.next_op)

    if collisions:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="operator_name_collision",
            refusal_reason=(
                "system spec operators collide with the composition's reserved operators "
                f"(Init/Next/Inv/ConstInit/R_Requirement) or each other: {sorted(collisions)}"
            ),
        )

    missing_transition = [op for op in (*init_ops, *next_ops) if op not in owner_of]
    if missing_transition:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_transition_operator",
            refusal_reason=(
                "system spec metadata names transition operators the spec body does not "
                f"define: {sorted(set(missing_transition))}"
            ),
        )

    # numeric_invariant binds by VARIABLE NAME, not by an interpreted Pred_*: R_Requirement ranges
    # over S's own state variable directly. The numeric analogue of the undefined_predicate guard —
    # refuse unless a reviewed S DECLARES every variable the premise/obligation names. Without S's
    # declaration the variable is a free symbol Apalache rejects (a type error, not a clean
    # valid/counterexample) and the coupling is vacuous (two disconnected uses of the same bare name).
    if numeric_invariant_obligation is not None:
        undeclared = [v for v in numeric_invariant_obligation.variables if v not in seen_variables]
        if undeclared:
            return ComposedSandRModule(
                status="refused",
                refusal_kind="undefined_state_variable",
                refusal_reason=(
                    "numeric_invariant premise/obligation references state variable(s) "
                    f"{sorted(undeclared)} that no reviewed system spec declares; the reviewed S must "
                    "declare and evolve each variable the invariant ranges over, or the narrowing "
                    "binds to no real state"
                ),
            )

    missing_predicates = [
        predicate for predicate in abstract_predicates if predicate not in defined_predicates
    ]
    if missing_predicates:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_predicate",
            refusal_reason=(
                "reviewed system specs do not interpret premise predicates "
                f"{sorted(missing_predicates)}; cannot ground S ∧ R"
            ),
        )

    undefined_obligation = [name for name in obligation_pred_names if name not in defined_predicates]
    if undefined_obligation:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_outcome_predicate",
            refusal_reason=(
                "reviewed system specs do not interpret the obligation predicate(s) "
                f"{sorted(undefined_obligation)}; without them the narrowing cannot tell whether "
                "S reaches the outcome/post-state the requirement constrains"
            ),
        )

    missing_invariants = [name for name in invariants if name not in owner_of]
    if missing_invariants:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_invariant",
            refusal_reason=(
                "system spec metadata names invariants that the spec body does not "
                f"define: {sorted(missing_invariants)}"
            ),
        )

    constant_block = _render_constant_block(identifier_constants)
    system_variable_blocks = _render_system_variable_blocks(system_variables)
    system_block = "\n\n".join(block for block in system_blocks if block).strip()
    inv_line = "Inv == " + " /\\ ".join([*invariants, "R_Requirement"])
    const_init = _render_const_init(identifier_constants)
    bound_predicates = sorted(
        (set(abstract_predicates) | set(obligation_pred_names)) & defined_predicates
    )

    if post_state_obligation is not None:
        # state_postcondition is a NEXT-RELATION obligation: R adds one ghost VARIABLE that records,
        # after each step, whether the premise held in the PRE-state, and Next conjoins its update
        # (Init sets it FALSE). R_Requirement is then the single-state invariant
        # `nlr_prev_premise => Pred_<state>(<value>)`, so a counterexample is a real S step OUT of a
        # premise-state that fails to establish the post-state — the strict next-step reading.
        #
        # This is encoded as a history-variable STATE invariant rather than the seemingly-direct
        # action invariant `Premise => Pred_<state>' = <value>` because Apalache 0.58 silently SKIPS
        # such an action invariant over a non-establishing / UNCHANGED transition and reports
        # NoError — a false pass on exactly the violation this check must catch (verified
        # empirically). The history-variable state invariant is the only shape the bounded checker
        # verifies soundly here.
        ghost = _NARROWING_POST_STATE_GHOST_VAR
        system_variable_blocks += _render_system_variable_blocks([(ghost, "Bool")])
        requirement_line = f"R_Requirement == {ghost} => {obligation_consequent}"
        init_line = "Init == " + " /\\ ".join([*init_ops, f"{ghost} = FALSE"])
        next_line = "Next == " + " /\\ ".join([*next_ops, f"{ghost}' = ({premise_expr})"])
        narrowing_comment = (
            "\\* ===== Requirement R narrows S's TRANSITIONS into a post-state obligation. R adds\n"
            f"\\* one ghost VARIABLE {ghost} recording, after each step, whether the premise held in\n"
            f"\\* the PRE-state (Next conjoins {ghost}' = the premise over S's unprimed state; Init\n"
            f"\\* sets it FALSE). The obligation {obligation_phrase} — checked as the state invariant\n"
            f"\\* R_Requirement == {ghost} => <post-state>, so a counterexample is a real S step out\n"
            "\\* of a premise-state that fails to establish the required post-state (the strict\n"
            "\\* next-step reading). Apalache 0.58 silently false-passes a primed-variable action\n"
            "\\* invariant over a non-establishing step, so the faithful Next-relation check is this\n"
            "\\* history-variable state invariant. =====\n"
        )
    else:
        requirement_line = f"R_Requirement == {premise_expr} => {obligation_consequent}"
        init_line = "Init == " + " /\\ ".join(init_ops)
        next_line = "Next == " + " /\\ ".join(next_ops)
        narrowing_comment = (
            "\\* ===== Requirement R narrows S: a state invariant over S's own variables. R adds\n"
            "\\* no transitions and no variable — S's Init/Next are the only state machine. The\n"
            f"\\* obligation {obligation_phrase}\n"
            "\\* while the premise holds, so a counterexample is a real S behavior — not an artifact\n"
            "\\* of a requirement harness stepping its own state. =====\n"
        )

    module_text = (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"{constant_block}"
        f"{system_variable_blocks}"
        f"\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
        f"{system_block}\n\n"
        f"{narrowing_comment}"
        f"{requirement_line}\n\n"
        f"\\* ===== S ∧ R: S's reachable states must preserve S's invariants and R's obligation =====\n"
        f"{init_line}\n"
        f"{next_line}\n"
        f"{inv_line}\n"
        f"{const_init}\n"
        f"====\n"
    )
    bound_state_invariants = (
        [
            {
                "kind": "numeric_invariant",
                "premise_expr": numeric_invariant_obligation.premise_expr,
                "obligation_expr": numeric_invariant_obligation.obligation_expr,
                "variables": list(numeric_invariant_obligation.variables),
            }
        ]
        if numeric_invariant_obligation is not None
        else []
    )

    return ComposedSandRModule(
        status="composed",
        module_text=module_text,
        preserved_invariants=[*invariants, "R_Requirement"],
        bound_predicates=bound_predicates,
        bound_state_invariants=bound_state_invariants,
    )


# Sentinel recorded as a declaration's type annotation when a single ``\* @type:`` comment
# precedes a *multi-name* comma-separated CONSTANTS/VARIABLES line. Apalache itself rejects that
# form ("Expected a type annotation for VARIABLE <second-name>"), so the composition refuses it
# (``unsupported_spec_variable``) rather than guess that one annotation types every name. The
# reviewed S must use the parser-supported per-variable single-line form (one ``@type`` comment
# immediately followed by one ``VARIABLE name`` line) for the composition to preserve its declared
# types. Constants are refused wholesale upstream, so only the variable path inspects this sentinel.
_AMBIGUOUS_MULTI_NAME_TYPE = "__nlr_ambiguous_multi_name_type__"


def _decl_names(remainder: str) -> list[str] | None:
    """Return the bare identifiers a declaration's name list holds, or None if it is not one.

    ``remainder`` is everything after the ``CONSTANT[S]``/``VARIABLE[S]`` keyword on its line —
    e.g. ``log, currentTerm, votedFor, state`` — split on commas and trimmed. Returns the names
    in order when every token is a bare identifier; returns None otherwise so the caller leaves
    the line in the spec body untouched rather than misclassifying a form it cannot pin (a
    parametrized constant ``Foo(_)``, a tuple, or a trailing same-line comment). Returning None
    is fail-closed: an unparsed declaration left in the body is never pinned by ConstInit (a
    constant) nor re-emitted with the Apalache type annotation a variable needs, so it cannot
    yield a spurious ``valid`` — Apalache fails the check on the unbound constant or untyped
    variable instead.
    """
    import re

    tokens = [token.strip() for token in remainder.split(",")]
    if tokens and all(re.fullmatch(r"\w+", token) for token in tokens):
        return tokens
    return None


def _split_declarations(
    operator_body: str,
) -> tuple[list[tuple[str, str | None]], list[tuple[str, str | None]], str]:
    """Separate CONSTANT/VARIABLE declarations from a spec's operator definitions.

    Returns ``(constants, variables, body_without_declarations)`` where constants and
    variables are ``(name, type_annotation_or_None)``. Both the singular keywords
    (``CONSTANT``/``VARIABLE``) and the plural forms real TLA uses for several names
    (``CONSTANTS``/``VARIABLES``, e.g. ``VARIABLES log, currentTerm, votedFor, state``) are
    recognized, and a comma-separated name list on one line yields one entry per name — so a
    reviewed spec's constants and variables reach the composition's refusal guards
    (``unsupported_spec_constant``, ``variable_name_collision``) instead of slipping through
    into the body unexamined.

    An Apalache ``\\* @type: …;`` comment immediately preceding a *single-name* declaration is
    consumed with it (and re-emitted by the composition); a ``@type`` comment preceding an
    operator *definition* (e.g. a predicate) is kept in the body. An *untyped* comma-separated
    declaration (no preceding ``@type``) yields one untyped entry per name (each defaults to
    ``Str`` on re-emit). A *typed* comma-separated declaration — one ``@type`` comment over several
    names — tags each name with the ``_AMBIGUOUS_MULTI_NAME_TYPE`` sentinel so the composition
    REFUSES it (``unsupported_spec_variable``): a single annotation cannot type several names, and
    Apalache itself rejects the form ("Expected a type annotation for VARIABLE <second>"). Per-name
    types require the supported single-name declaration form: one ``@type`` comment immediately
    followed by one ``VARIABLE name`` line.

    The composition re-emits declarations at the top so a predicate that reads a spec variable
    is not declared after its use.

    TODO: this reads only single-line declarations. Two real-TLA forms still fall through to the
    body unparsed: (1) Apalache's *block form*, where the keyword stands alone on its line and
    each name follows on its own line with its own ``\\* @type: …;`` comment; and (2) a
    declaration with a trailing same-line comment. TLA+ permits declarations and definitions in
    any order, so an unparsed declaration left mid-body is NOT a parse error — but it is still
    fail-closed: an unparsed CONSTANT is never pinned by ConstInit (the check cannot complete
    over an unbound constant) and, on the post_state path, a block-declared ``nlr_prev_premise``
    duplicates the ghost VARIABLE the composition injects, so no unparsed form yields a spurious
    ``valid``. Extend ``_decl_names`` and this loop to read the block form before treating an
    arbitrary reviewed ``S`` as fully real-spec-ready.
    """
    import re

    lines = operator_body.splitlines()
    constants: list[tuple[str, str | None]] = []
    variables: list[tuple[str, str | None]] = []
    kept: list[str] = []
    index = 0
    total = len(lines)
    decl_re = re.compile(r"\s*(CONSTANT|VARIABLE)S?\s+(.+?)\s*$")
    type_re = re.compile(r"\s*\\\*\s*@type:\s*(.+?);\s*$")
    while index < total:
        line = lines[index]
        type_match = type_re.match(line)
        next_line = lines[index + 1] if index + 1 < total else ""
        paired_decl = decl_re.match(next_line) if type_match else None
        paired_names = _decl_names(paired_decl.group(2)) if paired_decl else None
        if type_match and paired_names is not None:
            bucket = constants if paired_decl.group(1) == "CONSTANT" else variables
            # A single preceding @type comment annotates a single-name declaration. Over a
            # comma-separated declaration one comment cannot type several names — Apalache itself
            # rejects the form ("Expected a type annotation for VARIABLE <second>") — so each name
            # is tagged with the ambiguous-type sentinel and the composition refuses it
            # (unsupported_spec_variable) rather than guess that one annotation types every name and
            # silently check the reviewed S against a changed variable surface.
            if len(paired_names) == 1:
                bucket.append((paired_names[0], type_match.group(1).strip()))
            else:
                bucket.extend((name, _AMBIGUOUS_MULTI_NAME_TYPE) for name in paired_names)
            index += 2
            continue
        bare_decl = decl_re.match(line)
        bare_names = _decl_names(bare_decl.group(2)) if bare_decl else None
        if bare_names is not None:
            bucket = constants if bare_decl.group(1) == "CONSTANT" else variables
            bucket.extend((name, None) for name in bare_names)
            index += 1
            continue
        kept.append(line)
        index += 1
    return constants, variables, "\n".join(kept).strip()


def _render_system_variable_blocks(variables: list[tuple[str, str | None]]) -> str:
    """Render each system spec variable as its own Apalache-typed VARIABLE block."""
    blocks = []
    for name, type_annotation in variables:
        annotation = type_annotation or "Str"
        blocks.append(f"VARIABLE\n  \\* @type: {annotation};\n  {name}\n\n")
    return "".join(blocks)


def parse_lowered_identifier_constants(module_text: str) -> list[str]:
    """Return non-predicate ``CONSTANT`` names declared in a lowered module.

    These are the scope identifiers (e.g. ``redemption``, ``wallet``) that the
    composition re-declares in a single Apalache-typed CONSTANT block and pins
    via ConstInit. ``Pred_*`` constants are excluded — the system spec binds
    those with concrete operator definitions.
    """
    import re

    names: list[str] = []
    for match in re.finditer(r"^CONSTANT (\w+)\s*$", module_text, re.MULTILINE):
        name = match.group(1)
        if not name.startswith("Pred_"):
            names.append(name)
    return names


def parse_lowered_variable_name(module_text: str) -> str | None:
    """Return the single VARIABLE name declared in a lowered module, or None."""
    import re

    match = re.search(r"^VARIABLE (\w+)\s*$", module_text, re.MULTILINE)
    return match.group(1) if match else None


def extract_lowered_logic_body(module_text: str) -> str:
    """Return the operator-definition body of a lowered module (Init … last op).

    Slices from the first top-level operator definition (``Init ==``) through to
    the line before the module terminator, dropping the declaration headers whose
    Apalache type-annotation placement the composition re-emits in its own form.
    """
    import re

    lines = module_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^Init\s*==", line):
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].strip() == "====":
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def parse_operator_definition_names(module_text: str) -> list[str]:
    """Return top-level operator names defined (``Name == …`` / ``Name(a) == …``).

    Anchored at line start with no leading whitespace, so continuation lines of a
    multi-line definition (``  /\\ NLRState = "idle"``) and single-``=`` equalities
    are not mistaken for definitions.
    """
    import re

    return re.findall(r"^(\w+)\s*(?:\([^)]*\))?\s*==", module_text, re.MULTILINE)


def _parse_premise_expression(logic_body: str) -> str | None:
    """Return the RHS of the lowered requirement's ``Premise == …`` definition.

    The premise is a conjunction of the requirement's abstract ``Pred_*`` predicates over
    its scope identifiers (e.g. ``Pred_not_authorized(wallet)``). The stateful-S narrowing
    reuses it verbatim as the antecedent of the obligation invariant — S interprets the
    same predicates over its own state, so the antecedent fires exactly when S's reachable
    state satisfies the precondition.
    """
    import re

    match = re.search(r"^Premise\s*==\s*(.+?)\s*$", logic_body, re.MULTILINE)
    return match.group(1).strip() if match else None


def _strip_spec_operator_body(spec_text: str) -> str:
    """Strip a system spec down to its inlinable operator definitions.

    Removes the ``---- MODULE … ----`` / ``====`` wrapper and any EXTENDS line
    (the composed module supplies Naturals/TLC), leaving operator definitions and
    their type-annotation comments intact for verbatim inlining.
    """
    import re

    lines = spec_text.splitlines()
    if lines and lines[0].startswith("---- MODULE "):
        lines = lines[1:]
    if lines and lines[-1].strip() == "====":
        lines = lines[:-1]
    kept = [line for line in lines if not re.match(r"^EXTENDS\b", line.strip())]
    return "\n".join(kept).strip()


def _render_constant_block(identifier_constants: list[str]) -> str:
    """Render identifier constants as one Apalache-typed CONSTANT block."""
    if not identifier_constants:
        return ""
    entries = ",\n".join(
        f"  \\* @type: Str;\n  {name}" for name in identifier_constants
    )
    return f"CONSTANT\n{entries}\n\n"


def _render_variable_block(variable_name: str) -> str:
    """Render the requirement's state variable as an Apalache-typed VARIABLE block."""
    return f"VARIABLE\n  \\* @type: Str;\n  {variable_name}\n\n"


def _render_const_init(identifier_constants: list[str]) -> str:
    """Render a ConstInit that pins each identifier constant to a model value."""
    if not identifier_constants:
        return "ConstInit == TRUE"
    conjuncts = " /\\ ".join(f'{name} = "{name}"' for name in identifier_constants)
    return f"ConstInit == {conjuncts}"
