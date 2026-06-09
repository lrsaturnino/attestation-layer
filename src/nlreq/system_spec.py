from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .impact import ImpactAnalysisArtifact


SYSTEM_SPEC_REGISTRY_VERSION = "0.1"
SPEC_TRACE_CONTRACT_SCHEMA_VERSION = "0.1"


class SystemSpecEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    module_ids: list[str] = Field(min_length=1)
    formalism: Literal["tla", "smt", "ltl", "alloy", "lean", "other"]
    path: str
    version: str
    review_status: Literal["draft", "reviewed", "rejected"]
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    recorded_hash: str | None = None
    # Operator metadata the S∧R composition reads from the reviewed spec S. invariants
    # names the spec's safety operators the composed module must preserve; the composition
    # refuses (no vacuous pass) when a relevant spec declares none. init_op/next_op name the
    # spec's own transition operators when S carries its own state machine; the composition
    # consumes them so S's Init/Next are the sole state machine and the requirement narrows S
    # as a state invariant over S's variables — see formal_lowering._compose_system_narrowing.
    init_op: str | None = None
    next_op: str | None = None
    invariants: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_path(self) -> SystemSpecEntry:
        parsed = PurePosixPath(self.path)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("system spec path must be project-root-relative")
        return self


class SystemSpecRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_SPEC_REGISTRY_VERSION
    specs: list[SystemSpecEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> SystemSpecRegistry:
        spec_ids = [spec.spec_id for spec in self.specs]
        if len(spec_ids) != len(set(spec_ids)):
            raise ValueError("system spec ids must be unique")
        return self


class SystemSpecStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    module_ids: list[str]
    path: str
    version: str
    formalism: str
    review_status: str
    freshness: str
    current_hash: str | None = None
    recorded_hash: str | None = None
    status: Literal["fresh", "stale", "missing", "unreviewed"]
    reason: str | None = None


class SystemSpecRegistryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SYSTEM_SPEC_REGISTRY_VERSION
    result: Literal["valid", "needs_review"]
    statuses: list[SystemSpecStatus] = Field(default_factory=list)


def load_system_spec_registry(path: Path) -> SystemSpecRegistry:
    return SystemSpecRegistry.model_validate_json(path.read_text())


def build_system_spec_registry_report(
    registry: SystemSpecRegistry,
    *,
    project_root: Path,
    module_ids: list[str] | None = None,
) -> SystemSpecRegistryReport:
    selected = set(module_ids or [])
    statuses = [
        _status_for_entry(entry, project_root=project_root)
        for entry in registry.specs
        if not selected or selected.intersection(entry.module_ids)
    ]
    result = "valid" if all(status.status == "fresh" for status in statuses) else "needs_review"
    return SystemSpecRegistryReport(result=result, statuses=statuses)


def specs_for_impact(
    registry: SystemSpecRegistry,
    impact: ImpactAnalysisArtifact,
) -> list[SystemSpecEntry]:
    affected = set(impact.affected_modules)
    return [entry for entry in registry.specs if affected.intersection(entry.module_ids)]


def unspecified_modules(registry: SystemSpecRegistry, module_ids: list[str]) -> list[str]:
    """Modules with no system spec entry covering them — genuinely unspec'd (PC-10).

    A module is unspecified when NO registry entry lists it in ``module_ids``: there is no S to
    conjoin, reproduce traces against, or run S ∧ R over. This is deliberately distinct from a
    module whose spec is draft/rejected/stale or whose spec file is missing — those are
    UNREVIEWED/STALE/MISSING coverage failures the coverage report already surfaces. PC-10 returns
    NEEDS_SPEC_COVERAGE and queues a Specula extraction only for modules that have no spec at all,
    so the gate never confuses "no spec exists" with "a spec exists but is not yet usable". Returns
    the unspecified modules sorted.
    """
    covered = {module_id for entry in registry.specs for module_id in entry.module_ids}
    return sorted(set(module_ids) - covered)


def _status_for_entry(entry: SystemSpecEntry, *, project_root: Path) -> SystemSpecStatus:
    path = (project_root / entry.path).resolve(strict=False)
    if not path.is_file():
        return SystemSpecStatus(
            spec_id=entry.spec_id,
            module_ids=entry.module_ids,
            path=entry.path,
            version=entry.version,
            formalism=entry.formalism,
            review_status=entry.review_status,
            freshness=entry.freshness,
            recorded_hash=entry.recorded_hash,
            status="missing",
            reason="spec file is missing",
        )
    current_hash = _sha256_file(path)
    if entry.review_status != "reviewed":
        status = "unreviewed"
        reason = "spec is not reviewed"
    elif entry.freshness != "fresh":
        status = "stale"
        reason = "spec freshness is not fresh"
    elif entry.recorded_hash is not None and entry.recorded_hash != current_hash:
        status = "stale"
        reason = "recorded hash does not match current spec"
    else:
        status = "fresh"
        reason = None
    return SystemSpecStatus(
        spec_id=entry.spec_id,
        module_ids=entry.module_ids,
        path=entry.path,
        version=entry.version,
        formalism=entry.formalism,
        review_status=entry.review_status,
        freshness=entry.freshness,
        current_hash=current_hash,
        recorded_hash=entry.recorded_hash,
        status=status,  # type: ignore[arg-type]
        reason=reason,
    )


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class SpecTraceExpectation(BaseModel):
    """One trace-observable obligation the spec S asserts about the code's behavior (PC-11).

    Each kind is evaluable against a real normalized trace's events:

    - ``event_emitted``: an event whose action matches ``target`` must appear (e.g. ``Redeemed``).
    - ``state_value_reached``: a read call whose action matches ``target`` (e.g. ``total()``) must
      observe the decoded value ``value`` at some point. If the read appears but never returns
      ``value``, the spec is contradicted (a populated delta); if the read never appears, the trace
      cannot witness the obligation (no-coverage).
    - ``action_reverts``: a call whose action matches ``target`` must revert (optionally with revert
      reason ``value``). If it appears but never reverts — or reverts with a different reason — the
      spec is contradicted.
    - ``action_never``: no event whose action matches ``target`` may appear; observing one
      contradicts the spec (a forbidden-action delta).

    ``target`` matches an event action either exactly or as a signature head (``total`` matches
    ``total()``, ``Redeemed`` matches ``Redeemed(uint256)``).
    """

    model_config = ConfigDict(extra="forbid")

    expectation_id: str
    kind: Literal["event_emitted", "state_value_reached", "action_reverts", "action_never"]
    target: str
    value: str | None = None
    description: str = ""


class SpecTraceContract(BaseModel):
    """The trace-observable projection of a registered spec S, for PC-11 code↔spec validation.

    PROVENANCE (read this before trusting the evidence): the expectations are S's declared
    trace-observable obligations, SPECIFIED here for PC-11 (``provenance="declared"`` — curated
    alongside the reviewed spec). Auto-deriving the contract from S itself is Specula's job —
    PC-5 (Solidity) / PC-8 (Go) — and is OUT OF SCOPE here. This module validates only that
    whatever obligations the contract declares are REPRODUCED by the code's real traces: a spec
    that cannot reproduce the code's traces is not a spec of the code. The validator therefore
    tests the declared contract against real traces; it does not assert the contract was machine-
    extracted from S. When PC-5/PC-8 land they set ``provenance="specula_extracted"``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SPEC_TRACE_CONTRACT_SCHEMA_VERSION
    spec_id: str
    module_ids: list[str] = Field(default_factory=list)
    expectations: list[SpecTraceExpectation] = Field(default_factory=list)
    provenance: Literal["declared", "specula_extracted"] = "declared"
