"""Pinned subprocess client that extracts real EVM traces with Foundry for the Solidity vertical (PC-4).

It runs ``forge test --json -vvvv`` over a checked-in Foundry project, captures the per-test EVM
call/log arena, and projects it into an ordered, decoded event list — call paths (decoded function
signatures), success/revert, emitted events (decoded names + params), and the values returned by
view reads so a state change is observable at call granularity. Decoding uses Foundry's own
artifacts (``methodIdentifiers`` for selectors, ``forge inspect ... events`` for event topics) — no
keccak dependency. The forge version and a hash of the raw forge output are recorded as the trace's
real-tool provenance. Forge absent / a compile failure / a timeout yield a non-extracted result so
the adapter degrades to ingestion rather than fabricating a trace.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FOUNDRY_CLIENT_SCHEMA_VERSION = "0.1"
DEFAULT_FOUNDRY_TIMEOUT_SECONDS = 300


class FoundryTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int
    kind: Literal["call", "log"]
    depth: int
    action: str
    success: bool | None = None
    caller: str | None = None
    address: str | None = None
    selector: str | None = None
    topic0: str | None = None
    topics: list[str] = Field(default_factory=list)
    data: str | None = None
    output: str | None = None
    decoded_output: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class FoundryTestTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    test: str
    status: str
    events: list[FoundryTraceEvent] = Field(default_factory=list)


class FoundryClientResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = FOUNDRY_CLIENT_SCHEMA_VERSION
    status: Literal["extracted", "unavailable", "tool_error"]
    forge_version: str | None = None
    raw_output_hash: str | None = None
    test_traces: list[FoundryTestTrace] = Field(default_factory=list)
    reason: str | None = None


def foundry_available() -> bool:
    """Whether forge can be driven here (tests skip with a recorded reason when it cannot)."""
    return shutil.which("forge") is not None


def _forge_version(forge: str, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            [forge, "--version"], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0].strip() if output else None


def _selector_map(out_dir: Path) -> dict[str, str]:
    """selector(8-hex) -> function signature, read from every build artifact's methodIdentifiers."""
    mapping: dict[str, str] = {}
    if not out_dir.is_dir():
        return mapping
    for artifact in out_dir.rglob("*.json"):
        try:
            data = json.loads(artifact.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        identifiers = data.get("methodIdentifiers")
        if isinstance(identifiers, dict):
            for signature, selector in identifiers.items():
                if isinstance(selector, str):
                    mapping[selector.lower()] = signature
    return mapping


def _event_abi_by_signature(out_dir: Path) -> dict[str, list[dict]]:
    """canonical event signature -> ABI inputs, read from every build artifact's ABI."""
    mapping: dict[str, list[dict]] = {}
    if not out_dir.is_dir():
        return mapping
    for artifact in out_dir.rglob("*.json"):
        try:
            data = json.loads(artifact.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for entry in data.get("abi", []) or []:
            if entry.get("type") != "event":
                continue
            inputs = entry.get("inputs", []) or []
            signature = f"{entry.get('name')}({','.join(i.get('type', '') for i in inputs)})"
            mapping[signature] = inputs
    return mapping


def _contract_names(out_dir: Path) -> set[str]:
    if not out_dir.is_dir():
        return set()
    return {artifact.stem for artifact in out_dir.rglob("*.json")}


def _event_topic_map(forge: str, cwd: Path, out_dir: Path) -> dict[str, dict]:
    """topic0(0x..) -> {"signature", "inputs"} by joining `forge inspect ... events` topics with ABI inputs."""
    abi_by_signature = _event_abi_by_signature(out_dir)
    topic_map: dict[str, dict] = {}
    for name in sorted(_contract_names(out_dir)):
        try:
            completed = subprocess.run(
                [forge, "inspect", name, "events", "--json"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode != 0:
            continue
        try:
            events = json.loads(completed.stdout)
        except json.JSONDecodeError:
            continue
        if not isinstance(events, dict):
            continue
        for signature, topic0 in events.items():
            if isinstance(topic0, str):
                topic_map[topic0.lower()] = {
                    "signature": signature,
                    "inputs": abi_by_signature.get(signature, []),
                }
    return topic_map


def _decode_uint(value: str | None) -> str | None:
    if not value or not value.startswith("0x"):
        return None
    body = value[2:]
    if not body or len(body) % 2 != 0:
        return None
    try:
        return str(int(body, 16))
    except ValueError:
        return None


def _decode_event_params(topics: list[str], data: str | None, inputs: list[dict]) -> dict[str, str]:
    """Best-effort decode of an event's params for simple scalar types (address/uint/bool/bytes32).

    Indexed params are read from topics[1:], non-indexed from the ABI-encoded data, positionally.
    Anything we cannot decode is left out; the raw topics/data are always retained on the event.
    """
    params: dict[str, str] = {}
    if not inputs:
        return params
    indexed = [i for i in inputs if i.get("indexed")]
    non_indexed = [i for i in inputs if not i.get("indexed")]
    for position, spec in enumerate(indexed):
        topic_index = position + 1
        if topic_index >= len(topics):
            break
        decoded = _decode_word(topics[topic_index], spec.get("type", ""))
        if decoded is not None:
            params[spec.get("name") or f"arg{position}"] = decoded
    body = (data or "")[2:] if (data or "").startswith("0x") else (data or "")
    for position, spec in enumerate(non_indexed):
        word = body[position * 64 : position * 64 + 64]
        if len(word) < 64:
            break
        decoded = _decode_word("0x" + word, spec.get("type", ""))
        if decoded is not None:
            params[spec.get("name") or f"data{position}"] = decoded
    return params


def _decode_word(word: str, abi_type: str) -> str | None:
    if not word.startswith("0x") or len(word) != 66:
        return None
    body = word[2:]
    if abi_type == "address":
        return "0x" + body[24:]
    if abi_type.startswith("uint") or abi_type.startswith("int"):
        try:
            return str(int(body, 16))
        except ValueError:
            return None
    if abi_type == "bool":
        return "true" if int(body, 16) else "false"
    if abi_type.startswith("bytes"):
        return "0x" + body
    return None


def _walk_arena(
    arena: list[dict],
    *,
    selector_map: dict[str, str],
    topic_map: dict[str, dict],
) -> list[FoundryTraceEvent]:
    nodes = {node["idx"]: node for node in arena}
    events: list[FoundryTraceEvent] = []
    counter = {"n": 0}

    def next_ordinal() -> int:
        value = counter["n"]
        counter["n"] += 1
        return value

    def emit_call(node: dict) -> None:
        trace = node.get("trace", {})
        data = trace.get("data")
        selector = None
        if isinstance(data, str) and len(data) >= 10:
            selector = data[2:10].lower()
        action = selector_map.get(selector or "", selector or trace.get("kind", "call"))
        output = trace.get("output")
        events.append(
            FoundryTraceEvent(
                ordinal=next_ordinal(),
                kind="call",
                depth=trace.get("depth", 0),
                action=action,
                success=trace.get("success"),
                caller=trace.get("caller"),
                address=trace.get("address"),
                selector=selector,
                data=data,
                output=output,
                decoded_output=_decode_uint(output),
            )
        )

    def emit_log(log: dict, depth: int) -> None:
        raw = log.get("raw_log", {})
        topics = raw.get("topics", []) or []
        topic0 = topics[0].lower() if topics else None
        event_meta = topic_map.get(topic0 or "")
        action = event_meta["signature"] if event_meta else (topic0 or "log")
        params = (
            _decode_event_params(topics, raw.get("data"), event_meta["inputs"])
            if event_meta
            else {}
        )
        events.append(
            FoundryTraceEvent(
                ordinal=next_ordinal(),
                kind="log",
                depth=depth,
                action=action,
                topic0=topic0,
                topics=topics,
                data=raw.get("data"),
                params=params,
            )
        )

    def visit(idx: int) -> None:
        node = nodes.get(idx)
        if node is None:
            return
        emit_call(node)
        children = node.get("children", []) or []
        trace = node.get("trace", {})
        for item in node.get("ordering", []) or []:
            if "Call" in item:
                child_position = item["Call"]
                if 0 <= child_position < len(children):
                    visit(children[child_position])
            elif "Log" in item:
                log_position = item["Log"]
                logs = node.get("logs", []) or []
                if 0 <= log_position < len(logs):
                    emit_log(logs[log_position], trace.get("depth", 0))

    roots = [node["idx"] for node in arena if node.get("parent") is None]
    for root in roots:
        visit(root)
    return events


def extract_foundry_traces(
    project_root: Path,
    *,
    test_filter: str | None = None,
    timeout_seconds: int = DEFAULT_FOUNDRY_TIMEOUT_SECONDS,
) -> FoundryClientResult:
    """Run ``forge test`` over the Foundry project and return decoded, ordered per-test traces."""
    forge = shutil.which("forge")
    if forge is None:
        return FoundryClientResult(status="unavailable", reason="forge (Foundry) is not installed")
    if not (project_root / "foundry.toml").is_file():
        return FoundryClientResult(
            status="unavailable",
            reason="project root has no foundry.toml; not a Foundry project",
        )
    command = [forge, "test", "--json", "-vvvv"]
    if test_filter:
        command += ["--match-test", test_filter]
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
        return FoundryClientResult(
            status="tool_error", reason=f"forge test timed out after {timeout_seconds}s"
        )
    except OSError as exc:
        return FoundryClientResult(status="tool_error", reason=f"forge could not be executed: {exc}")

    forge_version = _forge_version(forge, project_root)
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        tail = (completed.stderr or completed.stdout or "").strip()[-400:]
        return FoundryClientResult(
            status="tool_error",
            forge_version=forge_version,
            reason=f"forge test emitted no parseable JSON (exit {completed.returncode}): {tail}",
        )

    out_dir = project_root / "out"
    selector_map = _selector_map(out_dir)
    topic_map = _event_topic_map(forge, project_root, out_dir)
    raw_output_hash = "sha256:" + hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest()

    test_traces: list[FoundryTestTrace] = []
    for suite_id, suite in report.items():
        for test_name, test_result in (suite.get("test_results") or {}).items():
            events: list[FoundryTraceEvent] = []
            for kind, arena in test_result.get("traces") or []:
                if kind != "Execution":
                    continue
                events.extend(
                    _walk_arena(
                        arena.get("arena", []),
                        selector_map=selector_map,
                        topic_map=topic_map,
                    )
                )
            test_traces.append(
                FoundryTestTrace(
                    suite=suite_id,
                    test=test_name,
                    status=test_result.get("status", "unknown"),
                    events=events,
                )
            )

    if not test_traces:
        return FoundryClientResult(
            status="tool_error",
            forge_version=forge_version,
            raw_output_hash=raw_output_hash,
            reason="forge test produced no test results to trace",
        )
    return FoundryClientResult(
        status="extracted",
        forge_version=forge_version,
        raw_output_hash=raw_output_hash,
        test_traces=test_traces,
    )
