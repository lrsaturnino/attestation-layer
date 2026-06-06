from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .controlled_semantics import ClaimClass, build_controlled_requirement_semantics_reference
from .formal_lowering import pred_name
from .jsonutil import canonical_json, sha256_json
from .models import EvidenceLevel, RequirementIRV2, SemanticNode, SourceSpan, TemporalBound, ValueRef
from .proof_closure import ProofDispatchPlan, ProofPremiseRoute


FORMAL_CLAIM_SCHEMA_VERSION = "0.1"
FORMAL_CLAIM_TOOL_VERSION = "0.1"


FormalClaimRole = Literal["scope", "premise", "action", "obligation"]
FormalClaimFragmentKind = Literal[
    "scope",
    "predicate",
    "comparison",
    "membership",
    "action",
    "success",
    "rejection_order",
    "post_state",
    "event_emission",
    "state_invariant",
    "causal_transition",
]


class FormalClaimOperand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["identifier", "number", "string"]
    value: str | int | float


class FormalClaimTemporalBound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | float
    unit: Literal["second", "minute", "hour", "day", "block"]


class FormalClaimFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment_id: str
    source_node_id: str
    role: FormalClaimRole
    kind: FormalClaimFragmentKind
    canonical: str
    predicate: str | None = None
    operator: Literal["eq", "neq", "lt", "lte", "gt", "gte", "in"] | None = None
    operands: list[FormalClaimOperand] = Field(default_factory=list)
    temporal_bound: FormalClaimTemporalBound | None = None
    source_spans: list[SourceSpan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormalClaimUnsupportedFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: str
    reason: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class FormalClaimSemanticsRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    claim_class: ClaimClass | None = None
    text: str


class FormalClaimSemanticsCompletionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_class: ClaimClass
    supported: bool
    exact_semantics: str
    supported_fragment_kinds: list[FormalClaimFragmentKind] = Field(default_factory=list)
    required_evidence: list[EvidenceLevel] = Field(default_factory=list)
    backend_projection_obligations: list[str] = Field(default_factory=list)
    trace_validation_obligations: list[str] = Field(default_factory=list)
    unsupported_behavior: str
    limitations: list[str] = Field(default_factory=list)


class FormalClaimSemanticsCompletionReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_CLAIM_SCHEMA_VERSION
    result: Literal["complete", "incomplete"]
    semantics_profile: str
    claim_classes: list[FormalClaimSemanticsCompletionEntry] = Field(default_factory=list)
    missing_claim_classes: list[str] = Field(default_factory=list)
    evidence_matrix_hash: str
    refusal_rules: list[str] = Field(default_factory=list)
    tool: str = "nlreq.formal_claim"
    tool_version: str = FORMAL_CLAIM_TOOL_VERSION


class FormalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_CLAIM_SCHEMA_VERSION
    claim_id: str
    requirement_id: str
    source_ir_version: Literal["0.2"]
    source_ir_hash: str
    claim_class: ClaimClass
    semantics_profile: str
    scope: list[FormalClaimFragment] = Field(default_factory=list)
    premises: list[FormalClaimFragment] = Field(default_factory=list)
    action: FormalClaimFragment
    obligations: list[FormalClaimFragment] = Field(default_factory=list)
    canonical_formula: str
    source_spans: list[SourceSpan] = Field(default_factory=list)
    node_map: dict[str, str] = Field(default_factory=dict)
    required_evidence: list[EvidenceLevel] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormalClaimLoweringReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_CLAIM_SCHEMA_VERSION
    requirement_id: str
    result: Literal["lowered", "refused", "needs_review"]
    source_ir_hash: str
    formal_claim: FormalClaim | None = None
    unsupported_fragments: list[FormalClaimUnsupportedFragment] = Field(default_factory=list)
    semantics_rules: list[FormalClaimSemanticsRule] = Field(default_factory=list)
    refusal_code: str | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.formal_claim"
    tool_version: str = FORMAL_CLAIM_TOOL_VERSION


def build_formal_claim(requirement: RequirementIRV2) -> FormalClaimLoweringReport:
    source_ir_hash = sha256_json(requirement)
    claim_class = _claim_class(requirement)
    rules = _semantics_rules(claim_class)
    unsupported = _unsupported_fragments(requirement.semantic_ir)
    if claim_class is None:
        unsupported.append(
            FormalClaimUnsupportedFragment(
                node_id=requirement.semantic_ir.node_id,
                kind=requirement.semantic_ir.kind,
                reason="semantic root does not declare a supported requirement_class",
                source_spans=requirement.semantic_ir.source_spans,
                next_actions=["Use a supported DSL v3 requirement class."],
            )
        )
    if unsupported or claim_class is None:
        return FormalClaimLoweringReport(
            requirement_id=requirement.requirement_id,
            result="refused",
            source_ir_hash=source_ir_hash,
            unsupported_fragments=unsupported,
            semantics_rules=rules,
            refusal_code="NLR-SEMANTIC-UNSUPPORTED",
            input_hashes={"requirement_ir": source_ir_hash},
        )

    scope = [_scope_fragment(node) for node in requirement.semantic_ir.scope]
    premises = _premise_fragments(requirement.semantic_ir.premise)
    action = _action_fragment(requirement.semantic_ir.obligation.action)
    obligations = _obligation_fragments(requirement.semantic_ir.obligation.must)
    fragments = [*scope, *premises, action, *obligations]
    formula = _canonical_formula(scope, premises, action, obligations)
    claim = FormalClaim(
        claim_id=f"FC-{requirement.requirement_id}",
        requirement_id=requirement.requirement_id,
        source_ir_version=requirement.ir_version,
        source_ir_hash=source_ir_hash,
        claim_class=claim_class,
        semantics_profile=f"dsl-v3/{claim_class}",
        scope=scope,
        premises=premises,
        action=action,
        obligations=obligations,
        canonical_formula=formula,
        source_spans=requirement.semantic_ir.source_spans,
        node_map={fragment.source_node_id: fragment.fragment_id for fragment in fragments},
        required_evidence=_required_evidence_for_claim_class(claim_class),
        metadata={"canonical_signature_hash": sha256_json(_claim_signature_parts(scope, premises, action, obligations))},
    )
    return FormalClaimLoweringReport(
        requirement_id=requirement.requirement_id,
        result="lowered",
        source_ir_hash=source_ir_hash,
        formal_claim=claim,
        semantics_rules=rules,
        input_hashes={"requirement_ir": source_ir_hash, "formal_claim": sha256_json(claim)},
    )


def build_formal_claim_semantics_completion_reference() -> FormalClaimSemanticsCompletionReference:
    reference = build_controlled_requirement_semantics_reference()
    entries = [
        FormalClaimSemanticsCompletionEntry(
            claim_class=claim.claim_class,
            supported=claim.supported,
            exact_semantics=claim.canonical_rule,
            supported_fragment_kinds=_supported_fragment_kinds_for_claim_class(claim.claim_class),
            required_evidence=claim.required_evidence,
            backend_projection_obligations=_backend_projection_obligations(claim.claim_class),
            trace_validation_obligations=_trace_validation_obligations(claim.required_evidence),
            unsupported_behavior=(
                "Unknown claim classes, unsupported semantic-node kinds, missing temporal "
                "bounds, and unsupported premise or obligation shapes refuse before backend dispatch."
            ),
            limitations=claim.limitations,
        )
        for claim in reference.claim_classes
    ]
    expected = {
        "authorization_precondition",
        "state_precondition",
        "state_postcondition",
        "numeric_invariant",
        "event_state_correspondence",
        "bounded_temporal",
        "cross_module_causal_obligation",
    }
    present = {entry.claim_class for entry in entries}
    missing = sorted(expected - present)
    return FormalClaimSemanticsCompletionReference(
        result="incomplete" if missing else "complete",
        semantics_profile="dsl-v3/formal-claim-semantics-0.1",
        claim_classes=entries,
        missing_claim_classes=missing,
        evidence_matrix_hash=sha256_json(
            [
                {
                    "claim_class": entry.claim_class,
                    "required_evidence": entry.required_evidence,
                    "fragments": entry.supported_fragment_kinds,
                }
                for entry in entries
            ]
        ),
        refusal_rules=[
            "No partial formal claim is emitted for unsupported semantic fragments.",
            "Backend projection consumes typed formal fragments, not raw controlled prose.",
            "Bounded temporal and cross-module semantics require explicit temporal bounds.",
            "Formal claim lowering names required evidence but never emits backend evidence.",
        ],
    )


def formal_claim_signature(
    claim: FormalClaim,
    *,
    alpha_identifiers: bool = False,
    commutative: bool = False,
) -> str:
    alpha_map: dict[str, str] = {}
    payload = {
        "claim_class": claim.claim_class,
        "scope": [
            _fragment_signature(fragment, alpha_map=alpha_map, alpha=alpha_identifiers)
            for fragment in claim.scope
        ],
        "premises": [
            _fragment_signature(fragment, alpha_map=alpha_map, alpha=alpha_identifiers)
            for fragment in claim.premises
        ],
        "action": _fragment_signature(claim.action, alpha_map=alpha_map, alpha=alpha_identifiers),
        "obligations": [
            _fragment_signature(fragment, alpha_map=alpha_map, alpha=alpha_identifiers)
            for fragment in claim.obligations
        ],
    }
    if commutative:
        payload["premises"] = sorted(payload["premises"], key=repr)
        payload["obligations"] = sorted(payload["obligations"], key=repr)
    return canonical_json(payload)


def formal_claim_to_proof_premise_routes(claim: FormalClaim) -> list[ProofPremiseRoute]:
    """Map FormalClaim fragments to ProofPremiseRoute entries for backend dispatch.

    Each non-scope fragment becomes a typed route. The backend_id is selected
    to match the required evidence level for the fragment kind — ensuring every
    route can be discharged by its routed producer without an evidence mismatch.
    The mapping follows the default_evidence_producer_mapping() producer table.
    """
    routes: list[ProofPremiseRoute] = []
    for fragment in [*claim.premises, *claim.obligations]:
        role: str = fragment.role if fragment.role in {"premise", "obligation"} else "obligation"
        evidence = _evidence_for_fragment_kind(fragment.kind)
        backend = _backend_for_fragment_kind(fragment.kind, evidence)
        routes.append(
            ProofPremiseRoute(
                premise_id=fragment.fragment_id,
                node_id=fragment.source_node_id,
                node_kind=fragment.kind,
                role=role,  # type: ignore[arg-type]
                backend_id=backend,
                required_evidence=evidence,
                reason=f"formal claim fragment {fragment.kind} routed to {backend}",
                routing_mode="formal_claim",
            )
        )
    return routes


def build_proof_dispatch_plan_from_formal_claim(claim: FormalClaim) -> ProofDispatchPlan:
    """Build a ProofDispatchPlan whose routes correspond to FormalClaim fragment IDs.

    Each premise/obligation fragment becomes one route. Callers pass the returned
    plan as dispatch= to build_proof_object so that ProofObject.premises[*].premise_id
    contains the formal fragment IDs.
    """
    routes = formal_claim_to_proof_premise_routes(claim)
    return ProofDispatchPlan(
        policy_id=f"formal-claim:{claim.claim_id}",
        routes=routes,
    )


def formal_claim_fragment_bound_predicate(fragment: FormalClaimFragment) -> str | None:
    """The ``Pred_*`` operator a fragment contributes to the composed S ∧ R module, or None.

    Coverage of an S ∧ R-discharged fragment is anchored to the composition's real
    ``bound_predicates`` rather than to a static fragment-kind table: a fragment is only
    "covered" by the model check when its operator was actually bound into the module the
    checker ran. A premise ``predicate`` binds ``Pred_<predicate>``; a ``rejection_order``
    obligation binds the forbidden-outcome ``Pred_<action>`` (its first operand); a
    ``post_state`` obligation binds the affirmed post-state ``Pred_<state>`` (its state operand,
    the operator ``derive_post_state_obligation`` names). Other kinds the lowering does not bind
    return None, so a fragment whose predicate never reaches the module cannot be falsely
    discharged.
    """
    if fragment.kind == "predicate" and fragment.predicate:
        return pred_name(fragment.predicate)
    if fragment.kind == "rejection_order" and fragment.operands:
        return pred_name(str(fragment.operands[0].value))
    if fragment.kind == "post_state" and fragment.operands:
        return pred_name(str(fragment.operands[0].value))
    return None


def _evidence_for_fragment_kind(kind: FormalClaimFragmentKind) -> EvidenceLevel:
    _map: dict[FormalClaimFragmentKind, EvidenceLevel] = {
        # A premise predicate is an uninterpreted boolean: it has no fragment-level SMT
        # content (a free boolean is trivially SAT — see formal_claim_smt), so it is
        # discharged only by the requirement-level S ∧ R model check that interprets it
        # under a reviewed S. Its honest level is therefore BOUNDED_CHECKED (bounded model
        # checking), not SMT_CHECKED. Comparison/membership stay SMT (Z3 theories, PB-6).
        "predicate": EvidenceLevel.BOUNDED_CHECKED,
        "comparison": EvidenceLevel.SMT_CHECKED,
        "membership": EvidenceLevel.SMT_CHECKED,
        # A post_state obligation (``premise => post_state(state, value)``) is a stateful safety
        # obligation over S's transition relation: it asserts that EVERY premise-satisfying
        # behaviour of S reaches the post-state, which only the bounded S ∧ R ``Next`` check can
        # establish. A trace producer observing one execution reach that state proves nothing about
        # the universally-quantified obligation, so TRACE_VALIDATED would let a single observed run
        # discharge a claim the ``Next`` relation never verified. Its honest level is therefore
        # BOUNDED_CHECKED, matching the state/temporal kinds below and the kind-only proof router
        # (proof_closure._STATE_TEMPORAL_NODE_KINDS). Contrast ``event_emission``, which stays
        # TRACE_VALIDATED: "the event was observed" IS an execution observation, not a Next-relation
        # safety obligation.
        "post_state": EvidenceLevel.BOUNDED_CHECKED,
        "event_emission": EvidenceLevel.TRACE_VALIDATED,
        "state_invariant": EvidenceLevel.BOUNDED_CHECKED,
        "causal_transition": EvidenceLevel.BOUNDED_CHECKED,
        "rejection_order": EvidenceLevel.BOUNDED_CHECKED,
        "success": EvidenceLevel.TEST_VALIDATED,
        "scope": EvidenceLevel.CONSISTENCY_CHECKED,
        "action": EvidenceLevel.CONSISTENCY_CHECKED,
    }
    return _map.get(kind, EvidenceLevel.CONSISTENCY_CHECKED)


# Fragment kinds the gate's S ∧ R model check discharges directly. The authorization
# lowering encodes the premise predicate(s) and the rejection-order outcome into the
# composed module's Inv (Premise => ~Pred_<action>), which the bounded model checker
# verifies as one obligation. They therefore route to ``solver_system_checker`` — the
# producer that runs ``check_solver_backed_system_consistency`` — at BOUNDED_CHECKED, not
# to a fragment-level SMT producer that has no module to check them against.
# ``post_state`` joins them: it is the state-postcondition obligation re-expressed over S's
# variables as the affirmed invariant ``Premise => Pred_<state>(<value>)``, a single-state safety
# obligation the same bounded S ∧ R ``Next`` check verifies — never a trace observation. The
# stateful-S narrowing (PB-4) binds ``Pred_<state>`` into the checked module, so a valid verdict
# covers and discharges the ``post_state`` fragment and a counterexample blocks it; without a
# reviewed stateful S the composition refuses and the premise stays open, never discharging on
# lower-grade trace evidence.
_S_AND_R_DISCHARGED_KINDS: frozenset[FormalClaimFragmentKind] = frozenset(
    {"predicate", "rejection_order", "post_state"}
)

# Per-premise theory routing (PB-7). Comparison premises are discharged by the z3 Int/Real
# linear-arithmetic backend (``smt-theories``, formal_claim_smt); set-membership premises by cvc5's
# native finite-set theory (``cvc5``, cvc5_backend). Two independent solvers, each its own producer:
# a theory-checked premise is therefore never tagged with the propositional ``core_smt`` encoder that
# drops comparison/membership ops, and the two backends' verdicts also feed the cross-backend
# agreement check. An opaque named-set membership has no concrete members to encode, so cvc5 supplies
# no result and its route stays open — the honest outcome for a premise nothing here can discharge.
_SMT_THEORY_DISCHARGED_KINDS: dict[FormalClaimFragmentKind, str] = {
    "comparison": "smt-theories",
    "membership": "cvc5",
}


def _backend_for_fragment_kind(kind: FormalClaimFragmentKind, evidence: EvidenceLevel) -> str:
    """Return the backend_id that discharges a fragment of this kind at ``evidence`` (PB-7 routing).

    Predicate/rejection-order fragments the S ∧ R composition checks route to
    ``solver_system_checker``; comparison/membership premises route to their theory-aware SMT backend
    (``smt-theories``/``cvc5``); everything else falls back to the evidence-level default.
    """
    if kind in _S_AND_R_DISCHARGED_KINDS:
        return "solver_system_checker"
    theory_backend = _SMT_THEORY_DISCHARGED_KINDS.get(kind)
    if theory_backend is not None:
        return theory_backend
    return _backend_for_evidence(evidence)


def _backend_for_evidence(evidence: EvidenceLevel) -> str:
    """Return a backend_id whose allowed_evidence_levels includes evidence.

    Must stay in sync with proof_closure.default_evidence_producer_mapping().
    """
    _map: dict[EvidenceLevel, str] = {
        EvidenceLevel.SMT_CHECKED: "core_smt",
        EvidenceLevel.BOUNDED_CHECKED: "apalache",
        EvidenceLevel.TRACE_VALIDATED: "trace_validation",
        EvidenceLevel.TEST_VALIDATED: "command",
        EvidenceLevel.CONSISTENCY_CHECKED: "system_checker",
        EvidenceLevel.PROVEN_INDUCTIVE: "tlaps",
        EvidenceLevel.REVIEWED: "human_review",
    }
    return _map.get(evidence, "system_checker")


def _claim_class(requirement: RequirementIRV2) -> ClaimClass | None:
    raw = requirement.semantic_ir.metadata.get("requirement_class")
    supported = {item.claim_class for item in build_controlled_requirement_semantics_reference().claim_classes}
    return raw if raw in supported else None  # type: ignore[return-value]


def _semantics_rules(claim_class: ClaimClass | None) -> list[FormalClaimSemanticsRule]:
    reference = build_controlled_requirement_semantics_reference()
    rules = [
        FormalClaimSemanticsRule(
            rule_id="no-partial-unsupported-lowering",
            text="Unsupported semantic fragments produce refused formal-claim lowering.",
        ),
        FormalClaimSemanticsRule(
            rule_id="source-span-preservation",
            text="Every formal claim fragment retains source spans back to controlled text.",
        ),
    ]
    if claim_class is not None:
        claim_semantics = next(item for item in reference.claim_classes if item.claim_class == claim_class)
        rules.append(
            FormalClaimSemanticsRule(
                rule_id=f"claim-class.{claim_class}",
                claim_class=claim_class,
                text=claim_semantics.canonical_rule,
            )
        )
    return rules


def _required_evidence_for_claim_class(claim_class: ClaimClass) -> list[EvidenceLevel]:
    reference = build_controlled_requirement_semantics_reference()
    return next(item.required_evidence for item in reference.claim_classes if item.claim_class == claim_class)


def _supported_fragment_kinds_for_claim_class(claim_class: ClaimClass) -> list[FormalClaimFragmentKind]:
    common: list[FormalClaimFragmentKind] = ["scope", "action"]
    by_claim: dict[str, list[FormalClaimFragmentKind]] = {
        "authorization_precondition": ["predicate", "rejection_order"],
        "state_precondition": ["predicate", "success"],
        "state_postcondition": ["predicate", "comparison", "post_state"],
        "numeric_invariant": ["predicate", "comparison", "membership", "state_invariant"],
        "event_state_correspondence": ["predicate", "event_emission"],
        "bounded_temporal": ["predicate", "comparison", "event_emission"],
        "cross_module_causal_obligation": ["predicate", "causal_transition"],
    }
    return [*common, *by_claim.get(claim_class, [])]


def _backend_projection_obligations(claim_class: ClaimClass) -> list[str]:
    obligations = [
        "Preserve formal fragment IDs in backend artifacts or diagnostics.",
        "Record every bounded check as bounded evidence, not inductive proof.",
        "Return unsupported before execution when a fragment cannot be projected.",
    ]
    if claim_class in {"event_state_correspondence", "bounded_temporal", "cross_module_causal_obligation"}:
        obligations.append("Carry temporal bounds into backend budget metadata.")
    if claim_class == "cross_module_causal_obligation":
        obligations.append("Preserve source and target module names for causal trace joins.")
    return obligations


def _trace_validation_obligations(required_evidence: list[EvidenceLevel]) -> list[str]:
    if EvidenceLevel.TRACE_VALIDATED not in required_evidence:
        return []
    return [
        "Trace validators must map observed events or state changes to formal fragments.",
        "Lossy or missing trace fields cannot satisfy TRACE_VALIDATED evidence.",
    ]


def _unsupported_fragments(node: SemanticNode) -> list[FormalClaimUnsupportedFragment]:
    supported = {
        "rule",
        "forall",
        "and",
        "predicate",
        "membership",
        "eq",
        "neq",
        "lt",
        "lte",
        "gt",
        "gte",
        "action_obligation",
        "action",
        "before",
        "state_ref",
        "post_state",
        "within",
        "event",
        "transition",
    }
    result: list[FormalClaimUnsupportedFragment] = []
    for item in _walk_nodes(node):
        if item.kind not in supported:
            result.append(
                FormalClaimUnsupportedFragment(
                    node_id=item.node_id,
                    kind=item.kind,
                    reason="semantic node kind is not supported by formal claim IR lowering",
                    source_spans=item.source_spans,
                    next_actions=["Rewrite the requirement using a supported controlled construct."],
                )
            )
    return result


def _scope_fragment(node: SemanticNode) -> FormalClaimFragment:
    return FormalClaimFragment(
        fragment_id=f"formal.{node.node_id}",
        source_node_id=node.node_id,
        role="scope",
        kind="scope",
        canonical=f"forall({node.name}:{node.target})",
        operands=[FormalClaimOperand(kind="identifier", value=node.name or "")],
        source_spans=node.source_spans,
        metadata={"target": node.target} if node.target else {},
    )


def _premise_fragments(node: SemanticNode | None) -> list[FormalClaimFragment]:
    if node is None:
        return []
    if node.kind == "and":
        return [_premise_fragment(child) for child in node.children]
    return [_premise_fragment(node)]


def _premise_fragment(node: SemanticNode) -> FormalClaimFragment:
    if node.kind == "predicate":
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="premise",
            kind="predicate",
            canonical=f"{node.name}({_operands_canonical(operands)})",
            predicate=node.name,
            operands=operands,
            source_spans=node.source_spans,
        )
    if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"}:
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="premise",
            kind="comparison",
            canonical=f"{node.kind}({_operands_canonical(operands)})",
            operator=node.kind,  # type: ignore[arg-type]
            operands=operands,
            source_spans=node.source_spans,
        )
    if node.kind == "membership":
        operands = [_operand(arg) for arg in node.args]
        # A set-literal membership (`x is in {A, B}`) carries its members as concrete operands and
        # is marked so the SMT encoder enumerates it; an opaque named-set membership
        # (`x is in S`) carries the set as a single opaque identifier and stays a model-level check.
        metadata = (
            {"membership": "set_literal"}
            if node.metadata.get("membership") == "set_literal"
            else {}
        )
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="premise",
            kind="membership",
            canonical=f"in({_operands_canonical(operands)})",
            operator="in",
            operands=operands,
            source_spans=node.source_spans,
            metadata=metadata,
        )
    raise ValueError(f"unsupported premise node for formal claim lowering: {node.kind}")


def _action_fragment(node: SemanticNode | None) -> FormalClaimFragment:
    if node is None:
        raise ValueError("formal claim requires action node")
    return FormalClaimFragment(
        fragment_id=f"formal.{node.node_id}",
        source_node_id=node.node_id,
        role="action",
        kind="action",
        canonical=f"action({node.name})",
        operands=[FormalClaimOperand(kind="identifier", value=node.name or "")],
        source_spans=node.source_spans,
    )


def _obligation_fragments(node: SemanticNode | None) -> list[FormalClaimFragment]:
    if node is None:
        return []
    if node.kind == "and":
        return [_obligation_fragment(child) for child in node.children]
    return [_obligation_fragment(node)]


def _obligation_fragment(node: SemanticNode) -> FormalClaimFragment:
    if node.kind == "predicate" and node.name == "succeeds":
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="success",
            canonical=f"succeeds({_operands_canonical(operands)})",
            predicate="succeeds",
            operands=operands,
            source_spans=node.source_spans,
        )
    if node.kind == "before":
        reject = node.children[0] if node.children else None
        before = node.children[1] if len(node.children) > 1 else None
        action = reject.args[0].value if reject is not None and reject.args else "unknown"
        state = before.name if before is not None else "unknown"
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="rejection_order",
            canonical=f"rejects_before({action},{state})",
            predicate="rejects_before",
            operands=[
                FormalClaimOperand(kind="identifier", value=str(action)),
                FormalClaimOperand(kind="identifier", value=str(state)),
            ],
            source_spans=node.source_spans,
        )
    if node.kind == "post_state":
        operand = _operand(node.value) if node.value is not None else FormalClaimOperand(kind="identifier", value="unknown")
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="post_state",
            canonical=f"post_state({node.name},{_operand_canonical(operand)})",
            predicate="post_state",
            operands=[FormalClaimOperand(kind="identifier", value=node.name or ""), operand],
            source_spans=node.source_spans,
        )
    if node.kind == "within":
        child = node.children[0] if node.children else None
        temporal_bound = _temporal_bound(node.temporal_bound)
        if child is not None and child.kind == "event":
            return FormalClaimFragment(
                fragment_id=f"formal.{node.node_id}",
                source_node_id=node.node_id,
                role="obligation",
                kind="event_emission",
                canonical=f"within(event({child.name}),{temporal_bound.value},{temporal_bound.unit})",
                predicate="within_event",
                operands=[FormalClaimOperand(kind="identifier", value=child.name or "")],
                temporal_bound=temporal_bound,
                source_spans=node.source_spans,
            )
        if child is not None and child.kind == "transition":
            source_module = str(child.metadata.get("source_module", "unknown"))
            target_module = str(child.metadata.get("target_module", "unknown"))
            return FormalClaimFragment(
                fragment_id=f"formal.{node.node_id}",
                source_node_id=node.node_id,
                role="obligation",
                kind="causal_transition",
                canonical=(
                    f"within(transition({source_module},{target_module},{child.name}),"
                    f"{temporal_bound.value},{temporal_bound.unit})"
                ),
                predicate="within_transition",
                operands=[
                    FormalClaimOperand(kind="identifier", value=source_module),
                    FormalClaimOperand(kind="identifier", value=target_module),
                    FormalClaimOperand(kind="identifier", value=child.name or ""),
                ],
                temporal_bound=temporal_bound,
                source_spans=node.source_spans,
            )
    if node.kind in {"eq", "neq", "lt", "lte", "gt", "gte"}:
        operands = [_operand(arg) for arg in node.args]
        return FormalClaimFragment(
            fragment_id=f"formal.{node.node_id}",
            source_node_id=node.node_id,
            role="obligation",
            kind="state_invariant",
            canonical=f"invariant({node.kind}({_operands_canonical(operands)}))",
            operator=node.kind,  # type: ignore[arg-type]
            operands=operands,
            source_spans=node.source_spans,
        )
    raise ValueError(f"unsupported obligation node for formal claim lowering: {node.kind}")


def _canonical_formula(
    scope: list[FormalClaimFragment],
    premises: list[FormalClaimFragment],
    action: FormalClaimFragment,
    obligations: list[FormalClaimFragment],
) -> str:
    scope_text = " and ".join(fragment.canonical for fragment in scope) or "true"
    premise_text = " and ".join(fragment.canonical for fragment in premises) or "true"
    obligation_text = " and ".join(fragment.canonical for fragment in obligations) or "true"
    return f"{scope_text}: ({premise_text}) => ({action.canonical} requires {obligation_text})"


def _claim_signature_parts(
    scope: list[FormalClaimFragment],
    premises: list[FormalClaimFragment],
    action: FormalClaimFragment,
    obligations: list[FormalClaimFragment],
) -> dict[str, Any]:
    return {
        "scope": [fragment.canonical for fragment in scope],
        "premises": [fragment.canonical for fragment in premises],
        "action": action.canonical,
        "obligations": [fragment.canonical for fragment in obligations],
    }


def _fragment_signature(
    fragment: FormalClaimFragment,
    *,
    alpha_map: dict[str, str],
    alpha: bool,
) -> dict[str, Any]:
    operands = [
        {"kind": operand.kind, "value": _alpha_value(str(operand.value), alpha_map) if alpha and operand.kind == "identifier" else operand.value}
        for operand in fragment.operands
    ]
    if fragment.operator in {"eq", "neq"}:
        operands = sorted(operands, key=repr)
    return {
        "role": fragment.role,
        "kind": fragment.kind,
        "predicate": fragment.predicate,
        "operator": fragment.operator,
        "operands": operands,
        "temporal_bound": fragment.temporal_bound.model_dump(mode="json") if fragment.temporal_bound else None,
        "metadata": fragment.metadata,
    }


def _alpha_value(value: str, alpha_map: dict[str, str]) -> str:
    if value not in alpha_map:
        alpha_map[value] = f"id{len(alpha_map) + 1}"
    return alpha_map[value]


def _operand(value: ValueRef | None) -> FormalClaimOperand:
    if value is None:
        return FormalClaimOperand(kind="identifier", value="unknown")
    return FormalClaimOperand(kind=value.kind, value=value.value)


def _temporal_bound(value: TemporalBound | None) -> FormalClaimTemporalBound:
    if value is None:
        raise ValueError("temporal formal claim fragment requires a temporal bound")
    return FormalClaimTemporalBound(value=value.value, unit=value.unit)


def _operands_canonical(operands: list[FormalClaimOperand]) -> str:
    return ",".join(_operand_canonical(operand) for operand in operands)


def _operand_canonical(operand: FormalClaimOperand) -> str:
    if operand.kind == "string":
        return repr(operand.value)
    return str(operand.value)


def _walk_nodes(node: SemanticNode):
    yield node
    for child in node.scope:
        yield from _walk_nodes(child)
    if node.premise is not None:
        yield from _walk_nodes(node.premise)
    if node.obligation is not None:
        yield from _walk_nodes(node.obligation)
    if node.action is not None:
        yield from _walk_nodes(node.action)
    if node.must is not None:
        yield from _walk_nodes(node.must)
    for child in node.children:
        yield from _walk_nodes(child)
    if isinstance(node.left, SemanticNode):
        yield from _walk_nodes(node.left)
    if isinstance(node.right, SemanticNode):
        yield from _walk_nodes(node.right)
