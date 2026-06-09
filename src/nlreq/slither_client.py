"""Pinned subprocess client that drives the real Slither analyzer for the Solidity vertical (PC-3).

Slither lives in its own environment and is not importable from the project, so this client locates
the interpreter that has Slither and runs :mod:`nlreq._slither_driver` under it as a subprocess,
then parses the JSON the driver emits between sentinel markers. It records the interpreter and the
Slither version for provenance. Every failure mode — Slither not installed, the interpreter not
resolvable, a compilation error, a timeout — is reported as a non-``analyzed`` result so the caller
degrades honestly to static resolution rather than fabricating a tool-backed answer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._slither_driver import JSON_BEGIN, JSON_END


SLITHER_CLIENT_SCHEMA_VERSION = "0.1"
DEFAULT_SLITHER_TIMEOUT_SECONDS = 180


class SlitherSymbol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    signature: str
    container: str | None = None
    declarer: str | None = None
    visibility: str | None = None
    file: str | None = None
    start: int | None = None
    length: int | None = None


class SlitherCallEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caller_contract: str
    caller_signature: str
    caller_file: str | None = None
    callee_contract: str | None = None
    callee_signature: str
    callee_name: str
    callee_file: str | None = None
    kind: str = "internal"


class SlitherAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slither_version: str | None = None
    files: list[str] = Field(default_factory=list)
    symbols: list[SlitherSymbol] = Field(default_factory=list)
    edges: list[SlitherCallEdge] = Field(default_factory=list)


class SlitherClientResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SLITHER_CLIENT_SCHEMA_VERSION
    status: Literal["analyzed", "unavailable", "tool_error"]
    analysis: SlitherAnalysis | None = None
    reason: str | None = None
    interpreter: str | None = None
    slither_version: str | None = None


def slither_interpreter() -> str | None:
    """The Python interpreter that has Slither installed, or None when it cannot be located.

    Resolution order: an explicit ``NLREQ_SLITHER_PYTHON`` override; the shebang of the ``slither``
    console script (the pipx/venv layout points it at the env's python); a ``python``/``python3``
    sibling of the console script (a plain venv install). None means Slither is unavailable and the
    caller must degrade to static resolution.
    """
    override = os.environ.get("NLREQ_SLITHER_PYTHON")
    if override and Path(override).exists():
        return override
    console = shutil.which("slither")
    if console is None:
        return None
    console_path = Path(console)
    try:
        first_line = console_path.read_text(errors="replace").splitlines()[0]
        if first_line.startswith("#!"):
            interpreter = first_line[2:].strip().split()[0]
            if interpreter and Path(interpreter).exists():
                return interpreter
    except (OSError, IndexError):
        pass
    for name in ("python", "python3"):
        candidate = console_path.parent / name
        if candidate.exists():
            return str(candidate)
    return None


def slither_console() -> str | None:
    """Path to the ``slither`` CLI console script, or None when it is not on PATH.

    The CLI is what runs ``slither <target> --json -`` for the success gate; the interpreter
    (above) is what runs the driver for the rich call graph. An explicit ``NLREQ_SLITHER_CONSOLE``
    override wins for hermetic setups.
    """
    override = os.environ.get("NLREQ_SLITHER_CONSOLE")
    if override and Path(override).exists():
        return override
    return shutil.which("slither")


def slither_available() -> bool:
    """Whether Slither can be driven here (used by tests to skip with a recorded reason)."""
    return slither_interpreter() is not None and slither_console() is not None


class SlitherCliVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ``ok`` — Slither compiled and analyzed cleanly (``success: true``), regardless of detector
    # findings or the process exit code; ``failed`` — Slither reported ``success: false`` (a real
    # compilation/analysis failure); ``unparseable`` — no JSON object with a ``success`` field was
    # emitted; ``errored`` — the subprocess itself could not be run (timeout / OS error).
    outcome: Literal["ok", "failed", "unparseable", "errored"]
    error: str | None = None


def interpret_slither_cli(stdout: str) -> SlitherCliVerdict:
    """Decide success from the Slither CLI JSON ``success`` field — NOT the process exit code.

    ``slither <target> --json -`` exits NON-ZERO whenever its detectors report findings, even on a
    fully successful analysis, so the exit code is not a reliable success signal (the task warns of
    exactly this). The JSON ``success`` field is the authoritative signal: ``true`` on a clean
    compile+analysis regardless of detector findings, ``false`` on a compilation/analysis failure
    (with ``error`` populated). This function reads only that field, so it is the deterministic,
    tool-independent core the regression test exercises.
    """
    import json

    blob = stdout.strip()
    if not blob:
        return SlitherCliVerdict(outcome="unparseable")
    decoder = json.JSONDecoder()
    start = blob.find("{")
    if start == -1:
        return SlitherCliVerdict(outcome="unparseable")
    try:
        payload, _ = decoder.raw_decode(blob[start:])
    except json.JSONDecodeError:
        return SlitherCliVerdict(outcome="unparseable")
    if not isinstance(payload, dict) or "success" not in payload:
        return SlitherCliVerdict(outcome="unparseable")
    if payload.get("success") is True:
        return SlitherCliVerdict(outcome="ok")
    return SlitherCliVerdict(
        outcome="failed",
        error=str(payload.get("error") or "slither reported success=false"),
    )


def _run_slither_cli(
    console: str,
    target: Path,
    *,
    project_root: Path,
    timeout_seconds: int,
) -> SlitherCliVerdict:
    """Run ``slither <target> --json -`` and read the verdict from the JSON ``success`` field."""
    try:
        completed = subprocess.run(
            [console, str(target), "--json", "-"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return SlitherCliVerdict(
            outcome="errored", error=f"slither --json - timed out after {timeout_seconds}s"
        )
    except OSError as exc:
        return SlitherCliVerdict(outcome="errored", error=f"slither CLI could not be executed: {exc}")
    # Deliberately ignore completed.returncode: a non-zero exit accompanies detector findings on a
    # successful run. The JSON `success` field is the only success signal we trust.
    verdict = interpret_slither_cli(completed.stdout)
    if verdict.outcome == "unparseable":
        tail = (completed.stderr or completed.stdout or "").strip()[-300:]
        return SlitherCliVerdict(
            outcome="unparseable",
            error=f"slither --json - emitted no parseable JSON (exit {completed.returncode}): {tail}",
        )
    return verdict


def _slither_cli_version(console: str, project_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            [console, "--version"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0].strip() if output else None


def _extract_payload(stdout: str) -> dict | None:
    begin = stdout.find(JSON_BEGIN)
    end = stdout.find(JSON_END)
    if begin == -1 or end == -1 or end < begin:
        return None
    blob = stdout[begin + len(JSON_BEGIN) : end].strip()
    if not blob:
        return None
    import json

    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _run_slither_driver(
    interpreter: str,
    existing: list[Path],
    *,
    project_root: Path,
    timeout_seconds: int,
) -> tuple[dict | None, str | None]:
    """Run the driver under Slither's interpreter; return its parsed payload or a failure reason."""
    driver = Path(__file__).parent / "_slither_driver.py"
    command = [interpreter, str(driver), *[str(target) for target in existing]]
    try:
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"slither analysis timed out after {timeout_seconds}s"
    except OSError as exc:
        return None, f"slither interpreter could not be executed: {exc}"
    payload = _extract_payload(completed.stdout)
    if payload is None:
        tail = (completed.stderr or completed.stdout or "").strip()[-400:]
        return None, f"slither driver emitted no parseable result (exit {completed.returncode}): {tail}"
    if "error" in payload:
        return None, f"slither analysis failed: {payload.get('error')}"
    return payload, None


def analyze_with_slither(
    targets: list[Path],
    *,
    project_root: Path,
    timeout_seconds: int = DEFAULT_SLITHER_TIMEOUT_SECONDS,
) -> SlitherClientResult:
    """Analyze ``targets`` with Slither and return a structured, provenance-stamped result.

    PC-3 runs Slither in two steps. First the real ``slither <target> --json -`` CLI gates the
    analysis: its JSON ``success`` field — NOT the process exit code — decides whether Slither
    compiled and analyzed the sources cleanly (the CLI exits non-zero merely on detector findings).
    Only when every target passes that gate does the driver run under Slither's interpreter to
    extract the inheritance-resolved symbol inventory and the real call graph the CLI JSON cannot
    express. Any failure degrades to a non-``analyzed`` result so the caller falls back to static
    resolution rather than fabricating a tool-backed answer.
    """
    interpreter = slither_interpreter()
    console = slither_console()
    if interpreter is None or console is None:
        return SlitherClientResult(
            status="unavailable",
            reason="slither is not installed or its CLI/interpreter could not be resolved",
        )
    # Resolve to absolute paths so the driver finds them regardless of its working directory, while
    # cwd stays at project_root so relative Solidity imports still resolve.
    existing = [target.resolve() for target in targets if target.is_file()]
    if not existing:
        return SlitherClientResult(
            status="tool_error",
            interpreter=interpreter,
            reason="no Solidity source files from the manifest were found on disk",
        )
    version = _slither_cli_version(console, project_root)
    # --- CLI success gate (PC-3): the documented `success`-field contract, exit code ignored ------
    for target in existing:
        verdict = _run_slither_cli(
            console, target, project_root=project_root, timeout_seconds=timeout_seconds
        )
        if verdict.outcome != "ok":
            return SlitherClientResult(
                status="tool_error",
                interpreter=interpreter,
                slither_version=version,
                reason=(
                    f"slither --json - did not report success for {target.name} "
                    f"({verdict.outcome}): {verdict.error}"
                ),
            )
    # --- Rich extraction: only reached once Slither's own `success` gate passed for every target --
    payload, reason = _run_slither_driver(
        interpreter, existing, project_root=project_root, timeout_seconds=timeout_seconds
    )
    if payload is None:
        return SlitherClientResult(
            status="tool_error",
            interpreter=interpreter,
            slither_version=version,
            reason=reason,
        )
    analysis = SlitherAnalysis.model_validate(payload)
    return SlitherClientResult(
        status="analyzed",
        analysis=analysis,
        interpreter=interpreter,
        slither_version=version or analysis.slither_version,
    )
