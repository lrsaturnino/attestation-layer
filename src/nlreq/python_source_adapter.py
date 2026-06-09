from __future__ import annotations

import ast
import platform
from pathlib import Path

from .models import EvidenceLevel, NormalizedTraceArtifact, SourceSpan, SymbolRef
from .source_adapter import (
    AdapterCapabilityClaim,
    AdapterCapabilityContract,
    AdapterLimitation,
    CodePresentation,
    SourceBinding,
    SourceBindingValidation,
    SourceCallEdge,
    SourceCallGraph,
    SourceLanguageAdapter,
    SourceManifest,
    SourceSymbol,
    SourceSymbolResolution,
)


# The CPython version whose built-in ``ast`` performed the parse — recorded as the analysis producer
# on every symbol and call graph (PC-14). This is what makes the Python adapter HONESTLY tool-backed
# rather than regex: a real parser ran, and its version is captured. ``ast`` is a static analyzer with
# no runtime trace producer, so this never lifts the adapter above static_resolution — the capability
# contract and the certification gate both keep it there.
_PYTHON_AST_VERSION = platform.python_version()


class PythonSourceLanguageAdapter(SourceLanguageAdapter):
    adapter_id = "python-source"
    language = "python"
    runtime = "cpython"
    ecosystem = "dynamic_scripting"
    # ast is a REAL static analyzer (not regex), but it produces no runtime traces, so the only level
    # it can honestly evidence is static_resolution. trace_capable/production_candidate are reserved
    # for adapters that PRODUCE provenanced traces (Solidity/Foundry, Go/runtime-trace); the
    # certification suite blocks any contract that claims a trace level it cannot evidence.
    capability_level = "static_resolution"
    supported_symbol_types = ("function", "async_function", "class")
    limitations = (
        AdapterLimitation(
            limitation_id="python-ast-nested-scope",
            category="analysis_depth",
            description=(
                "Definitions are indexed by name across the module's AST; a name defined more than "
                "once (a method shared by two classes, or a redefinition) is resolved by name without "
                "full scope qualification."
            ),
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="python-ast-dynamic-dispatch",
            category="dynamic_behavior",
            description=(
                "Dynamic dispatch (getattr, monkeypatching, decorators that rebind, runtime-built "
                "call targets) is not resolved by the static ast pass and needs explicit external "
                "evidence."
            ),
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="python-external-trace-producer",
            category="runtime_trace",
            description=(
                "Runtime traces must be supplied by a normalized cpython/OpenTelemetry producer; the "
                "ast adapter records no trace provenance of its own, so it cannot evidence "
                "TRACE_VALIDATED — it stays static_resolution."
            ),
            closure_effect="block",
        ),
    )

    def __init__(self, *, project_root: Path | None = None) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def resolve_symbol(self, ref: SymbolRef, manifest: SourceManifest) -> SourceSymbolResolution:
        matches: list[SourceSymbol] = []
        for module in manifest.modules:
            path = self._path(module.path)
            if not path.is_file():
                continue
            for name, node in _definitions(path).items():
                if name == ref.name:
                    matches.append(
                        SourceSymbol(
                            name=name,
                            module_id=module.module_id,
                            path=module.path,
                            symbol_type=_symbol_type(node),
                            source_span=_span_for_node(path, node),
                            metadata={
                                "analysis": "ast",
                                "python_version": _PYTHON_AST_VERSION,
                            },
                        )
                    )
        if len(matches) == 1:
            return SourceSymbolResolution(ref=ref, status="resolved", symbols=matches)
        if len(matches) > 1:
            return SourceSymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=matches,
                reason="symbol appears in multiple Python modules",
            )
        return SourceSymbolResolution(ref=ref, status="unresolved", reason="symbol not found")

    def call_graph(self, manifest: SourceManifest) -> SourceCallGraph:
        module_for_symbol = {
            symbol: module.module_id for module in manifest.modules for symbol in module.symbols
        }
        edges: list[SourceCallEdge] = []
        for module in manifest.modules:
            path = self._path(module.path)
            if not path.is_file():
                continue
            definitions = _definitions(path)
            for caller, node in definitions.items():
                for callee in sorted(_called_names(node)):
                    edges.append(
                        SourceCallEdge(
                            caller=f"{module.module_id}:{caller}",
                            callee=f"{module_for_symbol.get(callee, module.module_id)}:{callee}",
                        )
                    )
        return SourceCallGraph(
            adapter_id=self.adapter_id,
            language=self.language,
            modules=[module.module_id for module in manifest.modules],
            edges=edges,
            metadata={"analysis": "ast", "python_version": _PYTHON_AST_VERSION},
        )

    def validate_binding(self, binding: SourceBinding) -> SourceBindingValidation:
        if binding.adapter_id != self.adapter_id:
            return SourceBindingValidation(
                valid=False,
                reason=f"binding adapter mismatch: expected {self.adapter_id}, found {binding.adapter_id}",
            )
        path = self._path(binding.symbol.path)
        if not path.is_file():
            return SourceBindingValidation(valid=False, reason="source path does not exist")
        return SourceBindingValidation(valid=True)

    def present_to_llm(self, refs: list[SymbolRef], manifest: SourceManifest) -> CodePresentation:
        snippets: list[dict[str, str]] = []
        for ref in refs:
            result = self.resolve_symbol(ref, manifest)
            for symbol in result.symbols:
                path = self._path(symbol.path)
                snippets.append(
                    {
                        "symbol": symbol.name,
                        "path": symbol.path,
                        "content": _snippet(path, symbol.source_span),
                    }
                )
        return CodePresentation(
            adapter_id=self.adapter_id,
            language=self.language,
            snippets=snippets,
            metadata={"analysis": "ast"},
        )

    def extract_traces(self, manifest: SourceManifest) -> NormalizedTraceArtifact:
        traces = []
        for module in manifest.modules:
            for trace_source in module.trace_sources:
                artifact = NormalizedTraceArtifact.model_validate_json(
                    self._path(trace_source).read_text()
                )
                for trace in artifact.root:
                    traces.append(
                        trace.model_copy(
                            update={
                                "adapter_id": self.adapter_id,
                                "language": trace.language or self.language,
                                "runtime": trace.runtime or self.runtime,
                            }
                        )
                    )
        return NormalizedTraceArtifact.model_validate(traces)

    def parse_manifest(self, path: Path) -> SourceManifest:
        return SourceManifest.model_validate_json(path.read_text())

    def capability_contract(self) -> AdapterCapabilityContract:
        """The honest v2 capability contract for the ast-backed Python adapter (PC-14).

        Symbol resolution, the call graph, and code presentation are backed by CPython's built-in
        ``ast`` — a real parser, recorded as the ``analysis: "ast"`` producer with its version on every
        symbol and call graph — so they evidence STATICALLY_RESOLVED rather than the regex floor.
        ``ast`` runs no program, so the trace capabilities declare static_resolution with no trace
        evidence; the certification gate therefore certifies this adapter at static_resolution, never
        trace_capable. Mirrors the RegexProductionSourceAdapter contract shape so the conformance and
        certification suites read it identically.
        """
        limitation_ids = [limitation.limitation_id for limitation in self.limitations]
        runtime_limitation_ids = [
            limitation.limitation_id
            for limitation in self.limitations
            if limitation.category == "runtime_trace"
        ]
        return AdapterCapabilityContract(
            adapter_id=self.adapter_id,
            language=self.language,
            runtime=self.runtime,
            ecosystem=self.ecosystem,
            capability_level=self.capability_level,
            capabilities=[
                AdapterCapabilityClaim(
                    capability_id="manifest",
                    level="manifest_only",
                    notes="Consumes the common source manifest contract.",
                ),
                AdapterCapabilityClaim(
                    capability_id="binding_validation",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.STATICALLY_RESOLVED],
                    notes="Validates adapter identity and source path reachability.",
                ),
                AdapterCapabilityClaim(
                    capability_id="static_symbol_resolution",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.STATICALLY_RESOLVED],
                    limitation_ids=limitation_ids,
                    notes="Resolves functions and classes from the module's real ast, not a regex scan.",
                ),
                AdapterCapabilityClaim(
                    capability_id="call_graph",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.STATICALLY_RESOLVED],
                    limitation_ids=limitation_ids,
                    notes="Builds caller->callee edges from ast Call nodes, not a regex scan.",
                ),
                AdapterCapabilityClaim(
                    capability_id="code_presentation",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.REVIEWED],
                    notes="Presents ast-located source spans for human and model review.",
                ),
                AdapterCapabilityClaim(
                    capability_id="source_impact",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.STATICALLY_RESOLVED],
                    notes="Provides ast symbols and the call graph as source-impact inputs.",
                ),
                AdapterCapabilityClaim(
                    capability_id="coverage_mapping",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.REVIEWED],
                    notes="Maps source modules to reviewed specs through manifest module ids and spec refs.",
                ),
                AdapterCapabilityClaim(
                    capability_id="normalized_trace",
                    level="static_resolution",
                    evidence_labels=[],
                    requires_external_tool=True,
                    limitation_ids=runtime_limitation_ids,
                    notes=(
                        "Ingests externally-produced normalized trace artifacts declared by the "
                        "source manifest. It records no trace provenance of its own, so it cannot "
                        "evidence TRACE_VALIDATED — a real cpython trace producer would be required."
                    ),
                ),
                AdapterCapabilityClaim(
                    capability_id="runtime_trace_extraction",
                    level="static_resolution",
                    evidence_labels=[],
                    requires_external_tool=True,
                    limitation_ids=runtime_limitation_ids,
                    notes=(
                        "ast does not run the program, so the adapter extracts no traces of its own "
                        "and claims no trace evidence. Promoting this to trace_capable would require "
                        "recorded real-tool provenance (a captured runtime trace + producer version)."
                    ),
                ),
            ],
            limitations=list(self.limitations),
            supported_evidence=[
                EvidenceLevel.STATICALLY_RESOLVED,
                EvidenceLevel.REVIEWED,
            ],
            supported_symbol_types=list(self.supported_symbol_types),
            supported_trace_runtimes=[self.runtime] if self.runtime else [],
        )

    def _path(self, path_text: str) -> Path:
        path = (self.project_root / path_text).resolve(strict=False)
        root = self.project_root.resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes project root: {path_text}") from exc
        return path


def _definitions(path: Path) -> dict[str, ast.AST]:
    tree = ast.parse(path.read_text())
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                names.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                names.add(child.func.attr)
    return names


def _symbol_type(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async_function"
    return "function"


def _span_for_node(path: Path, node: ast.AST) -> SourceSpan | None:
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)
    if lineno is None or end_lineno is None:
        return None
    lines = path.read_text().splitlines(keepends=True)
    start_char = sum(len(line) for line in lines[: lineno - 1])
    end_char = sum(len(line) for line in lines[:end_lineno])
    return SourceSpan(
        document=path.as_posix(),
        start_char=start_char,
        end_char=end_char,
        text="".join(lines[lineno - 1 : end_lineno]),
    )


def _snippet(path: Path, span: SourceSpan | None) -> str:
    if span is None:
        return path.read_text()
    return span.text
