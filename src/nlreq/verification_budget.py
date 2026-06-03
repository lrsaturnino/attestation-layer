from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json
from .models import BackendResult, RequirementIRV2


VERIFICATION_BUDGET_SCHEMA_VERSION = "0.1"


class AbstractionAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption_id: str
    statement: str
    scope: str
    reviewed: bool = False


class RequirementClassBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_class: Literal["safety", "liveness", "trace_grounded", "system_compatibility"]
    timeout_seconds: int = Field(gt=0)
    max_depth: int | None = Field(default=None, gt=0)
    max_states: int | None = Field(default=None, gt=0)
    finite_domains: dict[str, int] = Field(default_factory=dict)
    abstraction_level: Literal["none", "local", "compositional", "abstract"] = "local"


class VerificationBudgetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = VERIFICATION_BUDGET_SCHEMA_VERSION
    budgets: list[RequirementClassBudget] = Field(default_factory=list)


class VerificationBudgetReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = VERIFICATION_BUDGET_SCHEMA_VERSION
    requirement_id: str
    requirement_class: str
    budget: RequirementClassBudget
    assumptions: list[AbstractionAssumption] = Field(default_factory=list)
    assumptions_hash: str | None = None
    result: Literal["ready", "needs_review"]
    blockers: list[str] = Field(default_factory=list)


class BudgetedVerificationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = VERIFICATION_BUDGET_SCHEMA_VERSION
    requirement_id: str
    outcome: Literal["valid", "counterexample", "timeout", "unknown", "inconclusive"]
    budget_hash: str
    backend_status: str
    approving: bool
    closure_effect: Literal["allow", "block", "review"] = "block"
    unknown_policy: str = "Timeout, invalid, unsupported, and review-bound outcomes cannot approve closure."
    reason: str | None = None


def default_verification_budget_policy() -> VerificationBudgetPolicy:
    return VerificationBudgetPolicy(
        budgets=[
            RequirementClassBudget(
                requirement_class="safety",
                timeout_seconds=120,
                max_depth=20,
                max_states=10000,
                finite_domains={"actors": 3, "resources": 3},
            ),
            RequirementClassBudget(
                requirement_class="liveness",
                timeout_seconds=180,
                max_depth=30,
                max_states=20000,
                finite_domains={"steps": 30},
                abstraction_level="compositional",
            ),
            RequirementClassBudget(
                requirement_class="trace_grounded",
                timeout_seconds=60,
                max_depth=10,
                finite_domains={"traces": 10},
            ),
            RequirementClassBudget(
                requirement_class="system_compatibility",
                timeout_seconds=180,
                max_depth=25,
                max_states=50000,
                finite_domains={"modules": 10},
                abstraction_level="compositional",
            ),
        ]
    )


def build_verification_budget_report(
    requirement: RequirementIRV2,
    *,
    requirement_class: str,
    policy: VerificationBudgetPolicy | None = None,
    assumptions: list[AbstractionAssumption] | None = None,
) -> VerificationBudgetReport:
    active_policy = policy or default_verification_budget_policy()
    budget = _budget_for_class(active_policy, requirement_class)
    assumption_list = assumptions or []
    blockers = [
        f"assumption {assumption.assumption_id} requires review"
        for assumption in assumption_list
        if not assumption.reviewed
    ]
    return VerificationBudgetReport(
        requirement_id=requirement.requirement_id,
        requirement_class=requirement_class,
        budget=budget,
        assumptions=assumption_list,
        assumptions_hash=sha256_json(assumption_list) if assumption_list else None,
        result="needs_review" if blockers else "ready",
        blockers=blockers,
    )


def classify_budgeted_outcome(
    *,
    requirement_id: str,
    budget_report: VerificationBudgetReport,
    backend_result: BackendResult,
) -> BudgetedVerificationOutcome:
    if backend_result.status == "valid" and budget_report.result == "ready":
        outcome = "valid"
        approving = True
        closure_effect = "allow"
        reason = None
    elif backend_result.status == "counterexample":
        outcome = "counterexample"
        approving = False
        closure_effect = "block"
        reason = "backend produced a counterexample"
    elif backend_result.status == "timeout":
        outcome = "timeout"
        approving = False
        closure_effect = "block"
        reason = "verification budget was exhausted"
    elif backend_result.status in {"unsupported", "needs_review"} or budget_report.result != "ready":
        outcome = "inconclusive"
        approving = False
        closure_effect = "review"
        reason = "verification is inconclusive under current budget or assumptions"
    else:
        outcome = "unknown"
        approving = False
        closure_effect = "block"
        reason = "backend status is unknown for budget classification"
    return BudgetedVerificationOutcome(
        requirement_id=requirement_id,
        outcome=outcome,
        budget_hash=sha256_json(budget_report),
        backend_status=backend_result.status,
        approving=approving,
        closure_effect=closure_effect,
        reason=reason,
    )


def _budget_for_class(
    policy: VerificationBudgetPolicy, requirement_class: str
) -> RequirementClassBudget:
    for budget in policy.budgets:
        if budget.requirement_class == requirement_class:
            return budget
    raise ValueError(f"unknown requirement class: {requirement_class}")
