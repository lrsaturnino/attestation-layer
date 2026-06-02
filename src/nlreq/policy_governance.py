from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .gate import GatePolicy, GateWaiver


POLICY_GOVERNANCE_SCHEMA_VERSION = "0.1"
POLICY_GOVERNANCE_TOOL_VERSION = "0.1"


class WaiverAuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waiver_id: str
    status: Literal["active", "expired", "unsafe", "out_of_policy"]
    blocking: bool
    reason: str


class WaiverAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = POLICY_GOVERNANCE_SCHEMA_VERSION
    policy_id: str
    result: Literal["passed", "blocked"]
    findings: list[WaiverAuditFinding] = Field(default_factory=list)
    tool: str = "nlreq.policy_governance"
    tool_version: str = POLICY_GOVERNANCE_TOOL_VERSION


def build_waiver_audit_report(
    *,
    policy: GatePolicy,
    waivers: list[GateWaiver],
    now: datetime | None = None,
) -> WaiverAuditReport:
    active_now = now or datetime.now(timezone.utc)
    findings: list[WaiverAuditFinding] = []
    for waiver in waivers:
        if waiver.expires_at <= active_now:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="expired",
                    blocking=True,
                    reason="waiver is expired",
                )
            )
        elif not policy.waivers.allow_waivers:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="out_of_policy",
                    blocking=True,
                    reason="policy does not allow waivers",
                )
            )
        elif (
            policy.waivers.max_duration_days is not None
            and waiver.expires_at > active_now + timedelta(days=policy.waivers.max_duration_days)
        ):
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="out_of_policy",
                    blocking=True,
                    reason="waiver expiration exceeds policy maximum duration",
                )
            )
        elif policy.waivers.require_reviewed_hashes and not waiver.reviewed_hashes:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="out_of_policy",
                    blocking=True,
                    reason="policy requires reviewed hashes for waivers",
                )
            )
        elif not waiver.may_satisfy_hard_gate:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="unsafe",
                    blocking=True,
                    reason="waiver may not satisfy hard gate",
                )
            )
        else:
            findings.append(
                WaiverAuditFinding(
                    waiver_id=waiver.waiver_id,
                    status="active",
                    blocking=False,
                    reason="waiver is active and policy allows waivers",
                )
            )
    return WaiverAuditReport(
        policy_id=policy.policy_id,
        result="blocked" if any(finding.blocking for finding in findings) else "passed",
        findings=findings,
    )
