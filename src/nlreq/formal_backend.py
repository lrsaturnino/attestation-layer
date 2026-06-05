from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_json, sha256_text
from .model_checker_runner import (
    DEFAULT_OUTPUT_LIMIT_BYTES,
    ModelCheckerBudget,
    ModelCheckerCommand,
    run_model_checker,
)
from .models import (
    BackendResult,
    EvidenceLevel,
    RequirementIRV2,
    SemanticNode,
    bounded_evidence_backing_complete,
)
from .translator import LoweredFormalArtifact, lower_ir_v2_to_tla


FORMAL_BACKEND_SCHEMA_VERSION = "0.1"


FormalBackendTarget = Literal["tla", "smt", "ltl", "alloy", "lean"]


class FormalBackendBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, gt=0)
    max_states: int | None = Field(default=None, gt=0)
    max_depth: int | None = Field(default=None, gt=0)
    memory_budget_mb: int | None = Field(default=None, gt=0)
    solver_options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class FormalBackendExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checker_id: str = "tlc"
    command: list[str] | None = None
    artifact_dir: str | None = None
    expected_exit_code: int = 0
    tool_version: str | None = None
    tool_version_command: list[str] | None = None
    output_limit_bytes: int = Field(default=DEFAULT_OUTPUT_LIMIT_BYTES, gt=0, le=20000)


class UnsupportedConstruct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: str
    reason: str


class ConsumedAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    namespace: str
    schema_version: str
    keys: list[str] = Field(default_factory=list)


class FormalBackendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_BACKEND_SCHEMA_VERSION
    backend_id: str
    target: FormalBackendTarget
    requirement: RequirementIRV2
    entry_node_id: str = "rule.root"
    budget: FormalBackendBudget | None = None
    execution: FormalBackendExecution | None = None


class FormalBackendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FORMAL_BACKEND_SCHEMA_VERSION
    backend_id: str
    target: FormalBackendTarget
    result: BackendResult
    unsupported_constructs: list[UnsupportedConstruct] = Field(default_factory=list)
    consumed_annotations: list[ConsumedAnnotation] = Field(default_factory=list)
    lowered_artifact_hash: str | None = None


class FormalBackend(Protocol):
    backend_id: str
    target: FormalBackendTarget

    def check(self, request: FormalBackendRequest) -> FormalBackendResponse:
        ...


class TlaBoundaryBackend:
    backend_id = "tla-boundary"
    target: FormalBackendTarget = "tla"
    annotation_namespace = "tla"
    supported_node_kinds = {
        "rule",
        "forall",
        "and",
        "predicate",
        "action_obligation",
        "action",
        "before",
        "transition",
        "state_ref",
        "invariant",
        "state_delta",
        "event",
    }

    def check(self, request: FormalBackendRequest) -> FormalBackendResponse:
        if request.backend_id != self.backend_id:
            raise ValueError(
                f"backend_id mismatch: request {request.backend_id}, backend {self.backend_id}"
            )
        if request.target != self.target:
            raise ValueError(f"target mismatch: request {request.target}, backend {self.target}")

        unsupported: list[UnsupportedConstruct] = []
        consumed: list[ConsumedAnnotation] = []
        for node in _walk_nodes(request.requirement.semantic_ir):
            if node.kind not in self.supported_node_kinds:
                unsupported.append(
                    UnsupportedConstruct(
                        node_id=node.node_id,
                        kind=node.kind,
                        reason=f"node kind is not supported by backend {self.backend_id}",
                    )
                )
            annotation = node.annotations.get(self.annotation_namespace)
            if annotation is not None:
                schema_version = annotation.get("schema_version")
                if not isinstance(schema_version, str) or not schema_version:
                    unsupported.append(
                        UnsupportedConstruct(
                            node_id=node.node_id,
                            kind=node.kind,
                            reason=(
                                f"{self.annotation_namespace} annotation requires schema_version"
                            ),
                        )
                    )
                else:
                    consumed.append(
                        ConsumedAnnotation(
                            node_id=node.node_id,
                            namespace=self.annotation_namespace,
                            schema_version=schema_version,
                            keys=sorted(annotation),
                        )
                    )

        status = "unsupported" if unsupported else "needs_review"
        details = {
            "entry_node_id": request.entry_node_id,
            "checked_node_count": len(list(_walk_nodes(request.requirement.semantic_ir))),
            "boundary": "lowering_shape_only",
            "execution": "not_run",
        }
        if unsupported:
            details["unsupported_constructs"] = [
                item.model_dump(mode="json", exclude_none=True) for item in unsupported
            ]

        return FormalBackendResponse(
            backend_id=self.backend_id,
            target=self.target,
            result=BackendResult(
                backend=self.backend_id,
                status=status,
                evidence_level=None,
                details=details,
            ),
            unsupported_constructs=unsupported,
            consumed_annotations=consumed,
        )


class TlaRunnerBackend:
    backend_id = "tla-runner"
    target: FormalBackendTarget = "tla"

    def check(self, request: FormalBackendRequest) -> FormalBackendResponse:
        if request.backend_id != self.backend_id:
            raise ValueError(
                f"backend_id mismatch: request {request.backend_id}, backend {self.backend_id}"
            )
        if request.target != self.target:
            raise ValueError(f"target mismatch: request {request.target}, backend {self.target}")

        lowered = lower_ir_v2_to_tla(request.requirement)
        if lowered.status != "lowered" or lowered.content is None:
            unsupported = [
                UnsupportedConstruct(
                    node_id=diagnostic.node_id,
                    kind=diagnostic.kind,
                    reason=diagnostic.reason,
                )
                for diagnostic in lowered.diagnostics
            ]
            return FormalBackendResponse(
                backend_id=self.backend_id,
                target=self.target,
                result=BackendResult(
                    backend=self.backend_id,
                    status="unsupported",
                    evidence_level=None,
                    details={
                        "entry_node_id": request.entry_node_id,
                        "execution": "not_run",
                        "reason": "TLA lowering refused the requirement fragment",
                        "diagnostics": [
                            item.model_dump(mode="json", exclude_none=True)
                            for item in lowered.diagnostics
                        ],
                    },
                ),
                unsupported_constructs=unsupported,
                lowered_artifact_hash=sha256_json(lowered),
            )

        execution = request.execution or FormalBackendExecution()
        artifact_dir = _tla_artifact_dir(request, execution)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        module_name = _tla_module_name(lowered)
        module_path = artifact_dir / f"{module_name}.tla"
        config_path = artifact_dir / f"{module_name}.cfg"
        config_content = _tla_config_content()
        module_path.write_text(lowered.content)
        config_path.write_text(config_content)

        command = _tla_checker_command(execution, module_path, config_path, module_name)
        runner_result = run_model_checker(
            ModelCheckerCommand(
                run_id=f"{request.requirement.requirement_id}:tla",
                checker_id=execution.checker_id,
                command=command,
                cwd=artifact_dir.as_posix(),
                budget=_runner_budget(request.budget),
                expected_exit_code=execution.expected_exit_code,
                tool_version=execution.tool_version,
                tool_version_command=execution.tool_version_command,
                output_limit_bytes=execution.output_limit_bytes,
            )
        )
        status = _backend_status_for_runner_outcome(runner_result.outcome)
        details = {
            "entry_node_id": request.entry_node_id,
            "execution": "run",
            "checker_id": execution.checker_id,
            "runner_outcome": runner_result.outcome,
            "runner_result_hash": sha256_json(runner_result),
            # Surface the run-recorded version (null for a stub) so a BOUNDED_CHECKED
            # result fed into proof closure carries its real backing (see ProductionTla).
            "tool_version": runner_result.reproducibility.tool_version,
            "artifact_dir": artifact_dir.as_posix(),
            "module": module_path.name,
            "module_hash": _sha256_file(module_path),
            "config": config_path.name,
            "config_hash": _sha256_file(config_path),
            "bounds": _budget_details(request.budget),
            "command": command,
            "stdout": runner_result.stdout.model_dump(mode="json"),
            "stderr": runner_result.stderr.model_dump(mode="json"),
            "counterexamples": [
                item.model_dump(mode="json", exclude_none=True)
                for item in runner_result.counterexamples
            ],
            "unsupported_markers": runner_result.unsupported_markers,
            "tool_error": runner_result.tool_error,
        }
        return FormalBackendResponse(
            backend_id=self.backend_id,
            target=self.target,
            result=BackendResult(
                backend=self.backend_id,
                status=status,
                evidence_level=_bounded_evidence_level(status, details),
                details=details,
            ),
            lowered_artifact_hash=sha256_json(lowered),
        )


class ProductionTlaBackend:
    backend_id = "production-tla"
    checker_id = "production-tla"
    evidence_flavor = "bounded_tla"
    target: FormalBackendTarget = "tla"

    def default_command(self, budget: FormalBackendBudget | None) -> list[str]:
        raise NotImplementedError

    def default_version_command(self) -> list[str] | None:
        """Command that prints the backend's version, recorded with every run.

        Returns None when no verified version command is pinned for the backend; the runner
        then records whatever ``tool_version`` the caller supplied (or no version). Subclasses
        override with a pinned command (see docs/formal-backend-guide.md).
        """
        return None

    def check(self, request: FormalBackendRequest) -> FormalBackendResponse:
        if request.backend_id != self.backend_id:
            raise ValueError(
                f"backend_id mismatch: request {request.backend_id}, backend {self.backend_id}"
            )
        if request.target != self.target:
            raise ValueError(f"target mismatch: request {request.target}, backend {self.target}")

        lowered = lower_ir_v2_to_tla(request.requirement)
        if lowered.status != "lowered" or lowered.content is None:
            unsupported = [
                UnsupportedConstruct(
                    node_id=diagnostic.node_id,
                    kind=diagnostic.kind,
                    reason=diagnostic.reason,
                )
                for diagnostic in lowered.diagnostics
            ]
            return FormalBackendResponse(
                backend_id=self.backend_id,
                target=self.target,
                result=BackendResult(
                    backend=self.backend_id,
                    status="unsupported",
                    evidence_level=None,
                    details={
                        "entry_node_id": request.entry_node_id,
                        "execution": "not_run",
                        "reason": "TLA projection refused the requirement fragment",
                        "diagnostics": [
                            item.model_dump(mode="json", exclude_none=True)
                            for item in lowered.diagnostics
                        ],
                    },
                ),
                unsupported_constructs=unsupported,
                lowered_artifact_hash=sha256_json(lowered),
            )

        execution = request.execution or FormalBackendExecution(checker_id=self.checker_id)
        artifact_dir = _production_tla_artifact_dir(request, execution, self.backend_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        module_name = _tla_module_name(lowered)
        module_path = artifact_dir / f"{module_name}.tla"
        config_path = artifact_dir / f"{module_name}.cfg"
        module_path.write_text(lowered.content)
        config_path.write_text(_tla_config_content())

        command = _production_tla_command(
            execution.command or self.default_command(request.budget),
            module_path=module_path,
            config_path=config_path,
            module_name=module_name,
            budget=request.budget,
        )
        runner_result = run_model_checker(
            ModelCheckerCommand(
                run_id=f"{request.requirement.requirement_id}:{self.backend_id}",
                checker_id=execution.checker_id,
                command=command,
                cwd=artifact_dir.as_posix(),
                budget=_runner_budget(request.budget),
                expected_exit_code=execution.expected_exit_code,
                tool_version=execution.tool_version,
                tool_version_command=(
                    execution.tool_version_command or self.default_version_command()
                ),
                output_limit_bytes=execution.output_limit_bytes,
            )
        )
        status = _production_backend_status_for_runner(runner_result)
        details = {
            "entry_node_id": request.entry_node_id,
            "execution": "run",
            "checker_id": execution.checker_id,
            "evidence_flavor": self.evidence_flavor,
            "runner_outcome": runner_result.outcome,
            "runner_result_hash": sha256_json(runner_result),
            # Surface the version the run recorded (null for a stub/absent binary) so a
            # BOUNDED_CHECKED result fed into proof closure carries its real backing — the
            # closure gate requires a run-recorded version, not the producer's static one.
            "tool_version": runner_result.reproducibility.tool_version,
            "tool_missing": (
                runner_result.outcome == "tool_error"
                and runner_result.reproducibility.executable_resolved is None
            ),
            "artifact_dir": artifact_dir.as_posix(),
            "module": module_path.name,
            "module_hash": _sha256_file(module_path),
            "config": config_path.name,
            "config_hash": _sha256_file(config_path),
            "bounds": _budget_details(request.budget),
            "command": command,
            "stdout": runner_result.stdout.model_dump(mode="json"),
            "stderr": runner_result.stderr.model_dump(mode="json"),
            "counterexamples": [
                item.model_dump(mode="json", exclude_none=True)
                for item in runner_result.counterexamples
            ],
            "unsupported_markers": runner_result.unsupported_markers,
            "tool_error": runner_result.tool_error,
        }
        return FormalBackendResponse(
            backend_id=self.backend_id,
            target=self.target,
            result=BackendResult(
                backend=self.backend_id,
                status=status,
                evidence_level=_bounded_evidence_level(status, details),
                details=details,
            ),
            lowered_artifact_hash=sha256_json(lowered),
        )


class ApalacheBackend(ProductionTlaBackend):
    backend_id = "apalache"
    checker_id = "apalache"
    evidence_flavor = "symbolic_bounded"

    def default_command(self, budget: FormalBackendBudget | None) -> list[str]:
        depth = (budget.max_depth if budget is not None and budget.max_depth else 10)
        return ["apalache-mc", "check", f"--length={depth}", "{module}"]

    def default_version_command(self) -> list[str] | None:
        # `apalache-mc version` prints the pinned version (see docs/formal-backend-guide.md);
        # the runner records it in the run's reproducibility metadata.
        return ["apalache-mc", "version"]


class TlcProductionBackend(ProductionTlaBackend):
    backend_id = "tlc"
    checker_id = "tlc"
    evidence_flavor = "explicit_state_bounded"

    # TLC is a Java class in tla2tools.jar, not a standalone launcher like apalache-mc, so both
    # the check and the version probe invoke it through `java -cp tla2tools.jar tlc2.TLC` — the
    # exact form pinned in docs/formal-backend-guide.md. Sharing the `java` launcher across both
    # commands keeps the version probe attributable to the run under the runner's same-executable
    # provenance guard (a `tlc2.TLC` run with a `java …` probe would be suppressed as a different
    # binary). The relative `tla2tools.jar` resolves from the run's cwd, mirroring the guide.
    def default_command(self, budget: FormalBackendBudget | None) -> list[str]:
        return ["java", "-cp", "tla2tools.jar", "tlc2.TLC", "-config", "{config}", "{module}"]

    def default_version_command(self) -> list[str] | None:
        # `java -cp tla2tools.jar tlc2.TLC` (no model) prints the pinned TLC version banner; the
        # runner records it in the run's reproducibility metadata (PB-3). Symmetric with Apalache.
        return ["java", "-cp", "tla2tools.jar", "tlc2.TLC"]


def formal_backend_for_id(backend_id: str) -> FormalBackend:
    if backend_id == TlaBoundaryBackend.backend_id:
        return TlaBoundaryBackend()
    if backend_id == TlaRunnerBackend.backend_id:
        return TlaRunnerBackend()
    if backend_id == ApalacheBackend.backend_id:
        return ApalacheBackend()
    if backend_id == TlcProductionBackend.backend_id:
        return TlcProductionBackend()
    raise ValueError(f"unknown formal backend: {backend_id}")


def build_formal_backend_request(
    requirement: RequirementIRV2,
    *,
    backend_id: str,
    budget: FormalBackendBudget | None = None,
    execution: FormalBackendExecution | None = None,
) -> FormalBackendRequest:
    backend = formal_backend_for_id(backend_id)
    return FormalBackendRequest(
        backend_id=backend.backend_id,
        target=backend.target,
        requirement=requirement,
        budget=budget,
        execution=execution,
    )


def check_formal_backend(request: FormalBackendRequest) -> FormalBackendResponse:
    return formal_backend_for_id(request.backend_id).check(request)


def existing_formal_boundaries() -> list[dict[str, str]]:
    return [
        {
            "backend_id": "core_smt",
            "target": "smt",
            "scope": "flat ir_version 0.1 self-consistency and supported claim shape",
        },
        {
            "backend_id": "tla",
            "target": "tla",
            "scope": "reviewed TLA+ model/config execution, not compositional IR lowering",
        },
        {
            "backend_id": TlaBoundaryBackend.backend_id,
            "target": TlaBoundaryBackend.target,
            "scope": "compositional IR lowering boundary shape check",
        },
        {
            "backend_id": TlaRunnerBackend.backend_id,
            "target": TlaRunnerBackend.target,
            "scope": "runnable TLA+ MVP lowering and local model-checker execution",
        },
        {
            "backend_id": ApalacheBackend.backend_id,
            "target": ApalacheBackend.target,
            "scope": "production symbolic bounded checking through Apalache command execution",
        },
        {
            "backend_id": TlcProductionBackend.backend_id,
            "target": TlcProductionBackend.target,
            "scope": "production explicit-state checking through TLC command execution",
        },
    ]


def _tla_artifact_dir(request: FormalBackendRequest, execution: FormalBackendExecution) -> Path:
    if execution.artifact_dir is not None:
        return Path(execution.artifact_dir).resolve(strict=False)
    return (
        Path.cwd()
        / ".nlreq-formal-artifacts"
        / request.requirement.requirement_id
        / TlaRunnerBackend.backend_id
    ).resolve(strict=False)


def _tla_module_name(lowered: LoweredFormalArtifact) -> str:
    if lowered.content is None:
        raise ValueError("lowered TLA artifact has no content")
    first_line = lowered.content.splitlines()[0]
    prefix = "---- MODULE "
    suffix = " ----"
    if first_line.startswith(prefix) and first_line.endswith(suffix):
        return first_line[len(prefix) : -len(suffix)]
    return "Requirement"


def _tla_config_content() -> str:
    # INVARIANT checks RequirementHolds at every reachable state.
    # PROPERTY on a bare boolean formula only checks the initial state in TLC,
    # which is trivially true (NLRState = "idle") and vacuous.
    return "INIT Init\nNEXT Next\nINVARIANT RequirementHolds\n"


def _tla_checker_command(
    execution: FormalBackendExecution,
    module_path: Path,
    config_path: Path,
    module_name: str,
) -> list[str]:
    command = execution.command or ["tlc2.TLC", "-config", config_path.name, module_path.name]
    replacements = {
        "{module}": module_path.name,
        "{config}": config_path.name,
        "{module_name}": module_name,
    }
    rendered: list[str] = []
    for part in command:
        value = part
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        rendered.append(value)
    return rendered


def _runner_budget(budget: FormalBackendBudget | None) -> ModelCheckerBudget:
    if budget is None:
        return ModelCheckerBudget(timeout_seconds=120)
    return ModelCheckerBudget(
        timeout_seconds=budget.timeout_seconds or 120,
        max_depth=budget.max_depth,
        max_states=budget.max_states,
        memory_budget_mb=budget.memory_budget_mb,
        solver_options=budget.solver_options,
    )


def _budget_details(budget: FormalBackendBudget | None) -> dict[str, Any]:
    return _runner_budget(budget).model_dump(mode="json", exclude_none=True)


def _backend_status_for_runner_outcome(outcome: str) -> str:
    if outcome == "tool_error":
        return "invalid"
    return outcome


def _production_backend_status_for_runner(runner_result) -> str:
    if (
        runner_result.outcome == "tool_error"
        and runner_result.reproducibility.executable_resolved is None
    ):
        return "unsupported"
    if runner_result.outcome == "tool_error":
        return "invalid"
    return runner_result.outcome


def _bounded_evidence_level(status: str, details: dict[str, Any]) -> EvidenceLevel | None:
    """The honest evidence level for a model-checker run.

    A bounded model check is BOUNDED_CHECKED only when it completed — ``valid`` (no violation
    within bounds) or ``counterexample`` (a violation found within bounds) — AND recorded its
    full backing: the bounds searched, the checker command, and the version of the checker the
    run resolved (see ``models.bounded_evidence_backing_complete``). A timeout, a tool error, or
    a stub run that resolved no version produced no backed bounded evidence, so the level
    self-gates to None rather than emit an unbacked BOUNDED_CHECKED claim into proof closure."""
    if status in {"valid", "counterexample"} and bounded_evidence_backing_complete(details):
        return EvidenceLevel.BOUNDED_CHECKED
    return None


def _production_tla_artifact_dir(
    request: FormalBackendRequest,
    execution: FormalBackendExecution,
    backend_id: str,
) -> Path:
    if execution.artifact_dir is not None:
        return Path(execution.artifact_dir).resolve(strict=False)
    return (
        Path.cwd()
        / ".nlreq-formal-artifacts"
        / request.requirement.requirement_id
        / backend_id
    ).resolve(strict=False)


def _production_tla_command(
    command: list[str],
    *,
    module_path: Path,
    config_path: Path,
    module_name: str,
    budget: FormalBackendBudget | None,
) -> list[str]:
    replacements = {
        "{module}": module_path.name,
        "{config}": config_path.name,
        "{module_name}": module_name,
        "{max_depth}": str(budget.max_depth if budget and budget.max_depth else 10),
        "{max_states}": str(budget.max_states if budget and budget.max_states else ""),
    }
    rendered: list[str] = []
    for part in command:
        value = part
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        if value:
            rendered.append(value)
    return rendered


def _sha256_file(path: Path) -> str:
    return sha256_text(path.read_text())


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
