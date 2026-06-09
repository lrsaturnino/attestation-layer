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


def slither_available() -> bool:
    """Whether Slither can be driven here (used by tests to skip with a recorded reason)."""
    return slither_interpreter() is not None


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


def analyze_with_slither(
    targets: list[Path],
    *,
    project_root: Path,
    timeout_seconds: int = DEFAULT_SLITHER_TIMEOUT_SECONDS,
) -> SlitherClientResult:
    """Run the Slither driver over ``targets`` and return a structured, provenance-stamped result."""
    interpreter = slither_interpreter()
    if interpreter is None:
        return SlitherClientResult(
            status="unavailable",
            reason="slither is not installed or its interpreter could not be resolved",
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
        return SlitherClientResult(
            status="tool_error",
            interpreter=interpreter,
            reason=f"slither analysis timed out after {timeout_seconds}s",
        )
    except OSError as exc:
        return SlitherClientResult(
            status="tool_error",
            interpreter=interpreter,
            reason=f"slither interpreter could not be executed: {exc}",
        )
    payload = _extract_payload(completed.stdout)
    if payload is None:
        tail = (completed.stderr or completed.stdout or "").strip()[-400:]
        return SlitherClientResult(
            status="tool_error",
            interpreter=interpreter,
            reason=f"slither driver emitted no parseable result (exit {completed.returncode}): {tail}",
        )
    if "error" in payload:
        return SlitherClientResult(
            status="tool_error",
            interpreter=interpreter,
            reason=f"slither analysis failed: {payload.get('error')}",
        )
    analysis = SlitherAnalysis.model_validate(payload)
    return SlitherClientResult(
        status="analyzed",
        analysis=analysis,
        interpreter=interpreter,
        slither_version=analysis.slither_version,
    )
