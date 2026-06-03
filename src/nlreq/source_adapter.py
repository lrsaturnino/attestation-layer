from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .models import EvidenceLevel, NormalizedTraceArtifact, SourceSpan, SymbolRef


SOURCE_ADAPTER_SCHEMA_VERSION = "0.1"
SOURCE_ADAPTER_CAPABILITY_SCHEMA_VERSION = "0.2"
SOURCE_ADAPTER_INTERFACE_VERSION = "2.0"

AdapterCapabilityLevel = Literal[
    "manifest_only",
    "static_resolution",
    "trace_capable",
    "production_candidate",
]

AdapterCapabilityKind = Literal[
    "manifest",
    "binding_validation",
    "static_symbol_resolution",
    "call_graph",
    "code_presentation",
    "source_impact",
    "coverage_mapping",
    "normalized_trace",
    "runtime_trace_extraction",
    "specula_candidate_extraction",
]

AdapterEcosystem = Literal[
    "generic",
    "transaction_event",
    "compiled_service",
    "frontend_service",
    "compiled_system",
    "dynamic_scripting",
]


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


class AdapterLimitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limitation_id: str
    category: Literal[
        "analysis_depth",
        "language_feature",
        "runtime_trace",
        "tooling",
        "dynamic_behavior",
        "coverage_mapping",
        "specula_integration",
    ]
    description: str
    closure_effect: Literal["unsupported", "review", "block"] = "review"


class AdapterCapabilityClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: AdapterCapabilityKind
    level: AdapterCapabilityLevel
    evidence_labels: list[EvidenceLevel] = Field(default_factory=list)
    requires_external_tool: bool = False
    limitation_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class AdapterCapabilityContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SOURCE_ADAPTER_CAPABILITY_SCHEMA_VERSION
    interface_version: Literal["2.0"] = SOURCE_ADAPTER_INTERFACE_VERSION
    adapter_id: str
    language: str
    runtime: str | None = None
    ecosystem: AdapterEcosystem = "generic"
    capability_level: AdapterCapabilityLevel = "manifest_only"
    required_methods: list[str] = Field(
        default_factory=lambda: [
            "parse_manifest",
            "resolve_symbol",
            "validate_binding",
            "call_graph",
            "present_to_llm",
            "extract_traces",
            "capability_contract",
        ]
    )
    optional_methods: list[str] = Field(default_factory=list)
    capabilities: list[AdapterCapabilityClaim] = Field(default_factory=list)
    limitations: list[AdapterLimitation] = Field(default_factory=list)
    supported_evidence: list[EvidenceLevel] = Field(default_factory=list)
    supported_symbol_types: list[str] = Field(default_factory=list)
    supported_trace_runtimes: list[str] = Field(default_factory=list)
    failure_taxonomy: list[str] = Field(
        default_factory=lambda: [
            "unresolved_symbol",
            "ambiguous_symbol",
            "unsupported_language_feature",
            "missing_trace_source",
            "invalid_manifest",
        ]
    )

    @model_validator(mode="after")
    def validate_capability_contract(self) -> AdapterCapabilityContract:
        capability_ids = [claim.capability_id for claim in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("adapter capability ids must be unique")
        limitation_ids = [limitation.limitation_id for limitation in self.limitations]
        if len(limitation_ids) != len(set(limitation_ids)):
            raise ValueError("adapter limitation ids must be unique")
        known_limitations = set(limitation_ids)
        for claim in self.capabilities:
            unknown = sorted(set(claim.limitation_ids) - known_limitations)
            if unknown:
                raise ValueError(
                    f"capability {claim.capability_id} references unknown limitations: {unknown}"
                )
        declared_evidence = {
            evidence
            for claim in self.capabilities
            for evidence in claim.evidence_labels
        }
        unsupported = sorted(
            evidence.value
            for evidence in self.supported_evidence
            if evidence not in declared_evidence
        )
        if unsupported:
            raise ValueError(
                "supported_evidence must be backed by at least one capability claim: "
                + ", ".join(unsupported)
            )
        return self


class AdapterCapabilityRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.2"] = SOURCE_ADAPTER_CAPABILITY_SCHEMA_VERSION
    adapters: list[AdapterCapabilityContract] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_adapters(self) -> AdapterCapabilityRegistry:
        adapter_ids = [adapter.adapter_id for adapter in self.adapters]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("adapter capability registry adapter ids must be unique")
        return self


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

    def capability_contract(self) -> AdapterCapabilityContract:
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

    def capability_contract(self) -> AdapterCapabilityContract:
        return AdapterCapabilityContract(
            adapter_id=self.adapter_id,
            language=self.language,
            runtime=self.runtime,
            ecosystem="generic",
            capability_level="manifest_only",
            capabilities=[
                AdapterCapabilityClaim(
                    capability_id="manifest",
                    level="manifest_only",
                    notes="Parses source manifests and exposes declared symbols only.",
                ),
                AdapterCapabilityClaim(
                    capability_id="binding_validation",
                    level="manifest_only",
                    notes="Validates adapter identity on source bindings.",
                ),
            ],
            limitations=[
                AdapterLimitation(
                    limitation_id="null-no-static-analysis",
                    category="analysis_depth",
                    description="The null adapter does not inspect source files or produce gateable evidence.",
                    closure_effect="unsupported",
                )
            ],
            supported_symbol_types=["unknown"],
        )


def _validate_relative_path(path: str, *, field: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"{field} must be project-root-relative")
