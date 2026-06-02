from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .artifact_store import ArtifactRecord
from .end_to_end_gate import EndToEndRequirementGateReport
from .jsonutil import sha256_json


CI_PR_GATE_SCHEMA_VERSION = "0.1"
CI_PR_GATE_TOOL_VERSION = "0.1"


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
