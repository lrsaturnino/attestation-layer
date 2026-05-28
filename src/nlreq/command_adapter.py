from __future__ import annotations

import hashlib
import os
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


COMMAND_SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT_LIMIT_BYTES = 4000
SHELL_EXECUTABLES = {
    "bash",
    "cmd",
    "fish",
    "powershell",
    "pwsh",
    "sh",
    "zsh",
}


class CommandCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    name: str
    requirement_ids: list[str] = Field(min_length=1)
    command: list[str] = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: int = Field(default=60, gt=0)
    expected_exit_code: int = 0
    target_paths: list[str] = Field(default_factory=list)
    test_paths: list[str] = Field(default_factory=list)
    requested_evidence: EvidenceLevel = EvidenceLevel.TEST_VALIDATED
    env: dict[str, str] = Field(default_factory=dict)
    output_limit_bytes: int = Field(default=DEFAULT_OUTPUT_LIMIT_BYTES, gt=0, le=20000)

    @model_validator(mode="after")
    def validate_check(self) -> CommandCheck:
        if self.requested_evidence != EvidenceLevel.TEST_VALIDATED:
            raise ValueError("command checks may only request TEST_VALIDATED evidence")
        if any(not part for part in self.command):
            raise ValueError("command argv entries must be non-empty strings")
        if _looks_like_shell_invocation(self.command):
            raise ValueError("command checks must not use shell -c invocations")
        _validate_relative_path(self.cwd, field="cwd")
        for path in [*self.target_paths, *self.test_paths]:
            _validate_relative_path(path, field="target_paths/test_paths")
        return self


class CommandChecksArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = COMMAND_SCHEMA_VERSION
    adapter: Literal["command"] = "command"
    checks: list[CommandCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_checks(self) -> CommandChecksArtifact:
        check_ids = [check.check_id for check in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("command check ids must be unique")
        return self


class CommandResultsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = COMMAND_SCHEMA_VERSION
    adapter: Literal["command"] = "command"
    results: list[BackendResult] = Field(default_factory=list)


def load_command_checks(path: Path) -> CommandChecksArtifact:
    return CommandChecksArtifact.model_validate_json(path.read_text())


class CommandAdapter(Adapter):
    adapter_id = "command"
    target_kind = "command_test_runner"

    def __init__(
        self,
        checks: CommandChecksArtifact,
        *,
        project_root: Path | None = None,
    ) -> None:
        self.checks = checks
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
                evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
                description="Requirement terms are resolved through the command adapter vocabulary.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TEST_VALIDATED,
                description="Reviewed command checks can produce bounded test-runner evidence.",
            ),
        ]

    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        tasks: list[VerificationTask] = []
        for check in self.checks_for_requirement(ir.requirement_id):
            payload = self._payload_for_check(check, ir.requirement_id)
            tasks.append(
                VerificationTask(
                    id=check.check_id,
                    backend="adapter",
                    description=f"Run command check {check.check_id} for {ir.requirement_id}.",
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
            raise TypeError(f"unsupported command adapter task result: {type(result).__name__}")
        return collected

    def run_task(self, task: VerificationTask) -> BackendResult:
        if task.payload.get("task") != "command_check":
            return BackendResult(
                backend=self.adapter_id,
                status="unsupported",
                details={"task_id": task.id, "task": task.payload.get("task")},
            )
        missing_paths = [
            *task.payload.get("missing_target_paths", []),
            *task.payload.get("missing_test_paths", []),
        ]
        if missing_paths:
            return BackendResult(
                backend=self.adapter_id,
                status="invalid",
                evidence_level=EvidenceLevel.TEST_VALIDATED,
                details={
                    **_base_result_details(task),
                    "reason": "declared target or test path is missing",
                    "missing_paths": missing_paths,
                },
            )

        command = task.payload.get("command", [])
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            return _invalid_command_result(task, "command payload must be an argv string list")
        try:
            cwd = self._cwd_for_task(task)
        except ValueError as exc:
            return _invalid_command_result(task, str(exc))

        timeout_seconds = int(task.payload.get("timeout_seconds", 60))
        output_limit = int(task.payload.get("output_limit_bytes", DEFAULT_OUTPUT_LIMIT_BYTES))
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
                env=self._env_for_task(task),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return BackendResult(
                backend=self.adapter_id,
                status="timeout",
                evidence_level=EvidenceLevel.TEST_VALIDATED,
                details={
                    **_base_result_details(task),
                    "exit_code": None,
                    "timed_out": True,
                    "timeout_seconds": timeout_seconds,
                    "stdout_hash": _sha256_output(stdout),
                    "stderr_hash": _sha256_output(stderr),
                    "stdout_tail": _bounded_tail(stdout, output_limit),
                    "stderr_tail": _bounded_tail(stderr, output_limit),
                    "output_truncated": _output_truncated(stdout, stderr, output_limit),
                },
            )
        except OSError as exc:
            return _invalid_command_result(task, str(exc))

        expected_exit_code = int(task.payload.get("expected_exit_code", 0))
        status = "valid" if completed.returncode == expected_exit_code else "invalid"
        return BackendResult(
            backend=self.adapter_id,
            status=status,
            evidence_level=EvidenceLevel.TEST_VALIDATED,
            details={
                **_base_result_details(task),
                "exit_code": completed.returncode,
                "expected_exit_code": expected_exit_code,
                "timed_out": False,
                "timeout_seconds": timeout_seconds,
                "stdout_hash": _sha256_output(completed.stdout),
                "stderr_hash": _sha256_output(completed.stderr),
                "stdout_tail": _bounded_tail(completed.stdout, output_limit),
                "stderr_tail": _bounded_tail(completed.stderr, output_limit),
                "output_truncated": _output_truncated(
                    completed.stdout, completed.stderr, output_limit
                ),
            },
        )

    def checks_for_requirement(self, requirement_id: str) -> list[CommandCheck]:
        return [
            check
            for check in self.checks.checks
            if requirement_id in check.requirement_ids
        ]

    def checks_artifact_for_requirement(self, requirement_id: str) -> CommandChecksArtifact:
        return CommandChecksArtifact(checks=self.checks_for_requirement(requirement_id))

    def _payload_for_check(self, check: CommandCheck, requirement_id: str) -> dict[str, Any]:
        target_hashes, missing_target_paths = self._hash_paths(check.target_paths)
        test_hashes, missing_test_paths = self._hash_paths(check.test_paths)
        payload = {
            "adapter": self.adapter_id,
            "task": "command_check",
            "check_id": check.check_id,
            "name": check.name,
            "requirement_id": requirement_id,
            "requirement_ids": check.requirement_ids,
            "command": check.command,
            "cwd": check.cwd,
            "timeout_seconds": check.timeout_seconds,
            "expected_exit_code": check.expected_exit_code,
            "target_paths": check.target_paths,
            "test_paths": check.test_paths,
            "target_hashes": target_hashes,
            "test_hashes": test_hashes,
            "missing_target_paths": missing_target_paths,
            "missing_test_paths": missing_test_paths,
            "requested_evidence": check.requested_evidence.value,
            "env_keys": sorted(check.env),
            "output_limit_bytes": check.output_limit_bytes,
            "check_config_hash": sha256_json(check),
        }
        return payload

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

    def _cwd_for_task(self, task: VerificationTask) -> Path:
        cwd = task.payload.get("cwd", ".")
        if not isinstance(cwd, str):
            raise ValueError("cwd payload must be a string")
        path = self._project_path(cwd)
        if not path.is_dir():
            raise ValueError(f"command cwd does not exist: {cwd}")
        return path

    def _project_path(self, path_text: str) -> Path:
        path = self.project_root / path_text
        root = self.project_root.resolve()
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes project root: {path_text}") from exc
        return resolved

    def _env_for_task(self, task: VerificationTask) -> dict[str, str] | None:
        check_id = task.payload.get("check_id")
        if not isinstance(check_id, str):
            return None
        check = next((item for item in self.checks.checks if item.check_id == check_id), None)
        if check is None or not check.env:
            return None
        env = dict(os.environ)
        env.update(check.env)
        return env


def _base_result_details(task: VerificationTask) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "task_input_hash": task.input_hash,
        "check_id": task.payload.get("check_id"),
        "requirement_ids": task.payload.get("requirement_ids", []),
        "command": task.payload.get("command", []),
        "cwd": task.payload.get("cwd", "."),
        "target_hashes": task.payload.get("target_hashes", {}),
        "test_hashes": task.payload.get("test_hashes", {}),
        "env_keys": task.payload.get("env_keys", []),
        "check_config_hash": task.payload.get("check_config_hash"),
    }


def _invalid_command_result(task: VerificationTask, reason: str) -> BackendResult:
    return BackendResult(
        backend="command",
        status="invalid",
        evidence_level=EvidenceLevel.TEST_VALIDATED,
        details={
            **_base_result_details(task),
            "reason": reason,
        },
    )


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_output(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_tail(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[-limit:].decode("utf-8", errors="replace")


def _output_truncated(stdout: str, stderr: str, limit: int) -> bool:
    return len(stdout.encode("utf-8")) > limit or len(stderr.encode("utf-8")) > limit


def _looks_like_shell_invocation(command: list[str]) -> bool:
    executable = Path(command[0]).name.lower()
    return executable in SHELL_EXECUTABLES and "-c" in command[1:]


def _validate_relative_path(path: str, *, field: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field} entries must be project-root-relative paths")
