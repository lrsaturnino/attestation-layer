from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MODEL_CHECKER_RUNNER_SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT_LIMIT_BYTES = 4000


ModelCheckerOutcome = Literal[
    "valid",
    "counterexample",
    "timeout",
    "unsupported",
    "tool_error",
]


class ModelCheckerBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, gt=0)
    max_depth: int | None = Field(default=None, gt=0)
    max_states: int | None = Field(default=None, gt=0)
    memory_budget_mb: int | None = Field(default=None, gt=0)
    solver_options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ModelCheckerCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    checker_id: str
    command: list[str] = Field(min_length=1)
    cwd: str = "."
    budget: ModelCheckerBudget = Field(default_factory=ModelCheckerBudget)
    expected_exit_code: int = 0
    tool_version: str | None = None
    tool_version_command: list[str] | None = None
    output_limit_bytes: int = Field(default=DEFAULT_OUTPUT_LIMIT_BYTES, gt=0, le=20000)

    @model_validator(mode="after")
    def validate_command(self) -> ModelCheckerCommand:
        if any(not item for item in self.command):
            raise ValueError("command argv entries must be non-empty strings")
        if self.tool_version_command is not None and any(
            not item for item in self.tool_version_command
        ):
            raise ValueError("tool_version_command argv entries must be non-empty strings")
        return self


class ModelCheckerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    tail: str
    truncated: bool


class ModelCheckerCounterexample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["stdout", "stderr", "combined"]
    marker: str
    excerpt: str


class ModelCheckerReproducibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cwd: str
    command: list[str]
    command_line: str
    executable: str
    executable_resolved: str | None = None
    tool_version: str | None = None
    tool_version_command: list[str] | None = None
    budget: ModelCheckerBudget


class ModelCheckerRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = MODEL_CHECKER_RUNNER_SCHEMA_VERSION
    run_id: str
    checker_id: str
    outcome: ModelCheckerOutcome
    exit_code: int | None
    expected_exit_code: int
    timed_out: bool = False
    stdout: ModelCheckerOutput
    stderr: ModelCheckerOutput
    counterexamples: list[ModelCheckerCounterexample] = Field(default_factory=list)
    unsupported_markers: list[str] = Field(default_factory=list)
    tool_error: str | None = None
    reproducibility: ModelCheckerReproducibility


class ModelCheckerRunArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = MODEL_CHECKER_RUNNER_SCHEMA_VERSION
    runs: list[ModelCheckerRunResult] = Field(default_factory=list)


def run_model_checker(request: ModelCheckerCommand, *, project_root: Path | None = None) -> ModelCheckerRunResult:
    cwd = _resolve_cwd(project_root, request.cwd)
    version = request.tool_version
    if (
        version is None
        and request.tool_version_command is not None
        and _same_tool(request.command, request.tool_version_command)
    ):
        # A version probe only testifies to the *tool* it shares with the run. When the configured
        # tool_version_command invokes a different tool than request.command — a different binary
        # (a real `apalache-mc version` probe while the run executes an absent
        # `apalache-mc-not-installed`) or, for a JVM launcher, a different main class (a real
        # `java -cp tla2tools.jar tlc2.TLC` probe while the run is a bare `java -version`) — its
        # reported version belongs to a different program and must never be attributed to this run;
        # the version stays null. An explicit request.tool_version (a caller assertion) is untouched.
        version = _run_tool_version(request.tool_version_command, cwd=cwd, limit=request.output_limit_bytes)

    try:
        completed = subprocess.run(
            request.command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=request.budget.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return _result(
            request,
            cwd=cwd,
            outcome="timeout",
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            tool_version=version,
        )
    except OSError as exc:
        return _result(
            request,
            cwd=cwd,
            outcome="tool_error",
            exit_code=None,
            stdout="",
            stderr="",
            tool_error=str(exc),
            tool_version=version,
        )

    classification = _classify_output(completed.stdout, completed.stderr)
    outcome: ModelCheckerOutcome
    if classification[0] is not None:
        outcome = classification[0]
    elif completed.returncode != request.expected_exit_code:
        outcome = "tool_error"
    else:
        outcome = "valid"

    return _result(
        request,
        cwd=cwd,
        outcome=outcome,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        counterexamples=classification[1],
        unsupported_markers=classification[2],
        tool_error=(
            f"exit code {completed.returncode} did not match expected {request.expected_exit_code}"
            if outcome == "tool_error" and completed.returncode != request.expected_exit_code
            else None
        ),
        tool_version=version,
    )


def _resolve_cwd(project_root: Path | None, cwd_text: str) -> Path:
    cwd = Path(cwd_text)
    if cwd.is_absolute():
        return cwd.resolve(strict=False)
    root = Path(project_root) if project_root is not None else Path.cwd()
    return (root / cwd).resolve(strict=False)


# JVM launchers whose argv[0] names the *interpreter*, not the program it runs. `java -version`
# prints the JVM banner and never loads a checker; the real tool is the main class / -jar named
# in the arguments (e.g. tlc2.TLC), versioned independently of the JVM. So a version probe and a
# run that share only `java` may invoke entirely different programs — basename equality is not
# enough. Direct binaries (apalache-mc) and interpreters whose own version *is* the tool version
# (python running a script) are intentionally excluded: argv[0] names their tool. `javaw` is the
# Windows windowless launcher; same semantics as `java`.
_JVM_LAUNCHERS = frozenset({"java", "javaw"})

# `java` options that consume the following token as a separate value, so that value is not the
# main class. Conservative: an unlisted value-option would make its value look like a main class,
# which can only *split* two otherwise-equal identities (a probe stays unattributed) — the safe
# direction, never a false attribution.
_JAVA_VALUE_OPTIONS = frozenset(
    {
        "-cp",
        "-classpath",
        "--class-path",
        "-p",
        "--module-path",
        "--add-modules",
        "--add-exports",
        "--add-opens",
        "--add-reads",
        "--limit-modules",
        "--patch-module",
        "--upgrade-module-path",
        "--source",
    }
)


def _java_entrypoint(args: list[str]) -> tuple[str, ...]:
    """The program a `java` invocation runs, as an identity tuple, ignoring trailing program args.

    Resolves the three launch forms — ``-jar <jar>``, ``-m/--module <module>``, and a bare
    ``<MainClass>`` (after JVM options / classpath) — to the artifact that names the tool. A pure
    JVM invocation with no entrypoint (e.g. ``java -version``) returns ``()`` so it cannot be
    mistaken for any checker. The classpath only *locates* the class; the main class *names* the
    program, so it is the identity.
    """
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-jar" and index + 1 < len(args):
            return (f"jar:{Path(args[index + 1]).name}",)
        if token in {"-m", "--module"} and index + 1 < len(args):
            return (f"module:{args[index + 1]}",)
        if token in _JAVA_VALUE_OPTIONS:
            index += 2  # skip the option and its value (e.g. `-cp tla2tools.jar`)
            continue
        if token.startswith("-"):
            index += 1  # a JVM flag (joined or standalone): -version, -ea, -Xmx512m, -Dk=v, …
            continue
        return (f"class:{token}",)  # first bare token after JVM options is the main class
    return ()


def _tool_identity(command: list[str]) -> tuple[str, ...]:
    """The tool a command invokes, normalized so a version probe and the run it documents compare
    equal iff they invoke the same tool.

    For a direct binary the basename is the tool (``apalache-mc`` ≡ ``/x/apalache-mc``). For a JVM
    launcher the identity also includes the entrypoint (main class / jar), because the launcher
    runs different programs — and ``java -version`` reports the JVM, not the checker.
    """
    exe = Path(command[0]).name
    if exe in _JVM_LAUNCHERS:
        return (exe, *_java_entrypoint(command[1:]))
    return (exe,)


def _same_tool(command: list[str], version_command: list[str]) -> bool:
    """Whether a version probe invokes the same tool as the run it documents.

    Guards version provenance: a probe of a different tool must not lend its version to this run.
    See :func:`_tool_identity` for why basename equality is insufficient for JVM launchers.
    """
    return _tool_identity(command) == _tool_identity(version_command)


def _run_tool_version(command: list[str], *, cwd: Path, limit: int) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip()
    if not output:
        return None
    return _bounded_tail(output, limit).strip()


def _result(
    request: ModelCheckerCommand,
    *,
    cwd: Path,
    outcome: ModelCheckerOutcome,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    timed_out: bool = False,
    counterexamples: list[ModelCheckerCounterexample] | None = None,
    unsupported_markers: list[str] | None = None,
    tool_error: str | None = None,
    tool_version: str | None = None,
) -> ModelCheckerRunResult:
    executable = request.command[0]
    return ModelCheckerRunResult(
        run_id=request.run_id,
        checker_id=request.checker_id,
        outcome=outcome,
        exit_code=exit_code,
        expected_exit_code=request.expected_exit_code,
        timed_out=timed_out,
        stdout=_output(stdout, request.output_limit_bytes),
        stderr=_output(stderr, request.output_limit_bytes),
        counterexamples=counterexamples or [],
        unsupported_markers=unsupported_markers or [],
        tool_error=tool_error,
        reproducibility=ModelCheckerReproducibility(
            cwd=cwd.as_posix(),
            command=request.command,
            command_line=shlex.join(request.command),
            executable=executable,
            executable_resolved=shutil.which(executable),
            tool_version=tool_version,
            tool_version_command=request.tool_version_command,
            budget=request.budget,
        ),
    )


def _classify_output(
    stdout: str, stderr: str
) -> tuple[ModelCheckerOutcome | None, list[ModelCheckerCounterexample], list[str]]:
    combined = f"{stdout}\n{stderr}"
    lowered = combined.lower()

    for marker in [
        "timed out",
        "timeout",
        "time limit exceeded",
        "max depth reached",
        "state space limit",
        "state limit",
    ]:
        if marker in lowered:
            return "timeout", [], []

    unsupported_markers = [
        marker
        for marker in [
            "unsupported",
            "not supported",
            "unsupported operator",
            "unsupported construct",
        ]
        if marker in lowered
    ]
    if unsupported_markers:
        return "unsupported", [], unsupported_markers

    counterexamples: list[ModelCheckerCounterexample] = []
    for marker in [
        "counterexample",
        "the outcome is: error",
        "checker has found an error",
        "violation found",
        "invariant is violated",
        "is violated",
        "invariant violation",
        "property is violated",
        "temporal property is violated",
        "assertion failed",
    ]:
        if marker in lowered:
            counterexamples.append(
                ModelCheckerCounterexample(
                    source="combined",
                    marker=marker,
                    excerpt=_excerpt_for_marker(combined, marker),
                )
            )
    if counterexamples:
        return "counterexample", counterexamples, []

    for marker in [
        "the outcome is: noerror",
        "the outcome is: no error",
        "checker reports no error",
        "no error has been found",
        "model checking completed",
        "verification successful",
        "successfully verified",
    ]:
        if marker in lowered:
            return "valid", [], []

    return None, [], []


def _output(value: str, limit: int) -> ModelCheckerOutput:
    encoded = value.encode("utf-8")
    return ModelCheckerOutput(
        sha256="sha256:" + hashlib.sha256(encoded).hexdigest(),
        tail=_bounded_tail(value, limit),
        truncated=len(encoded) > limit,
    )


def _bounded_tail(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[-limit:].decode("utf-8", errors="replace")


def _excerpt_for_marker(output: str, marker: str) -> str:
    lowered = output.lower()
    index = lowered.find(marker)
    if index < 0:
        return _bounded_tail(output, 500)
    start = max(0, index - 160)
    end = min(len(output), index + len(marker) + 340)
    return output[start:end].strip()
