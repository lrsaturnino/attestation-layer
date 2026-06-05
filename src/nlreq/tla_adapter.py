from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adapter import Adapter, default_generic_adapter
from .jsonutil import sha256_json
from .models import (
    BackendResult,
    EvidenceCapability,
    EvidenceLevel,
    RequirementIR,
    Symbol,
    SymbolBinding,
    SymbolRef,
    SymbolResolution,
    ValidationResult,
    VerificationTask,
)


TLA_SCHEMA_VERSION = "0.1"
DEFAULT_TLA_TIMEOUT_SECONDS = 120
DEFAULT_OUTPUT_LIMIT_BYTES = 4000


class TlaModelCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    requirement_ids: list[str] = Field(min_length=1)
    module: str
    config: str
    checker: Literal["tlc", "apalache", "custom"] = "tlc"
    command: list[str] = Field(min_length=1)
    properties: list[str] = Field(min_length=1)
    bounds: dict[str, int | str] = Field(default_factory=dict)
    constants: dict[str, int | str | bool] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=DEFAULT_TLA_TIMEOUT_SECONDS, gt=0)
    requested_evidence: EvidenceLevel = EvidenceLevel.BOUNDED_CHECKED
    expected_exit_code: int = 0
    output_limit_bytes: int = Field(default=DEFAULT_OUTPUT_LIMIT_BYTES, gt=0, le=20000)

    @model_validator(mode="after")
    def validate_model(self) -> TlaModelCheck:
        if self.requested_evidence != EvidenceLevel.BOUNDED_CHECKED:
            raise ValueError("TLA checks may only request BOUNDED_CHECKED evidence")
        if not self.bounds:
            raise ValueError(
                "a BOUNDED_CHECKED TLA check must declare the bounds it searches; an empty bounds "
                "emits a bounded-evidence claim with no backing"
            )
        if any(not part for part in self.command):
            raise ValueError("model checker command argv entries must be non-empty strings")
        _validate_relative_path(self.module, field="module")
        _validate_relative_path(self.config, field="config")
        return self


class TlaModelConfigArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TLA_SCHEMA_VERSION
    adapter: Literal["tla"] = "tla"
    models: list[TlaModelCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_models(self) -> TlaModelConfigArtifact:
        model_ids = [model.model_id for model in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("TLA model ids must be unique")
        return self


class TlaResultsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TLA_SCHEMA_VERSION
    adapter: Literal["tla"] = "tla"
    results: list[BackendResult] = Field(default_factory=list)


def load_tla_model_config(path: Path) -> TlaModelConfigArtifact:
    return TlaModelConfigArtifact.model_validate_json(path.read_text())


class TlaAdapter(Adapter):
    adapter_id = "tla"
    target_kind = "tla_model"

    def __init__(self, config: TlaModelConfigArtifact, *, project_root: Path | None = None) -> None:
        self.config = config
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._symbol_adapter = default_generic_adapter()

    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        return self._symbol_adapter.resolve_symbols(refs)

    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        if binding.adapter != self.adapter_id:
            return ValidationResult(
                valid=False,
                reason=f"binding adapter mismatch: expected {self.adapter_id}, found {binding.adapter}",
            )
        generic_binding = binding.model_copy(update={"adapter": self._symbol_adapter.adapter_id})
        return self._symbol_adapter.validate_binding(generic_binding)

    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        if not symbols:
            return []
        return [
            EvidenceCapability(
                evidence_level=EvidenceLevel.BOUNDED_CHECKED,
                description="Reviewed TLA+ model/config can be checked by a bounded model checker.",
            )
        ]

    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        tasks: list[VerificationTask] = []
        for model in self.models_for_requirement(ir.requirement_id):
            payload = self._payload_for_model(model, ir.requirement_id)
            tasks.append(
                VerificationTask(
                    id=model.model_id,
                    backend="adapter",
                    description=f"Run TLA model check {model.model_id} for {ir.requirement_id}.",
                    input_hash=sha256_json(payload),
                    payload=payload,
                )
            )
        return tasks

    def collect_evidence(self, task_results: list[object]) -> list[BackendResult]:
        collected: list[BackendResult] = []
        for result in task_results:
            if isinstance(result, BackendResult):
                collected.append(result)
                continue
            if isinstance(result, dict):
                collected.append(BackendResult.model_validate(result))
                continue
            raise TypeError(f"unsupported TLA adapter task result: {type(result).__name__}")
        return collected

    def run_task(self, task: VerificationTask) -> BackendResult:
        if task.payload.get("task") != "tla_model_check":
            return BackendResult(
                backend=self.adapter_id,
                status="unsupported",
                details={"task_id": task.id, "task": task.payload.get("task")},
            )
        missing_paths = task.payload.get("missing_model_paths", [])
        if missing_paths:
            return BackendResult(
                backend=self.adapter_id,
                status="invalid",
                evidence_level=EvidenceLevel.BOUNDED_CHECKED,
                details={
                    **_base_details(task),
                    "reason": "declared TLA module or config is missing",
                    "missing_paths": missing_paths,
                },
            )

        command = task.payload.get("command", [])
        timeout_seconds = int(task.payload.get("timeout_seconds", DEFAULT_TLA_TIMEOUT_SECONDS))
        output_limit = int(task.payload.get("output_limit_bytes", DEFAULT_OUTPUT_LIMIT_BYTES))
        try:
            completed = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return BackendResult(
                backend=self.adapter_id,
                status="timeout",
                evidence_level=EvidenceLevel.BOUNDED_CHECKED,
                details={
                    **_base_details(task),
                    "timed_out": True,
                    "exit_code": None,
                    "stdout_hash": _sha256_output(stdout),
                    "stderr_hash": _sha256_output(stderr),
                    "stdout_tail": _bounded_tail(stdout, output_limit),
                    "stderr_tail": _bounded_tail(stderr, output_limit),
                },
            )
        except OSError as exc:
            return BackendResult(
                backend=self.adapter_id,
                status="invalid",
                evidence_level=EvidenceLevel.BOUNDED_CHECKED,
                details={**_base_details(task), "reason": str(exc)},
            )

        combined_output = completed.stdout + "\n" + completed.stderr
        violation = _model_violation_reason(combined_output)
        expected_exit_code = int(task.payload.get("expected_exit_code", 0))
        valid = completed.returncode == expected_exit_code and violation is None
        return BackendResult(
            backend=self.adapter_id,
            status="valid" if valid else "counterexample",
            evidence_level=EvidenceLevel.BOUNDED_CHECKED,
            details={
                **_base_details(task),
                "timed_out": False,
                "exit_code": completed.returncode,
                "expected_exit_code": expected_exit_code,
                "violation_reason": violation,
                "stdout_hash": _sha256_output(completed.stdout),
                "stderr_hash": _sha256_output(completed.stderr),
                "stdout_tail": _bounded_tail(completed.stdout, output_limit),
                "stderr_tail": _bounded_tail(completed.stderr, output_limit),
            },
        )

    def models_for_requirement(self, requirement_id: str) -> list[TlaModelCheck]:
        return [model for model in self.config.models if requirement_id in model.requirement_ids]

    def config_artifact_for_requirement(self, requirement_id: str) -> TlaModelConfigArtifact:
        return TlaModelConfigArtifact(models=self.models_for_requirement(requirement_id))

    def _payload_for_model(self, model: TlaModelCheck, requirement_id: str) -> dict[str, Any]:
        model_hashes, missing_paths = self._hash_paths([model.module, model.config])
        return {
            "adapter": self.adapter_id,
            "task": "tla_model_check",
            "model_id": model.model_id,
            "requirement_id": requirement_id,
            "requirement_ids": model.requirement_ids,
            "module": model.module,
            "config": model.config,
            "model_hashes": model_hashes,
            "missing_model_paths": missing_paths,
            "checker": model.checker,
            "command": model.command,
            "properties": model.properties,
            "bounds": model.bounds,
            "constants": model.constants,
            "timeout_seconds": model.timeout_seconds,
            "expected_exit_code": model.expected_exit_code,
            "requested_evidence": model.requested_evidence.value,
            "output_limit_bytes": model.output_limit_bytes,
            "model_config_hash": sha256_json(model),
        }

    def _hash_paths(self, paths: Iterable[str]) -> tuple[dict[str, str], list[str]]:
        hashes: dict[str, str] = {}
        missing: list[str] = []
        for path_text in paths:
            path = self._project_path(path_text)
            if not path.is_file():
                missing.append(path_text)
                continue
            hashes[path_text] = _sha256_file(path)
        return hashes, missing

    def _project_path(self, path_text: str) -> Path:
        path = self.project_root / path_text
        root = self.project_root.resolve()
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes project root: {path_text}") from exc
        return resolved


def _base_details(task: VerificationTask) -> dict[str, Any]:
    model_hashes = task.payload.get("model_hashes", {})
    return {
        "task_id": task.id,
        "task_input_hash": task.input_hash,
        "model_id": task.payload.get("model_id"),
        "requirement_ids": task.payload.get("requirement_ids", []),
        "module": task.payload.get("module"),
        "config": task.payload.get("config"),
        "module_hash": model_hashes.get(task.payload.get("module")),
        "config_hash": model_hashes.get(task.payload.get("config")),
        "checker": task.payload.get("checker"),
        "command": task.payload.get("command", []),
        "properties": task.payload.get("properties", []),
        "bounds": task.payload.get("bounds", {}),
        "constants": task.payload.get("constants", {}),
        "model_config_hash": task.payload.get("model_config_hash"),
    }


def _model_violation_reason(output: str) -> str | None:
    lowered = output.lower()
    markers = [
        "invariant is violated",
        "property is violated",
        "temporal property is violated",
        "counterexample",
        "error: invariant",
        "error: property",
    ]
    for marker in markers:
        if marker in lowered:
            return marker
    return None


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_output(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_tail(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[-limit:].decode("utf-8", errors="replace")


def _validate_relative_path(path: str, *, field: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field} must be a project-root-relative path")
