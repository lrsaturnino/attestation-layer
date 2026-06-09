"""Pinned subprocess client that drives the real Go toolchain for the Go vertical (PC-6/PC-7).

Three real tools back the Go adapter, each run as a version-recorded subprocess:

* ``gopls symbols`` — type-aware symbol inventory per file (functions, methods with their
  receivers, types), so a method declared on two types resolves as ambiguous (Go's only
  symbol-resolution ambiguity source — it has no overloads).
* ``callgraph -algo=cha`` — a real CHA call graph. Interface dispatch resolves to every
  implementation of the interface, an edge a lexical pass cannot attribute to a concrete receiver.
* ``go test -trace`` + the vendored :mod:`golang.org/x/exp/trace` reader (``_go_trace_reader``) —
  a real runtime/trace extracted from a real Go execution, projected to goroutine-attributed,
  call-level events.

Every failure mode — a tool not installed, a build error, a timeout, a trace-format version the
pinned reader cannot parse — is reported as a non-``analyzed``/``extracted`` result so the adapter
degrades honestly to lexical static resolution / ingestion rather than fabricating a tool-backed
answer. The reader's runtime/trace format is coupled to the producing Go toolchain version; the
pinned, vendored x/exp/trace supports Go 1.21–1.26, and a newer format degrades (it does not crash).
"""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GO_CLIENT_SCHEMA_VERSION = "0.1"
DEFAULT_GO_TIMEOUT_SECONDS = 300

# The vendored runtime/trace reader module (the Go-vertical analogue of _slither_driver.py).
_TRACE_READER_DIR = Path(__file__).parent / "_go_trace_reader"

# A gopls symbols line: ``<name> <Kind> <startLine>:<startCol>-<endLine>:<endCol>``. The name has no
# internal whitespace (Go identifiers and ``(*Type).Method`` receivers contain none), so three
# whitespace-separated tokens always parse cleanly. A leading tab marks a nested member (an interface
# method, a struct field) of the preceding top-level container.
_GOPLS_SYMBOL_LINE = re.compile(
    r"^(?P<indent>\t*)(?P<name>\S+)\s+(?P<kind>\w+)\s+"
    r"(?P<sl>\d+):(?P<sc>\d+)-(?P<el>\d+):(?P<ec>\d+)\s*$"
)
# A method name from gopls / callgraph: ``(Recv).Method`` or ``(*Recv).Method``.
_METHOD_NAME = re.compile(r"^\(\*?(?P<recv>[^)]+)\)\.(?P<method>\w+)$")


# --- symbol resolution + call graph (PC-6) --------------------------------------------------------


class GoSymbol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    container: str | None = None
    file: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


class GoCallEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The package import path + package-relative symbol label of each endpoint (e.g.
    # "example.com/m/coordinator" + "(*Recorder).Run"). The manifest-aware adapter maps the package
    # to a module id; the client stays manifest-agnostic.
    caller_package: str
    caller_label: str
    callee_package: str
    callee_label: str


class GoAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    go_version: str | None = None
    gopls_version: str | None = None
    # The callgraph binary's own build provenance (the module that built it, e.g.
    # "golang.org/x/tools v0.45.0 (go1.26.0)"), read from `go version -m`. It identifies WHICH
    # callgraph produced the graph — the call-graph tool-backed gate keys on this, not on go_version
    # (the Go toolchain alone does not prove a callgraph binary ran).
    callgraph_version: str | None = None
    module_path: str | None = None
    files: list[str] = Field(default_factory=list)
    symbols: list[GoSymbol] = Field(default_factory=list)
    edges: list[GoCallEdge] = Field(default_factory=list)


class GoAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = GO_CLIENT_SCHEMA_VERSION
    status: Literal["analyzed", "unavailable", "tool_error"]
    analysis: GoAnalysis | None = None
    reason: str | None = None
    go_version: str | None = None
    gopls_version: str | None = None


def go_binary() -> str | None:
    return shutil.which("go")


def gopls_binary() -> str | None:
    return shutil.which("gopls")


def callgraph_binary() -> str | None:
    return shutil.which("callgraph")


def go_symbol_tools_available() -> bool:
    """Whether gopls + callgraph + go can be driven here (tests skip with a recorded reason)."""
    return go_binary() is not None and gopls_binary() is not None and callgraph_binary() is not None


def go_trace_tools_available() -> bool:
    """Whether go is present to run a traced test and the vendored reader module exists."""
    return go_binary() is not None and (_TRACE_READER_DIR / "main.go").is_file()


def _first_line(text: str) -> str | None:
    lines = text.strip().splitlines()
    return lines[0].strip() if lines else None


def _go_version(go: str, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            [go, "version"], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _first_line(completed.stdout or completed.stderr or "")


def _gopls_version(gopls: str, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            [gopls, "version"], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # gopls version prints the build info; the first line carries the version (e.g.
    # "golang.org/x/tools/gopls v0.22.0").
    return _first_line(completed.stdout or completed.stderr or "")


def _callgraph_version(go: str, callgraph: str, cwd: Path) -> str | None:
    """Capture the callgraph binary's build provenance via ``go version -m`` (PC-6).

    ``callgraph`` (golang.org/x/tools/cmd/callgraph) has no ``-version`` flag, so its identity is read
    from the Go build info embedded in the binary: a ``mod`` record carries the module that built it
    (``golang.org/x/tools vX.Y.Z``) and the first line carries the building Go toolchain
    (``go1.26.0``). The module version is the meaningful callgraph version; the toolchain is appended
    for reproducibility. Returns ``None`` only when the command cannot run — when build info is present
    but lacks a parseable ``mod`` record it falls back to the toolchain line, so an analyzed graph is
    never misclassified as non-tool-backed for want of a version.

    Like the call-graph backing signal it feeds, this is adapter-asserted, not preimage-bound: it
    proves a *callgraph* binary (not the regex fallback) produced the graph, not that its output is
    cryptographically tied to this version. Binding it to the tool's captured output is a future
    tightening, the same asymmetry documented on the certifier's call-graph gate.
    """
    try:
        completed = subprocess.run(
            [go, "version", "-m", callgraph],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    lines = completed.stdout.splitlines()
    # The first line is "<path>: go1.26.0"; keep the toolchain token after the colon.
    _, _, after_colon = lines[0].partition(": ")
    toolchain = after_colon.strip()
    for line in lines:
        fields = [field for field in line.split("\t") if field]
        # A module record is ("mod", "<module path>", "<version>", "<hash>") (the leading tab drops).
        if len(fields) >= 3 and fields[0] == "mod":
            module = f"{fields[1]} {fields[2]}"
            return f"{module} ({toolchain})" if toolchain else module
    return toolchain or None


def _go_module_path(go: str, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            [go, "list", "-m"], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return _first_line(completed.stdout or "")


def _package_import_path(module_path: str, relative_file: str) -> str:
    """The Go import path of the package containing ``relative_file`` within ``module_path``."""
    directory = str(PurePosixPath(relative_file).parent)
    if directory in ("", "."):
        return module_path
    return f"{module_path}/{directory}"


def _parse_gopls_symbols(file: str, stdout: str) -> list[GoSymbol]:
    """Parse ``gopls symbols <file>`` output into structured symbols.

    Top-level functions/methods/types are reported flush-left; interface methods and struct fields
    are reported tab-indented under the preceding container. A method name arrives receiver-qualified
    (``(*Recorder).Run``); the bare method name plus the receiver type are recorded so a method shared
    by two types resolves as ambiguous.
    """
    symbols: list[GoSymbol] = []
    current_container: str | None = None
    for line in stdout.splitlines():
        match = _GOPLS_SYMBOL_LINE.match(line)
        if not match:
            continue
        indent = match.group("indent")
        raw_name = match.group("name")
        kind = match.group("kind")
        method = _METHOD_NAME.match(raw_name)
        if method:
            name = method.group("method")
            container: str | None = method.group("recv")
        elif indent:
            # A nested member (interface method, struct field) belongs to the current container.
            name = raw_name
            container = current_container
        else:
            name = raw_name
            container = None
        if not indent and kind in {"Struct", "Interface"}:
            current_container = raw_name
        symbols.append(
            GoSymbol(
                name=name,
                kind=kind,
                container=container,
                file=file,
                start_line=int(match.group("sl")),
                start_col=int(match.group("sc")),
                end_line=int(match.group("el")),
                end_col=int(match.group("ec")),
            )
        )
    return symbols


def _run_gopls_symbols(
    gopls: str, file: Path, *, project_root: Path, timeout_seconds: int
) -> tuple[list[GoSymbol] | None, str | None]:
    try:
        completed = subprocess.run(
            [gopls, "symbols", str(file)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"gopls symbols timed out after {timeout_seconds}s"
    except OSError as exc:
        return None, f"gopls could not be executed: {exc}"
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()[-300:]
        return None, f"gopls symbols failed for {file.name} (exit {completed.returncode}): {tail}"
    rel = _relative_to(file, project_root)
    return _parse_gopls_symbols(rel, completed.stdout), None


def _relative_to(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _parse_go_node(node: str, module_path: str | None) -> tuple[str, str]:
    """Split a callgraph node into its (package import path, package-relative label).

    ``example.com/m/coordinator.Coordinate`` -> ("example.com/m/coordinator", "Coordinate").
    ``(*example.com/m/coordinator.Recorder).Run`` -> ("example.com/m/coordinator", "(*Recorder).Run").
    """
    node = node.strip()
    method = re.match(r"^\((?P<recv>\*?)(?P<recvpkg>.+)\)\.(?P<method>\w+)$", node)
    if method:
        receiver = method.group("recvpkg")
        package, _, type_name = receiver.rpartition(".")
        label = f"({method.group('recv')}{type_name}).{method.group('method')}"
        return package, label
    package, _, func = node.rpartition(".")
    return package, func


def _run_callgraph(
    callgraph: str,
    *,
    project_root: Path,
    module_path: str | None,
    timeout_seconds: int,
) -> tuple[list[GoCallEdge] | None, str | None]:
    """Run ``callgraph -algo=cha`` and keep the edges whose caller is in the analyzed module."""
    try:
        completed = subprocess.run(
            [callgraph, "-algo=cha", "-format={{.Caller}} --> {{.Callee}}", "./..."],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"callgraph timed out after {timeout_seconds}s"
    except OSError as exc:
        return None, f"callgraph could not be executed: {exc}"
    # callgraph exits non-zero if the package does not build; with no edges that is a real failure.
    if completed.returncode != 0 and not completed.stdout.strip():
        tail = (completed.stderr or "").strip()[-300:]
        return None, f"callgraph failed (exit {completed.returncode}): {tail}"
    edges: list[GoCallEdge] = []
    for line in completed.stdout.splitlines():
        if " --> " not in line:
            continue
        caller_node, _, callee_node = line.partition(" --> ")
        caller_pkg, caller_label = _parse_go_node(caller_node, module_path)
        callee_pkg, callee_label = _parse_go_node(callee_node, module_path)
        # Keep the analyzed module's OWN outgoing calls; drop stdlib/runtime internal edges.
        if module_path is None or not caller_pkg.startswith(module_path):
            continue
        edges.append(
            GoCallEdge(
                caller_package=caller_pkg,
                caller_label=caller_label,
                callee_package=callee_pkg,
                callee_label=callee_label,
            )
        )
    return edges, None


def analyze_go_source(
    module_files: list[Path],
    *,
    project_root: Path,
    timeout_seconds: int = DEFAULT_GO_TIMEOUT_SECONDS,
) -> GoAnalysisResult:
    """Resolve symbols (gopls) and the call graph (callgraph) for the Go module at ``project_root``.

    A non-``analyzed`` result means a tool was unavailable or could not be driven; the adapter then
    falls back to lexical static resolution and records the recorded reason — it never claims a
    tool-backed answer it did not produce.
    """
    go = go_binary()
    gopls = gopls_binary()
    callgraph = callgraph_binary()
    if go is None or gopls is None or callgraph is None:
        missing = [
            name
            for name, found in (("go", go), ("gopls", gopls), ("callgraph", callgraph))
            if found is None
        ]
        return GoAnalysisResult(
            status="unavailable",
            reason=f"go toolchain unavailable: missing {', '.join(missing)}",
        )
    existing = [path.resolve() for path in module_files if path.is_file()]
    if not existing:
        return GoAnalysisResult(
            status="tool_error",
            reason="no Go source files from the manifest were found on disk",
        )
    go_version = _go_version(go, project_root)
    gopls_version = _gopls_version(gopls, project_root)
    callgraph_version = _callgraph_version(go, callgraph, project_root)
    module_path = _go_module_path(go, project_root)

    symbols: list[GoSymbol] = []
    for file in existing:
        parsed, reason = _run_gopls_symbols(
            gopls, file, project_root=project_root, timeout_seconds=timeout_seconds
        )
        if parsed is None:
            return GoAnalysisResult(
                status="tool_error", go_version=go_version, gopls_version=gopls_version, reason=reason
            )
        symbols.extend(parsed)

    edges, reason = _run_callgraph(
        callgraph,
        project_root=project_root,
        module_path=module_path,
        timeout_seconds=timeout_seconds,
    )
    if edges is None:
        return GoAnalysisResult(
            status="tool_error", go_version=go_version, gopls_version=gopls_version, reason=reason
        )
    analysis = GoAnalysis(
        go_version=go_version,
        gopls_version=gopls_version,
        callgraph_version=callgraph_version,
        module_path=module_path,
        files=[_relative_to(file, project_root) for file in existing],
        symbols=symbols,
        edges=edges,
    )
    return GoAnalysisResult(
        status="analyzed", analysis=analysis, go_version=go_version, gopls_version=gopls_version
    )


# --- runtime/trace extraction (PC-7) --------------------------------------------------------------


class GoTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int
    kind: str
    goroutine: int
    time_ns: int
    name: str = ""
    category: str = ""
    message: str = ""
    task: int = 0


class GoTestTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str
    status: str
    events: list[GoTraceEvent] = Field(default_factory=list)


class GoTraceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = GO_CLIENT_SCHEMA_VERSION
    status: Literal["extracted", "unavailable", "tool_error"]
    go_version: str | None = None
    # raw_output is the base64-encoded RAW binary runtime/trace artifact (the real tool output the
    # events were projected from); raw_output_hash is sha256 of that base64 text. The capability gate
    # recomputes sha256(raw_output) and a Go-specific shape check decodes it and confirms the Go trace
    # magic header — so producer provenance stamped over ingested JSON cannot fake it (PC-1).
    raw_output_hash: str | None = None
    raw_output: str | None = None
    traces: list[GoTestTrace] = Field(default_factory=list)
    reason: str | None = None


def _run_reader(go: str, trace_file: Path, *, timeout_seconds: int) -> tuple[list[GoTraceEvent] | None, str | None]:
    """Run the vendored x/exp/trace reader over a binary trace and parse its NDJSON events."""
    import json

    try:
        completed = subprocess.run(
            [go, "run", "-mod=vendor", ".", str(trace_file.resolve())],
            cwd=str(_TRACE_READER_DIR),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"go trace reader timed out after {timeout_seconds}s"
    except OSError as exc:
        return None, f"go trace reader could not be executed: {exc}"
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip()[-300:]
        return None, f"go trace reader failed (exit {completed.returncode}): {tail}"
    events: list[GoTraceEvent] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(GoTraceEvent.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValueError):
            return None, "go trace reader emitted an unparseable event line"
    return events, None


def extract_go_traces(
    project_root: Path,
    *,
    packages: list[str],
    test_filter: str | None = None,
    timeout_seconds: int = DEFAULT_GO_TIMEOUT_SECONDS,
) -> GoTraceResult:
    """Run ``go test -trace`` over each package and extract a real runtime/trace per package.

    Each package's traced test run yields one binary runtime/trace; the vendored reader projects it
    to goroutine-attributed, call-level events. The base64 of the FIRST captured binary trace is the
    source-bound real-tool artifact recorded as provenance. Go absent / a build failure / a trace the
    pinned reader cannot parse yield a non-``extracted`` result so the adapter degrades to ingestion.
    """
    go = go_binary()
    if go is None:
        return GoTraceResult(status="unavailable", reason="go is not installed")
    if not (_TRACE_READER_DIR / "main.go").is_file():
        return GoTraceResult(status="unavailable", reason="vendored go trace reader is missing")
    if not (project_root / "go.mod").is_file():
        return GoTraceResult(
            status="unavailable", reason="project root has no go.mod; not a Go module"
        )
    go_version = _go_version(go, project_root)
    traces: list[GoTestTrace] = []
    first_raw: bytes | None = None
    for package in packages:
        with tempfile.TemporaryDirectory() as tmp:
            trace_file = Path(tmp) / "trace.out"
            command = [go, "test", package, "-trace", str(trace_file), "-count=1"]
            if test_filter:
                command += ["-run", test_filter]
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
                return GoTraceResult(
                    status="tool_error",
                    go_version=go_version,
                    reason=f"go test -trace timed out after {timeout_seconds}s",
                )
            except OSError as exc:
                return GoTraceResult(
                    status="tool_error",
                    go_version=go_version,
                    reason=f"go test could not be executed: {exc}",
                )
            if not trace_file.is_file() or trace_file.stat().st_size == 0:
                # A package with no tests (or a failed build) emits no usable trace; skip it.
                continue
            raw = trace_file.read_bytes()
            events, reason = _run_reader(go, trace_file, timeout_seconds=timeout_seconds)
            if events is None:
                return GoTraceResult(status="tool_error", go_version=go_version, reason=reason)
            if first_raw is None:
                first_raw = raw
            traces.append(
                GoTestTrace(
                    package=package,
                    status="Success" if completed.returncode == 0 else "Failure",
                    events=events,
                )
            )
    if not traces or first_raw is None:
        return GoTraceResult(
            status="tool_error",
            go_version=go_version,
            reason="go test -trace produced no runtime trace to extract",
        )
    raw_output = base64.b64encode(first_raw).decode("ascii")
    raw_output_hash = "sha256:" + hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
    return GoTraceResult(
        status="extracted",
        go_version=go_version,
        raw_output_hash=raw_output_hash,
        raw_output=raw_output,
        traces=traces,
    )
