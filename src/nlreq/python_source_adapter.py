from __future__ import annotations

import ast
from pathlib import Path

from .models import NormalizedTraceArtifact, SourceSpan, SymbolRef
from .source_adapter import (
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


class PythonSourceLanguageAdapter(SourceLanguageAdapter):
    adapter_id = "python-source"
    language = "python"
    runtime = "cpython"

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
