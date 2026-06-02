from __future__ import annotations

import re
from dataclasses import dataclass
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


CALL_PATTERN = re.compile(r"(?:^|[^\w.])(?P<name>[A-Za-z_][$\w]*)\s*\(")
IGNORED_CALLS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "throw",
    "new",
    "require",
    "assert",
    "revert",
}


@dataclass(frozen=True)
class ProductionDefinition:
    name: str
    symbol_type: str
    start: int
    end: int


class RegexProductionSourceAdapter(SourceLanguageAdapter):
    adapter_id = "regex-production-source"
    language = "unknown"
    runtime = None
    definition_pattern: re.Pattern[str]

    def __init__(self, *, project_root: Path | None = None) -> None:
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def resolve_symbol(self, ref: SymbolRef, manifest: SourceManifest) -> SourceSymbolResolution:
        matches: list[SourceSymbol] = []
        for module in manifest.modules:
            path = self._path(module.path)
            if not path.is_file():
                continue
            for definition in _definitions(path, self.definition_pattern).values():
                if definition.name == ref.name:
                    matches.append(
                        SourceSymbol(
                            name=definition.name,
                            module_id=module.module_id,
                            path=module.path,
                            symbol_type=definition.symbol_type,
                            source_span=_span_for_definition(path, definition),
                        )
                    )
        if len(matches) == 1:
            return SourceSymbolResolution(ref=ref, status="resolved", symbols=matches)
        if len(matches) > 1:
            return SourceSymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=matches,
                reason=f"symbol appears in multiple {self.language} modules",
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
            definitions = _definitions(path, self.definition_pattern)
            for definition in definitions.values():
                snippet = _snippet_for_definition(path, definition)
                for callee in sorted(_called_names(snippet) - {definition.name}):
                    edges.append(
                        SourceCallEdge(
                            caller=f"{module.module_id}:{definition.name}",
                            callee=f"{module_for_symbol.get(callee, module.module_id)}:{callee}",
                        )
                    )
        return SourceCallGraph(
            adapter_id=self.adapter_id,
            language=self.language,
            modules=[module.module_id for module in manifest.modules],
            edges=edges,
            metadata={"analysis": "regex-static"},
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
                snippets.append(
                    {
                        "symbol": symbol.name,
                        "path": symbol.path,
                        "content": symbol.source_span.text if symbol.source_span else "",
                    }
                )
        return CodePresentation(
            adapter_id=self.adapter_id,
            language=self.language,
            snippets=snippets,
            metadata={"analysis": "regex-static"},
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


class SoliditySourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "solidity-source"
    language = "solidity"
    runtime = "evm"
    definition_pattern = re.compile(
        r"\b(?P<kind>contract|library|interface|function|event|modifier)\s+"
        r"(?P<name>[A-Za-z_]\w*)\b"
    )


class GoSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "go-source"
    language = "go"
    runtime = "go"
    definition_pattern = re.compile(
        r"\bfunc\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_]\w*)\s*\("
        r"|\btype\s+(?P<type_name>[A-Za-z_]\w*)\b"
    )


class TypeScriptSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "typescript-source"
    language = "typescript"
    runtime = "node"
    definition_pattern = re.compile(
        r"\b(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
        r"|\b(?:export\s+)?(?:const|let|var)\s+(?P<value_name>[A-Za-z_$][\w$]*)\s*="
        r"|\b(?:export\s+)?(?:class|interface|type)\s+(?P<type_name>[A-Za-z_$][\w$]*)\b"
    )


class RustSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "rust-source"
    language = "rust"
    runtime = "rust"
    definition_pattern = re.compile(
        r"\b(?:pub\s+)?fn\s+(?P<name>[A-Za-z_]\w*)\s*\("
        r"|\b(?:pub\s+)?(?:struct|enum|trait)\s+(?P<type_name>[A-Za-z_]\w*)\b"
    )


class JavaSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "java-source"
    language = "java"
    runtime = "jvm"
    definition_pattern = re.compile(
        r"\b(?:public|private|protected)?\s*(?:class|interface|enum)\s+"
        r"(?P<type_name>[A-Za-z_]\w*)\b"
        r"|\b(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z_<>\[\]]+\s+"
        r"(?P<name>[A-Za-z_]\w*)\s*\("
    )


def production_adapter_for_language(language: str, *, project_root: Path | None = None):
    adapters = {
        "solidity": SoliditySourceAdapter,
        "go": GoSourceAdapter,
        "typescript": TypeScriptSourceAdapter,
        "rust": RustSourceAdapter,
        "java": JavaSourceAdapter,
    }
    try:
        return adapters[language](project_root=project_root)
    except KeyError as exc:
        raise ValueError(f"unknown production adapter language: {language}") from exc


def _definitions(path: Path, pattern: re.Pattern[str]) -> dict[str, ProductionDefinition]:
    text = path.read_text()
    matches = list(pattern.finditer(text))
    definitions: dict[str, ProductionDefinition] = {}
    for index, match in enumerate(matches):
        name = (
            match.groupdict().get("name")
            or match.groupdict().get("type_name")
            or match.groupdict().get("value_name")
        )
        if not name:
            continue
        start = match.start()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        definitions[name] = ProductionDefinition(
            name=name,
            symbol_type=_symbol_type(match),
            start=start,
            end=next_start,
        )
    return definitions


def _symbol_type(match: re.Match[str]) -> str:
    groups = match.groupdict()
    if groups.get("type_name"):
        return "type"
    if groups.get("value_name"):
        return "value"
    kind = groups.get("kind")
    if kind is not None:
        return kind
    return "function"


def _called_names(snippet: str) -> set[str]:
    names = {match.group("name") for match in CALL_PATTERN.finditer(snippet)}
    return {name for name in names if name not in IGNORED_CALLS}


def _span_for_definition(path: Path, definition: ProductionDefinition) -> SourceSpan:
    text = path.read_text()
    return SourceSpan(
        document=path.as_posix(),
        start_char=definition.start,
        end_char=definition.end,
        text=text[definition.start : definition.end],
    )


def _snippet_for_definition(path: Path, definition: ProductionDefinition) -> str:
    text = path.read_text()
    return text[definition.start : definition.end]
