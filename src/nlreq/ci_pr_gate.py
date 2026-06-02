from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .artifact_store import ArtifactRecord
from .end_to_end_gate import (
    EndToEndRequirementGateReport,
    ExtendedEndToEndRequirementGateReport,
)
from .jsonutil import sha256_json


CI_PR_GATE_SCHEMA_VERSION = "0.1"
CI_PR_GATE_TOOL_VERSION = "0.1"
CI_ADOPTION_SCHEMA_VERSION = "0.1"


class CiPrGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CI_PR_GATE_SCHEMA_VERSION
    mode: Literal["report_only", "soft_gate", "hard_gate"]
    result: Literal["passed", "blocked", "reported"]
    requirement_id: str
    decision: Literal["accepted", "refused", "unknown"]
    downstream_action_allowed: bool
    artifact_hashes: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.ci_pr_gate"
    tool_version: str = CI_PR_GATE_TOOL_VERSION


class CiAdoptionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CI_ADOPTION_SCHEMA_VERSION
    policy_id: str = "extended-release-adoption"
    default_mode: Literal["report_only", "soft_gate", "hard_gate"] = "report_only"
    require_stable_json: bool = True
    require_markdown: bool = True
    required_checks: list[str] = Field(
        default_factory=lambda: [
            "extended_gate",
            "stable_json",
            "pr_markdown",
            "machine_result",
        ]
    )
    allow_waivers: bool = True


class ExtendedCiPrGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CI_ADOPTION_SCHEMA_VERSION
    mode: Literal["report_only", "soft_gate", "hard_gate"]
    result: Literal["reported", "passed", "blocked"]
    enforcement: Literal["none", "advisory", "blocking"]
    requirement_id: str
    gate_decision: Literal["accepted", "refused", "unknown"]
    downstream_action_allowed: bool
    stable_json_hash: str
    policy_hash: str
    required_checks: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    blocked_checks: list[str] = Field(default_factory=list)
    waiver_ids: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    pr_markdown: str | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    tool: str = "nlreq.ci_pr_gate"
    tool_version: str = CI_PR_GATE_TOOL_VERSION


def build_ci_pr_gate_report(
    gate: EndToEndRequirementGateReport,
    *,
    mode: Literal["report_only", "soft_gate", "hard_gate"] = "report_only",
    artifact_records: list[ArtifactRecord] | None = None,
) -> CiPrGateReport:
    artifact_records = artifact_records or []
    blocked = mode == "hard_gate" and not gate.downstream_action_allowed
    return CiPrGateReport(
        mode=mode,
        result="reported" if mode == "report_only" else ("blocked" if blocked else "passed"),
        requirement_id=gate.requirement_id,
        decision=gate.decision,
        downstream_action_allowed=gate.downstream_action_allowed,
        artifact_hashes=[record.artifact_hash for record in artifact_records],
        next_actions=[blocker.message for blocker in gate.blockers],
        input_hashes={
            "end_to_end_gate": sha256_json(gate),
            "artifact_records": sha256_json(artifact_records),
        },
    )


def build_ci_adoption_report(
    gate: ExtendedEndToEndRequirementGateReport | EndToEndRequirementGateReport,
    *,
    mode: Literal["report_only", "soft_gate", "hard_gate"] | None = None,
    policy: CiAdoptionPolicy | None = None,
    waiver_ids: list[str] | None = None,
    include_markdown: bool = True,
) -> ExtendedCiPrGateReport:
    policy = policy or CiAdoptionPolicy()
    mode = mode or policy.default_mode
    waiver_ids = waiver_ids or []
    stable_json_hash = sha256_json(gate)
    next_actions = _gate_next_actions(gate)
    missing_checks: list[str] = []
    if policy.require_stable_json and not stable_json_hash:
        missing_checks.append("stable_json")
    if policy.require_markdown and not include_markdown:
        missing_checks.append("pr_markdown")

    blocked_checks: list[str] = []
    if not gate.downstream_action_allowed:
        blocked_checks.append("extended_gate")
    if gate.decision != "accepted":
        blocked_checks.append("machine_result")
    if waiver_ids and not policy.allow_waivers:
        blocked_checks.append("waiver_policy")

    gate_blocked = bool(missing_checks or blocked_checks)
    if mode == "report_only":
        result: Literal["reported", "passed", "blocked"] = "reported"
        enforcement: Literal["none", "advisory", "blocking"] = "none"
    elif mode == "soft_gate":
        result = "blocked" if gate_blocked else "passed"
        enforcement = "advisory"
    else:
        result = "blocked" if gate_blocked else "passed"
        enforcement = "blocking"

    report = ExtendedCiPrGateReport(
        mode=mode,
        result=result,
        enforcement=enforcement,
        requirement_id=gate.requirement_id,
        gate_decision=gate.decision,
        downstream_action_allowed=gate.downstream_action_allowed,
        stable_json_hash=stable_json_hash,
        policy_hash=sha256_json(policy),
        required_checks=policy.required_checks,
        missing_checks=missing_checks,
        blocked_checks=sorted(set(blocked_checks)),
        waiver_ids=waiver_ids,
        next_actions=next_actions,
        input_hashes={
            "gate": stable_json_hash,
            "policy": sha256_json(policy),
            "waivers": sha256_json(waiver_ids),
        },
    )
    if include_markdown:
        report = report.model_copy(update={"pr_markdown": extended_ci_pr_gate_markdown(report)})
    return report


def ci_pr_gate_markdown(report: CiPrGateReport) -> str:
    lines = [
        "# NLReq PR Gate",
        "",
        f"Mode: `{report.mode}`",
        f"Result: `{report.result}`",
        f"Requirement: `{report.requirement_id}`",
        f"Decision: `{report.decision}`",
        f"Downstream action allowed: `{str(report.downstream_action_allowed).lower()}`",
        "",
        "## Artifacts",
        "",
    ]
    if report.artifact_hashes:
        lines.extend(f"- `{artifact_hash}`" for artifact_hash in report.artifact_hashes)
    else:
        lines.append("No retained artifacts were supplied.")
    lines.extend(["", "## Next Actions", ""])
    if report.next_actions:
        lines.extend(f"- {action}" for action in report.next_actions)
    else:
        lines.append("No next actions.")
    return "\n".join(lines) + "\n"


def extended_ci_pr_gate_markdown(report: ExtendedCiPrGateReport) -> str:
    lines = [
        "# NLReq Extended PR Gate",
        "",
        f"Mode: `{report.mode}`",
        f"Result: `{report.result}`",
        f"Enforcement: `{report.enforcement}`",
        f"Requirement: `{report.requirement_id}`",
        f"Gate decision: `{report.gate_decision}`",
        f"Downstream action allowed: `{str(report.downstream_action_allowed).lower()}`",
        f"Stable JSON hash: `{report.stable_json_hash}`",
        "",
        "## Blocked Checks",
        "",
    ]
    if report.blocked_checks:
        lines.extend(f"- `{check}`" for check in report.blocked_checks)
    else:
        lines.append("No blocked checks.")
    lines.extend(["", "## Next Actions", ""])
    if report.next_actions:
        lines.extend(f"- {action}" for action in report.next_actions)
    else:
        lines.append("No next actions.")
    return "\n".join(lines) + "\n"


def _gate_next_actions(
    gate: ExtendedEndToEndRequirementGateReport | EndToEndRequirementGateReport,
) -> list[str]:
    if isinstance(gate, ExtendedEndToEndRequirementGateReport):
        return gate.refusal_summary
    return [blocker.message for blocker in gate.blockers]
