from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import EvidenceLevel


CONTROLLED_SEMANTICS_SCHEMA_VERSION = "0.1"
CONTROLLED_SEMANTICS_TOOL_VERSION = "0.1"
CONTROLLED_DSL_VERSION = "0.3"


ClaimClass = Literal[
    "authorization_precondition",
    "state_precondition",
    "state_postcondition",
    "numeric_invariant",
    "event_state_correspondence",
    "bounded_temporal",
    "cross_module_causal_obligation",
]


class ControlledConstructSemantics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    construct_id: str
    dsl_fragment: str
    formal_role: Literal["scope", "premise", "obligation", "temporal_bound"]
    canonical_meaning: str
    supported: bool = True
    allowed_claim_classes: list[ClaimClass] = Field(default_factory=list)
    required_evidence: list[EvidenceLevel] = Field(default_factory=list)
    refusal_behavior: str


class ControlledClaimClassSemantics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_class: ClaimClass
    supported: bool
    canonical_rule: str
    required_evidence: list[EvidenceLevel] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ControlledRequirementSemanticsReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CONTROLLED_SEMANTICS_SCHEMA_VERSION
    dsl_version: Literal["0.3"] = CONTROLLED_DSL_VERSION
    tool: str = "nlreq.controlled_semantics"
    tool_version: str = CONTROLLED_SEMANTICS_TOOL_VERSION
    claim_classes: list[ControlledClaimClassSemantics]
    constructs: list[ControlledConstructSemantics]
    refusal_rules: list[str] = Field(default_factory=list)


def build_controlled_requirement_semantics_reference() -> ControlledRequirementSemanticsReference:
    return ControlledRequirementSemanticsReference(
        claim_classes=[
            ControlledClaimClassSemantics(
                claim_class="authorization_precondition",
                supported=True,
                canonical_rule="forall scope: premise(actor not_authorized) implies rejects_before(action, state)",
                required_evidence=[
                    EvidenceLevel.CONSISTENCY_CHECKED,
                    EvidenceLevel.STATICALLY_RESOLVED,
                ],
            ),
            ControlledClaimClassSemantics(
                claim_class="state_precondition",
                supported=True,
                canonical_rule="forall scope: premise(actor approved) implies succeeds(action)",
                required_evidence=[EvidenceLevel.CONSISTENCY_CHECKED],
            ),
            ControlledClaimClassSemantics(
                claim_class="state_postcondition",
                supported=True,
                canonical_rule="forall scope: premise(...) implies post_state(state, value)",
                # The post_state obligation is a stateful safety obligation over the system's
                # transition relation, discharged by the bounded S ∧ R ``Next`` check
                # (BOUNDED_CHECKED), not by observing one execution reach the state. Routing it to
                # TRACE_VALIDATED would let a single trace discharge a universally-quantified
                # obligation — see formal_claim._evidence_for_fragment_kind.
                required_evidence=[
                    EvidenceLevel.CONSISTENCY_CHECKED,
                    EvidenceLevel.BOUNDED_CHECKED,
                ],
            ),
            ControlledClaimClassSemantics(
                claim_class="numeric_invariant",
                supported=True,
                canonical_rule="forall scope: premise(...) implies invariant(comparison)",
                # The comparison/membership premises are SMT-checked, but the state_invariant
                # obligation is a bounded S ∧ R check over the system's state (BOUNDED_CHECKED) —
                # the fragment route requires it (formal_claim._evidence_for_fragment_kind), so the
                # claim-class evidence must include it or it understates what closure needs.
                required_evidence=[
                    EvidenceLevel.CONSISTENCY_CHECKED,
                    EvidenceLevel.SMT_CHECKED,
                    EvidenceLevel.BOUNDED_CHECKED,
                ],
            ),
            ControlledClaimClassSemantics(
                claim_class="event_state_correspondence",
                supported=True,
                canonical_rule="forall scope: premise(...) implies within(event, bound)",
                required_evidence=[
                    EvidenceLevel.BOUNDED_CHECKED,
                    EvidenceLevel.TRACE_VALIDATED,
                ],
                limitations=["The bound is checked as bounded evidence, not inductive proof."],
            ),
            ControlledClaimClassSemantics(
                claim_class="bounded_temporal",
                supported=True,
                canonical_rule="forall scope: premise(...) implies within(event, bound)",
                required_evidence=[
                    EvidenceLevel.BOUNDED_CHECKED,
                    EvidenceLevel.TRACE_VALIDATED,
                ],
                limitations=["The bound is explicit and must be carried to backend budgets."],
            ),
            ControlledClaimClassSemantics(
                claim_class="cross_module_causal_obligation",
                supported=True,
                canonical_rule="forall scope: premise(...) implies within(transition(source,target,action), bound)",
                required_evidence=[
                    EvidenceLevel.BOUNDED_CHECKED,
                    EvidenceLevel.TRACE_VALIDATED,
                ],
                limitations=["Cross-module causality requires adapter-neutral trace causality before closure."],
            ),
        ],
        constructs=[
            ControlledConstructSemantics(
                construct_id="scope",
                dsl_fragment="scope NAME",
                formal_role="scope",
                canonical_meaning="Universal quantification over the named operation/entity scope.",
                allowed_claim_classes=[
                    "authorization_precondition",
                    "state_precondition",
                    "state_postcondition",
                    "numeric_invariant",
                    "event_state_correspondence",
                    "bounded_temporal",
                    "cross_module_causal_obligation",
                ],
                refusal_behavior="Malformed or missing scope is refused before formal-claim lowering.",
            ),
            ControlledConstructSemantics(
                construct_id="predicate.authorization",
                dsl_fragment="NAME is authorized | NAME is not authorized",
                formal_role="premise",
                canonical_meaning="Boolean authorization predicate over the named actor or subject.",
                allowed_claim_classes=["authorization_precondition", "bounded_temporal"],
                required_evidence=[EvidenceLevel.CONSISTENCY_CHECKED],
                refusal_behavior="Unsupported authorization polarity is refused with the source span.",
            ),
            ControlledConstructSemantics(
                construct_id="predicate.approval",
                dsl_fragment="NAME is approved | NAME is not approved | NAME is confirmed",
                formal_role="premise",
                canonical_meaning="Boolean workflow-state predicate over the named actor or entity.",
                allowed_claim_classes=[
                    "state_precondition",
                    "state_postcondition",
                    "event_state_correspondence",
                    "numeric_invariant",
                ],
                required_evidence=[EvidenceLevel.CONSISTENCY_CHECKED],
                refusal_behavior="Unknown workflow predicates are refused rather than inferred.",
            ),
            ControlledConstructSemantics(
                construct_id="predicate.comparison",
                dsl_fragment="value COMP value",
                formal_role="premise",
                canonical_meaning="Typed comparison with explicit operator and operands.",
                allowed_claim_classes=["numeric_invariant", "state_precondition"],
                required_evidence=[EvidenceLevel.SMT_CHECKED],
                refusal_behavior="Untyped comparison operands remain review-bound until symbols are resolved.",
            ),
            ControlledConstructSemantics(
                construct_id="obligation.succeed",
                dsl_fragment="NAME must succeed",
                formal_role="obligation",
                canonical_meaning="The named operation reaches the success outcome under the premise.",
                allowed_claim_classes=["state_precondition"],
                required_evidence=[EvidenceLevel.CONSISTENCY_CHECKED],
                refusal_behavior="Success obligations without a named action are refused.",
            ),
            ControlledConstructSemantics(
                construct_id="obligation.reject_before",
                dsl_fragment="NAME must reject before NAME",
                formal_role="obligation",
                canonical_meaning="The named operation rejects before the named state transition.",
                allowed_claim_classes=["authorization_precondition"],
                required_evidence=[EvidenceLevel.CONSISTENCY_CHECKED],
                refusal_behavior="Ordering targets that cannot be represented as state refs are refused.",
            ),
            ControlledConstructSemantics(
                construct_id="obligation.post_state",
                dsl_fragment="state NAME must be value",
                formal_role="obligation",
                canonical_meaning="The named state equals the explicit value after the action.",
                allowed_claim_classes=["state_postcondition"],
                required_evidence=[
                    EvidenceLevel.CONSISTENCY_CHECKED,
                    EvidenceLevel.TRACE_VALIDATED,
                ],
                refusal_behavior="Implicit post-state values are refused.",
            ),
            ControlledConstructSemantics(
                construct_id="obligation.within_event",
                dsl_fragment="emit NAME within NUMBER TIME_UNIT",
                formal_role="obligation",
                canonical_meaning="The named event occurs within the explicit temporal bound.",
                allowed_claim_classes=["event_state_correspondence", "bounded_temporal"],
                required_evidence=[
                    EvidenceLevel.BOUNDED_CHECKED,
                    EvidenceLevel.TRACE_VALIDATED,
                ],
                refusal_behavior="Missing bounds are refused; unsupported units are parser errors.",
            ),
            ControlledConstructSemantics(
                construct_id="obligation.keep_comparison",
                dsl_fragment="keep NAME COMP value",
                formal_role="obligation",
                canonical_meaning="The named value satisfies the comparison invariant.",
                allowed_claim_classes=["numeric_invariant"],
                required_evidence=[EvidenceLevel.SMT_CHECKED],
                refusal_behavior="Invariant targets without explicit comparison operators are refused.",
            ),
            ControlledConstructSemantics(
                construct_id="obligation.cross_module_causal",
                dsl_fragment="module NAME causes module NAME to NAME within NUMBER TIME_UNIT",
                formal_role="obligation",
                canonical_meaning="A source-module event causally precedes a target-module action within the bound.",
                allowed_claim_classes=["cross_module_causal_obligation"],
                required_evidence=[
                    EvidenceLevel.BOUNDED_CHECKED,
                    EvidenceLevel.TRACE_VALIDATED,
                ],
                refusal_behavior="The claim stays needs-review unless causal trace fields are available.",
            ),
        ],
        refusal_rules=[
            "Unsupported grammar is refused before semantic-tree construction.",
            "Unsupported semantic-node kinds are refused before backend projection.",
            "Ambiguous or review-bound constructs cannot be accepted without a hash-bound review artifact.",
            "Bounded temporal semantics must carry explicit bounds and cannot be labeled PROVEN_INDUCTIVE.",
        ],
    )

