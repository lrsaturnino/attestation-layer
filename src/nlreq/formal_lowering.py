from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .models import RequirementIRV2, SemanticNode


FORMAL_LOWERING_VERSION = "0.2"


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
        f"\\* @type: {_pred_type_annotation(args)};\nCONSTANT {_pred_name(name)}({', '.join('_' for _ in args)})"
        for name, args in predicates
        if args  # validation must have refused empty-arg predicates before reaching here
    )

    premise_parts = [
        f"{_pred_name(name)}({', '.join(args)})"
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
    return OutcomePredicate(name=_pred_name(action_name), args=tuple(subject))


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
    ``operator_name_collision``, ``undefined_predicate``, or
    ``undefined_invariant`` (stateless S, Case A); the stateful-S narrowing (Case B)
    additionally uses ``incomplete_transition_operators``,
    ``unsupported_spec_constant``, ``variable_name_collision``,
    ``undefined_transition_operator``, ``missing_outcome_predicate``, and
    ``undefined_outcome_predicate``.
    """

    status: Literal["composed", "refused"]
    module_text: str | None = None
    refusal_kind: str | None = None
    refusal_reason: str | None = None
    preserved_invariants: list[str] = field(default_factory=list)
    bound_predicates: list[str] = field(default_factory=list)


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
      unused — R's harness models the accepted/rejected outcome itself.
    - Stateful S (Case B): S brings its own ``Init``/``Next`` over its own
      variables, and R *narrows* it. The composition uses S's real ``Init``/``Next``
      as the only state machine and conjoins ``Premise => ~Pred_<action>(subject)``
      — the requirement obligation as a pure state invariant over S's variables —
      into ``Inv``. R adds NO transitions and NO variable: a counterexample is a
      real S behavior reaching the forbidden outcome while the premise holds, not an
      artifact of R's own harness stepping. ``outcome_predicate`` names the forbidden
      ``Pred_<action>`` (from the IR via ``derive_outcome_predicate``); S must
      interpret it or the composition refuses. See _compose_system_narrowing.
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
    # S: S's own Init/Next are the only state machine and R contributes a state invariant
    # (Premise => ~Pred_<action>) conjoined into Inv. Otherwise S is a stateless set of
    # predicate interpretations + invariants and R supplies the only state machine (Case A).
    if any(c.init_op or c.next_op for c in contributions):
        return _compose_system_narrowing(
            module_name=module_name,
            identifier_constants=identifier_constants,
            abstract_predicates=abstract_predicates,
            logic_body=logic_body,
            contributions=contributions,
            outcome_predicate=outcome_predicate,
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


def _compose_system_narrowing(
    *,
    module_name: str,
    identifier_constants: list[str],
    abstract_predicates: list[str],
    logic_body: str,
    contributions: list[SystemSpecContribution],
    outcome_predicate: OutcomePredicate | None,
) -> ComposedSandRModule:
    """Compose S ∧ R as a *narrowing* when S brings its own transition system (Case B).

    S's own ``Init``/``Next`` are the sole state machine; R adds no transitions and no
    variable. R contributes a single state invariant
    ``R_Requirement == Premise => ~Pred_<action>(subject)`` — the obligation re-expressed
    over S's state through the shared predicates — conjoined with S's named invariants into
    ``Inv``. A model checker then verifies ``Spec => []Inv`` against S's *real* transitions,
    so a counterexample is a genuine S behavior that reaches the forbidden outcome (the
    action accepted/executed) while the premise holds — not an artifact of a requirement
    harness stepping its own variable, which the prior synchronous product admitted.

    Soundness note. ``R_Requirement`` is a single-state safety invariant: it forbids any
    reachable state where the premise holds *and* the forbidden outcome holds. This captures
    "if the precondition holds, the action must not be executed" soundly precisely when S
    models the precondition as stable through the forbidden transition — i.e. the step that
    reaches ``Pred_<action>`` does not in the same step clear the premise. Reviewed specs
    that gate an outcome on a persisting precondition satisfy this; a future temporal lowering
    of the event/causal fragments generalises it without the stability assumption.

    Refuses, rather than emitting a meaningless module, when: a spec declares only one of
    init_op/next_op; a named transition operator is undefined; a spec brings its own CONSTANTS
    (the composition cannot pin them in ConstInit); two specs declare the same variable; an S
    operator shadows a reserved name; a premise predicate is uninterpreted; the forbidden
    outcome predicate was not supplied or is uninterpreted by S; or no invariant is declared.
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

    if outcome_predicate is None:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="missing_outcome_predicate",
            refusal_reason=(
                "no forbidden-outcome predicate was supplied; narrowing a stateful S needs "
                "the requirement's Pred_<action> to constrain S's reachable states"
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

    if outcome_predicate.name not in defined_predicates:
        return ComposedSandRModule(
            status="refused",
            refusal_kind="undefined_outcome_predicate",
            refusal_reason=(
                "reviewed system specs do not interpret the forbidden-outcome predicate "
                f"{outcome_predicate.name!r}; without it the narrowing cannot tell whether "
                "S reaches the outcome the requirement forbids"
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
    outcome_call = (
        f"{outcome_predicate.name}({', '.join(outcome_predicate.args)})"
        if outcome_predicate.args
        else outcome_predicate.name
    )
    requirement_line = f"R_Requirement == {premise_expr} => ~{outcome_call}"
    init_line = "Init == " + " /\\ ".join(init_ops)
    next_line = "Next == " + " /\\ ".join(next_ops)
    inv_line = "Inv == " + " /\\ ".join([*invariants, "R_Requirement"])
    const_init = _render_const_init(identifier_constants)
    bound_predicates = sorted(
        (set(abstract_predicates) | {outcome_predicate.name}) & defined_predicates
    )

    module_text = (
        f"---- MODULE {module_name} ----\n"
        f"EXTENDS Naturals, TLC\n\n"
        f"{constant_block}"
        f"{system_variable_blocks}"
        f"\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
        f"{system_block}\n\n"
        f"\\* ===== Requirement R narrows S: a state invariant over S's own variables. R adds\n"
        f"\\* no transitions and no variable — S's Init/Next are the only state machine. The\n"
        f"\\* obligation forbids S reaching the accepted/executed outcome ({outcome_predicate.name})\n"
        f"\\* while the premise holds, so a counterexample is a real S behavior — not an artifact\n"
        f"\\* of a requirement harness stepping its own state. =====\n"
        f"{requirement_line}\n\n"
        f"\\* ===== S ∧ R: S's reachable states must preserve S's invariants and R's obligation =====\n"
        f"{init_line}\n"
        f"{next_line}\n"
        f"{inv_line}\n"
        f"{const_init}\n"
        f"====\n"
    )
    return ComposedSandRModule(
        status="composed",
        module_text=module_text,
        preserved_invariants=[*invariants, "R_Requirement"],
        bound_predicates=bound_predicates,
    )


def _split_declarations(
    operator_body: str,
) -> tuple[list[tuple[str, str | None]], list[tuple[str, str | None]], str]:
    """Separate CONSTANT/VARIABLE declarations from a spec's operator definitions.

    Returns ``(constants, variables, body_without_declarations)`` where constants and
    variables are ``(name, type_annotation_or_None)``. An Apalache ``\\* @type: …;``
    comment immediately preceding a declaration is consumed with it (and re-emitted by the
    composition); a ``@type`` comment preceding an operator *definition* (e.g. a predicate)
    is kept in the body. The composition re-emits declarations at the top so a predicate
    that reads a spec variable is not declared after its use.
    """
    import re

    lines = operator_body.splitlines()
    constants: list[tuple[str, str | None]] = []
    variables: list[tuple[str, str | None]] = []
    kept: list[str] = []
    index = 0
    total = len(lines)
    decl_re = re.compile(r"\s*(CONSTANT|VARIABLE)\s+(\w+)")
    type_re = re.compile(r"\s*\\\*\s*@type:\s*(.+?);\s*$")
    while index < total:
        line = lines[index]
        type_match = type_re.match(line)
        next_line = lines[index + 1] if index + 1 < total else ""
        paired_decl = decl_re.match(next_line) if type_match else None
        if type_match and paired_decl:
            entry = (paired_decl.group(2), type_match.group(1).strip())
            (constants if paired_decl.group(1) == "CONSTANT" else variables).append(entry)
            index += 2
            continue
        bare_decl = decl_re.match(line)
        if bare_decl:
            entry = (bare_decl.group(2), None)
            (constants if bare_decl.group(1) == "CONSTANT" else variables).append(entry)
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
