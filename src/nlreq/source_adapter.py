from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .models import NormalizedTraceArtifact, SourceSpan, SymbolRef


SOURCE_ADAPTER_SCHEMA_VERSION = "0.1"


class SourceModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    path: str
    symbols: list[str] = Field(default_factory=list)
    spec_refs: list[str] = Field(default_factory=list)
    trace_sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_path(self) -> SourceModule:
        _validate_relative_path(self.path, field="path")
        for trace_source in self.trace_sources:
            _validate_relative_path(trace_source, field="trace_sources")
        return self


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = SOURCE_ADAPTER_SCHEMA_VERSION
    adapter: str
    language: str
    runtime: str | None = None
    modules: list[SourceModule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_modules(self) -> SourceManifest:
        module_ids = [module.module_id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("source module ids must be unique")
        return self


class SourceManifestArtifact(RootModel[SourceManifest]):
    pass


class SourceSymbol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    module_id: str
    path: str
    symbol_type: str = "unknown"
    source_span: SourceSpan | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceSymbolResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: SymbolRef
    status: Literal["resolved", "unresolved", "ambiguous"]
    symbols: list[SourceSymbol] = Field(default_factory=list)
    reason: str | None = None


class SourceCallEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caller: str
    callee: str
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceCallGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    language: str
    modules: list[str] = Field(default_factory=list)
    edges: list[SourceCallEdge] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    symbol: SourceSymbol


class SourceBindingValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    reason: str | None = None


class CodePresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    language: str
    snippets: list[dict[str, str]] = Field(default_factory=list)
    redactions: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceLanguageAdapter(Protocol):
    adapter_id: str
    language: str
    runtime: str | None

    def resolve_symbol(self, ref: SymbolRef, manifest: SourceManifest) -> SourceSymbolResolution:
        ...

    def call_graph(self, manifest: SourceManifest) -> SourceCallGraph:
        ...

    def validate_binding(self, binding: SourceBinding) -> SourceBindingValidation:
        ...

    def present_to_llm(self, refs: list[SymbolRef], manifest: SourceManifest) -> CodePresentation:
        ...

    def extract_traces(self, manifest: SourceManifest) -> NormalizedTraceArtifact:
        ...

    def parse_manifest(self, path: Path) -> SourceManifest:
        ...


class NullSourceLanguageAdapter:
    adapter_id = "null-source"
    language = "null"
    runtime = None

    def resolve_symbol(self, ref: SymbolRef, manifest: SourceManifest) -> SourceSymbolResolution:
        matches = [
            SourceSymbol(
                name=ref.name,
                module_id=module.module_id,
                path=module.path,
                symbol_type=ref.expected_type or "unknown",
            )
            for module in manifest.modules
            if ref.name in module.symbols
        ]
        if len(matches) == 1:
            return SourceSymbolResolution(ref=ref, status="resolved", symbols=matches)
        if len(matches) > 1:
            return SourceSymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=matches,
                reason="symbol appears in multiple source modules",
            )
        return SourceSymbolResolution(ref=ref, status="unresolved", reason="symbol not in manifest")

    def call_graph(self, manifest: SourceManifest) -> SourceCallGraph:
        return SourceCallGraph(
            adapter_id=self.adapter_id,
            language=manifest.language,
            modules=[module.module_id for module in manifest.modules],
            metadata={"source": "null-adapter"},
        )

    def validate_binding(self, binding: SourceBinding) -> SourceBindingValidation:
        if binding.adapter_id != self.adapter_id:
            return SourceBindingValidation(
                valid=False,
                reason=f"binding adapter mismatch: expected {self.adapter_id}, found {binding.adapter_id}",
            )
        return SourceBindingValidation(valid=True)

    def present_to_llm(self, refs: list[SymbolRef], manifest: SourceManifest) -> CodePresentation:
        snippets = [
            {
                "symbol": ref.name,
                "content": f"{manifest.language}:{ref.name}",
            }
            for ref in refs
        ]
        return CodePresentation(
            adapter_id=self.adapter_id,
            language=manifest.language,
            snippets=snippets,
            metadata={"source": "null-adapter"},
        )

    def extract_traces(self, manifest: SourceManifest) -> NormalizedTraceArtifact:
        return NormalizedTraceArtifact.model_validate([])

    def parse_manifest(self, path: Path) -> SourceManifest:
        return SourceManifest.model_validate_json(path.read_text())


def _validate_relative_path(path: str, *, field: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field} must be project-root-relative")
