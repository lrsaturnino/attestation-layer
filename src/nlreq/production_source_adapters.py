from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import foundry_client, slither_client
from .models import (
    EvidenceLevel,
    NormalizedTrace,
    NormalizedTraceArtifact,
    NormalizedTraceProducer,
    SourceSpan,
    SymbolRef,
    TraceEvent,
)
from .source_adapter import (
    AdapterCapabilityClaim,
    AdapterCapabilityContract,
    AdapterCapabilityLevel,
    AdapterEcosystem,
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
    ecosystem: AdapterEcosystem = "generic"
    # A purely lexical (regex) adapter resolves symbols statically; it drives no ecosystem tool and
    # produces no provenanced traces, so the only level it can honestly evidence is
    # static_resolution. trace_capable/production_candidate are reserved for adapters that extract
    # traces with recorded real-tool provenance (a tool version + a real artifact hash) — the
    # adapter certification suite blocks any contract that claims a trace level it cannot evidence.
    capability_level: AdapterCapabilityLevel = "static_resolution"
    supported_symbol_types: tuple[str, ...] = ("function", "type", "value")
    trace_runtimes: tuple[str, ...] = ()
    limitations: tuple[AdapterLimitation, ...] = (
        AdapterLimitation(
            limitation_id="regex-static-analysis-depth",
            category="analysis_depth",
            description="Static extraction is lexical and does not replace ecosystem-native project analysis.",
            closure_effect="review",
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
            for definition in _definition_list(path, self.definition_pattern):
                if definition.name == ref.name:
                    matches.append(
                        SourceSymbol(
                            name=definition.name,
                            module_id=module.module_id,
                            path=module.path,
                            symbol_type=definition.symbol_type,
                            source_span=_span_for_definition(path, definition),
                            metadata=self._symbol_metadata(definition),
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
            definitions = _definition_list(path, self.definition_pattern)
            for definition in definitions:
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
            metadata={"analysis": "regex-static", **self._manifest_metadata(manifest)},
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

    def capability_contract(self) -> AdapterCapabilityContract:
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
                    limitation_ids=[limitation.limitation_id for limitation in self.limitations],
                ),
                AdapterCapabilityClaim(
                    capability_id="call_graph",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.STATICALLY_RESOLVED],
                    limitation_ids=[limitation.limitation_id for limitation in self.limitations],
                ),
                AdapterCapabilityClaim(
                    capability_id="code_presentation",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.REVIEWED],
                    notes="Presents source spans for human and model review.",
                ),
                AdapterCapabilityClaim(
                    capability_id="source_impact",
                    level="static_resolution",
                    evidence_labels=[EvidenceLevel.STATICALLY_RESOLVED],
                    notes="Provides symbols and call graph inputs for source impact analysis.",
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
                    limitation_ids=[
                        limitation.limitation_id
                        for limitation in self.limitations
                        if limitation.category == "runtime_trace"
                    ],
                    notes=(
                        "Ingests externally-produced normalized trace artifacts declared by the "
                        "source manifest. It records no trace provenance of its own, so it cannot "
                        "evidence TRACE_VALIDATED — a real ecosystem trace producer is required for "
                        "that (e.g. the Foundry-backed Solidity vertical)."
                    ),
                ),
                AdapterCapabilityClaim(
                    capability_id="runtime_trace_extraction",
                    level="static_resolution",
                    evidence_labels=[],
                    requires_external_tool=True,
                    limitation_ids=[
                        limitation.limitation_id
                        for limitation in self.limitations
                        if limitation.category == "runtime_trace"
                    ],
                    notes=(
                        "The lexical adapter does not run an ecosystem trace producer, so it claims "
                        "no trace evidence. Promoting this capability to trace_capable requires "
                        "recorded real-tool provenance (a captured tool version and a real artifact "
                        "hash); the certification suite blocks an unevidenced trace claim."
                    ),
                ),
            ],
            limitations=list(self.limitations),
            supported_evidence=[
                EvidenceLevel.STATICALLY_RESOLVED,
                EvidenceLevel.REVIEWED,
            ],
            supported_symbol_types=list(self.supported_symbol_types),
            supported_trace_runtimes=list(self.trace_runtimes or (self.runtime,) if self.runtime else ()),
        )

    def _path(self, path_text: str) -> Path:
        path = (self.project_root / path_text).resolve(strict=False)
        root = self.project_root.resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes project root: {path_text}") from exc
        return path

    def _symbol_metadata(self, definition: ProductionDefinition) -> dict[str, str]:
        return {"analysis": "regex-static"}

    def _manifest_metadata(self, manifest: SourceManifest) -> dict[str, str]:
        return {
            "declared_symbols": str(sum(len(module.symbols) for module in manifest.modules)),
            "declared_spec_refs": str(sum(len(module.spec_refs) for module in manifest.modules)),
        }


class SoliditySourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "solidity-source"
    language = "solidity"
    runtime = "evm"
    ecosystem = "transaction_event"
    supported_symbol_types = ("contract", "library", "interface", "function", "event", "modifier")
    trace_runtimes = ("evm", "foundry", "debug_traceTransaction")
    limitations = (
        AdapterLimitation(
            limitation_id="solidity-overload-ambiguity",
            category="language_feature",
            description="Overloaded functions with the same source name are reported as ambiguous unless the manifest provides a unique binding strategy.",
            closure_effect="block",
        ),
        AdapterLimitation(
            limitation_id="solidity-inheritance-static-depth",
            category="analysis_depth",
            description="Inheritance, overloads, and the call graph are resolved by Slither when it is available; if Slither cannot be driven the adapter falls back to lexical extraction and reports static_resolution with a recorded skip reason.",
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="solidity-external-trace-producer",
            category="runtime_trace",
            description="Transaction traces must come from a normalized Foundry or debug_traceTransaction producer.",
            closure_effect="block",
        ),
    )
    definition_pattern = re.compile(
        r"\b(?P<kind>contract|library|interface|function|event|modifier)\s+"
        r"(?P<name>[A-Za-z_]\w*)\b"
    )

    def _symbol_metadata(self, definition: ProductionDefinition) -> dict[str, str]:
        return {
            "analysis": "regex-static",
            "ecosystem": "evm",
            "binding_role": "event" if definition.symbol_type == "event" else "source_symbol",
        }

    # --- Slither-backed resolution + call graph (PC-3) ------------------------------------------
    # When Slither can be driven, symbol resolution is inheritance- and overload-aware and the call
    # graph is real (a base call from a derived contract resolves to the base that declares it).
    # When Slither is unavailable the adapter degrades to the lexical RegexProductionSourceAdapter
    # behaviour and records the skip reason; it never claims a Slither-backed result it did not run.

    def _slither_result(self, manifest: SourceManifest):
        cache: dict[tuple[str, ...], object] = self.__dict__.setdefault("_slither_results", {})
        key = tuple(sorted(module.path for module in manifest.modules))
        if key not in cache:
            targets = [self._path(module.path) for module in manifest.modules]
            cache[key] = slither_client.analyze_with_slither(
                targets, project_root=self.project_root.resolve(strict=False)
            )
        return cache[key]

    def _file_to_module(self, manifest: SourceManifest) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for module in manifest.modules:
            mapping[module.path] = module.module_id
            mapping[Path(module.path).name] = module.module_id
        return mapping

    def _module_for_file(self, file: str | None, manifest: SourceManifest) -> str | None:
        if not file:
            return None
        mapping = self._file_to_module(manifest)
        return mapping.get(file) or mapping.get(Path(file).name)

    def _module_path_for_file(self, file: str | None, manifest: SourceManifest) -> str | None:
        if not file:
            return None
        basename = Path(file).name
        for module in manifest.modules:
            if module.path == file or Path(module.path).name == basename:
                return module.path
        return None

    def _slither_span(self, symbol, manifest: SourceManifest) -> SourceSpan | None:
        if symbol.start is None or symbol.length is None:
            return None
        module_path = self._module_path_for_file(symbol.file, manifest)
        if module_path is None:
            return None
        path = self._path(module_path)
        if not path.is_file():
            return None
        text = path.read_text()
        end = symbol.start + symbol.length
        return SourceSpan(
            document=path.as_posix(),
            start_char=symbol.start,
            end_char=min(end, len(text)),
            text=text[symbol.start : end],
        )

    @staticmethod
    def _slither_symbol_type(kind: str) -> str:
        return kind if kind in {"contract", "library", "interface", "function", "event", "modifier"} else "function"

    def resolve_symbol(self, ref: SymbolRef, manifest: SourceManifest) -> SourceSymbolResolution:
        result = self._slither_result(manifest)
        analysis = getattr(result, "analysis", None)
        if getattr(result, "status", None) != "analyzed" or analysis is None:
            return super().resolve_symbol(ref, manifest)

        seen: set[tuple[str, str | None, str]] = set()
        matches: list[SourceSymbol] = []
        for symbol in analysis.symbols:
            if symbol.name != ref.name:
                continue
            # A function inherited by N contracts appears N times with the same declarer+signature;
            # collapse to its single definition so inheritance does not look like ambiguity, while
            # genuine overloads (same name, different signature) stay distinct and resolve ambiguous.
            identity = (symbol.kind, symbol.declarer, symbol.signature)
            if identity in seen:
                continue
            seen.add(identity)
            module_id = self._module_for_file(symbol.file, manifest) or (
                manifest.modules[0].module_id if manifest.modules else "unknown"
            )
            module_path = self._module_path_for_file(symbol.file, manifest) or (
                manifest.modules[0].path if manifest.modules else ""
            )
            matches.append(
                SourceSymbol(
                    name=symbol.name,
                    module_id=module_id,
                    path=module_path,
                    symbol_type=self._slither_symbol_type(symbol.kind),
                    source_span=self._slither_span(symbol, manifest),
                    metadata={
                        "analysis": "slither",
                        "ecosystem": "evm",
                        "binding_role": "event" if symbol.kind == "event" else "source_symbol",
                        "signature": symbol.signature,
                        "declarer": symbol.declarer or "",
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
                reason=(
                    f"symbol resolves to {len(matches)} Slither-analyzed definitions "
                    "(overloaded or multiply-declared)"
                ),
            )
        return SourceSymbolResolution(
            ref=ref, status="unresolved", reason="symbol not found by Slither analysis"
        )

    def call_graph(self, manifest: SourceManifest) -> SourceCallGraph:
        result = self._slither_result(manifest)
        analysis = getattr(result, "analysis", None)
        if getattr(result, "status", None) != "analyzed" or analysis is None:
            graph = super().call_graph(manifest)
            graph.metadata["slither_status"] = getattr(result, "status", "unavailable")
            reason = getattr(result, "reason", None)
            if reason:
                graph.metadata["slither_skip_reason"] = reason
            return graph

        edges: list[SourceCallEdge] = []
        for edge in analysis.edges:
            caller_module = self._module_for_file(edge.caller_file, manifest) or edge.caller_contract
            callee_module = (
                self._module_for_file(edge.callee_file, manifest)
                or edge.callee_contract
                or caller_module
            )
            edges.append(
                SourceCallEdge(
                    caller=f"{caller_module}:{edge.caller_signature}",
                    callee=f"{callee_module}:{edge.callee_signature}",
                    metadata={
                        "kind": edge.kind,
                        "caller_contract": edge.caller_contract,
                        "callee_contract": edge.callee_contract or "",
                        "callee_name": edge.callee_name,
                    },
                )
            )
        metadata = {
            "analysis": "slither",
            "slither_status": "analyzed",
            **self._manifest_metadata(manifest),
        }
        if analysis.slither_version:
            metadata["slither_version"] = analysis.slither_version
        return SourceCallGraph(
            adapter_id=self.adapter_id,
            language=self.language,
            modules=[module.module_id for module in manifest.modules],
            edges=edges,
            metadata=metadata,
        )

    # --- Foundry-backed trace extraction (PC-4) -------------------------------------------------
    # When the project root is a Foundry project, the adapter PRODUCES traces by running the test
    # suite and projecting the real EVM call/log arena onto the NormalizedTrace contract — call
    # paths, success/revert, emitted events, decoded params, and the values returned by view reads
    # so a state change is observable at call granularity. The produced traces carry forge producer
    # provenance, so they are real-tool evidence the certification gate accepts. Without a Foundry
    # project (or with forge absent) it falls back to ingesting manifest-declared trace JSON, which
    # carries no provenance and so never lifts the adapter above static_resolution.

    def _foundry_result(self):
        project_root = self.project_root.resolve(strict=False)
        cache = self.__dict__.setdefault("_foundry_results", {})
        key = str(project_root)
        if key not in cache:
            cache[key] = foundry_client.extract_foundry_traces(project_root)
        return cache[key]

    def extract_traces(self, manifest: SourceManifest) -> NormalizedTraceArtifact:
        result = self._foundry_result()
        if result.status != "extracted":
            return super().extract_traces(manifest)
        producer = NormalizedTraceProducer(
            tool="forge", tool_version=result.forge_version or "forge"
        )
        source_hash = result.raw_output_hash or "sha256:unknown"
        traces: list[NormalizedTrace] = []
        for test_trace in result.test_traces:
            events = [self._normalize_foundry_event(event) for event in test_trace.events]
            traces.append(
                NormalizedTrace(
                    trace_id=f"{test_trace.suite}::{test_trace.test}",
                    adapter_id=self.adapter_id,
                    source_hash=source_hash,
                    language=self.language,
                    runtime=self.runtime,
                    events=events,
                    producer=producer,
                    metadata={
                        "producer": "foundry",
                        "forge_version": result.forge_version or "",
                        "test_status": test_trace.status,
                        "suite": test_trace.suite,
                        "test": test_trace.test,
                    },
                )
            )
        return NormalizedTraceArtifact.model_validate(traces)

    @staticmethod
    def _normalize_foundry_event(event) -> TraceEvent:
        metadata: dict[str, object] = {
            "kind": event.kind,
            "depth": event.depth,
            "evm_runtime": "foundry",
        }
        if event.success is not None:
            metadata["success"] = event.success
        if event.address:
            metadata["address"] = event.address
        if event.selector:
            metadata["selector"] = event.selector
        if event.topic0:
            metadata["topic0"] = event.topic0
        if event.topics:
            metadata["topics"] = event.topics
        if event.data:
            metadata["data"] = event.data
        if event.output:
            metadata["output"] = event.output
        if event.decoded_output is not None:
            metadata["decoded_output"] = event.decoded_output
        if event.params:
            metadata["params"] = event.params
        post_state: dict[str, object] | None = None
        if event.kind == "call" and event.decoded_output is not None:
            # A view read's decoded return makes the post-call state observable in the trace.
            post_state = {"return": event.decoded_output}
        elif event.kind == "log" and event.params:
            post_state = {"event_params": event.params}
        return TraceEvent(
            event_id=f"{event.kind}-{event.ordinal}",
            timestamp=event.ordinal,
            actor=event.caller,
            action=event.action,
            post_state=post_state,
            language="solidity",
            runtime="evm",
            metadata=metadata,
        )


class GoSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "go-source"
    language = "go"
    runtime = "go"
    ecosystem = "compiled_service"
    supported_symbol_types = ("function", "method", "type")
    trace_runtimes = ("go", "opentelemetry")
    limitations = (
        AdapterLimitation(
            limitation_id="go-build-tags-and-generics",
            category="language_feature",
            description="Build tags, generated files, and generic instantiation are not expanded by the lexical adapter slice.",
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="go-external-trace-producer",
            category="runtime_trace",
            description="Runtime traces must be supplied by a normalized runtime/trace or OpenTelemetry producer.",
            closure_effect="block",
        ),
        AdapterLimitation(
            limitation_id="go-specula-external",
            category="specula_integration",
            description="Specula-style candidate extraction uses adapter presentations and remains untrusted until reviewed.",
            closure_effect="review",
        ),
    )
    definition_pattern = re.compile(
        r"\bfunc\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_]\w*)\s*\("
        r"|\btype\s+(?P<type_name>[A-Za-z_]\w*)\b"
    )

    def _symbol_metadata(self, definition: ProductionDefinition) -> dict[str, str]:
        return {"analysis": "regex-static", "ecosystem": "go"}

    def _manifest_metadata(self, manifest: SourceManifest) -> dict[str, str]:
        package_count = len({module.module_id.split(":")[0] for module in manifest.modules})
        return {**super()._manifest_metadata(manifest), "package_count": str(package_count)}


class TypeScriptSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "typescript-source"
    language = "typescript"
    runtime = "node"
    ecosystem = "frontend_service"
    supported_symbol_types = ("function", "value", "class", "interface", "type")
    trace_runtimes = ("node", "browser", "opentelemetry")
    limitations = (
        AdapterLimitation(
            limitation_id="typescript-compiler-api-not-required",
            category="tooling",
            description="The graduation slice exposes a compiler-API-compatible contract but the bundled adapter uses lexical extraction for committed fixtures.",
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="typescript-dynamic-imports",
            category="dynamic_behavior",
            description="Dynamic imports, computed exports, and source-map reconstruction require explicit external evidence.",
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="typescript-external-trace-producer",
            category="runtime_trace",
            description="Browser and Node traces must be supplied through normalized trace producers.",
            closure_effect="block",
        ),
    )
    definition_pattern = re.compile(
        r"\b(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
        r"|\b(?:export\s+)?(?:const|let|var)\s+(?P<value_name>[A-Za-z_$][\w$]*)\s*="
        r"|\b(?:export\s+)?(?:class|interface|type)\s+(?P<type_name>[A-Za-z_$][\w$]*)\b"
    )


class JavaScriptProductionSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "javascript-source"
    language = "javascript"
    runtime = "node"
    ecosystem = "dynamic_scripting"
    supported_symbol_types = ("function", "value", "class")
    trace_runtimes = ("node", "browser", "opentelemetry")
    limitations = (
        AdapterLimitation(
            limitation_id="javascript-dynamic-properties",
            category="dynamic_behavior",
            description="Computed properties, monkey patching, eval, and runtime-only exports are unsupported without explicit external evidence.",
            closure_effect="unsupported",
        ),
        AdapterLimitation(
            limitation_id="javascript-external-trace-producer",
            category="runtime_trace",
            description="Browser and Node traces must be supplied through normalized trace producers.",
            closure_effect="block",
        ),
    )
    definition_pattern = re.compile(
        r"\b(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
        r"|\b(?:export\s+)?(?:const|let|var)\s+(?P<value_name>[A-Za-z_$][\w$]*)\s*="
        r"|\b(?:export\s+)?class\s+(?P<type_name>[A-Za-z_$][\w$]*)\b"
    )


class RustSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "rust-source"
    language = "rust"
    runtime = "rust"
    ecosystem = "compiled_system"
    supported_symbol_types = ("function", "struct", "enum", "trait", "type")
    trace_runtimes = ("rust", "opentelemetry", "tracing")
    limitations = (
        AdapterLimitation(
            limitation_id="rust-macro-expansion",
            category="language_feature",
            description="Macro-expanded symbols and compiler MIR facts require rust-analyzer or compiler integration outside this lexical slice.",
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="rust-external-trace-producer",
            category="runtime_trace",
            description="Runtime traces must be supplied by normalized tracing/OpenTelemetry producers.",
            closure_effect="block",
        ),
    )
    definition_pattern = re.compile(
        r"\b(?:pub\s+)?fn\s+(?P<name>[A-Za-z_]\w*)\s*\("
        r"|\b(?:pub\s+)?(?:struct|enum|trait)\s+(?P<type_name>[A-Za-z_]\w*)\b"
    )


class JavaSourceAdapter(RegexProductionSourceAdapter):
    adapter_id = "java-source"
    language = "java"
    runtime = "jvm"
    ecosystem = "compiled_service"
    supported_symbol_types = ("method", "class", "interface", "enum", "type")
    trace_runtimes = ("jvm", "jfr", "opentelemetry")
    limitations = (
        AdapterLimitation(
            limitation_id="java-overload-ambiguity",
            category="language_feature",
            description="Overloaded methods with the same source name are reported as ambiguous unless a unique binding is supplied.",
            closure_effect="block",
        ),
        AdapterLimitation(
            limitation_id="java-inheritance-static-depth",
            category="analysis_depth",
            description="Inheritance and virtual dispatch require JDT or bytecode analysis outside this lexical slice.",
            closure_effect="review",
        ),
        AdapterLimitation(
            limitation_id="java-external-trace-producer",
            category="runtime_trace",
            description="Runtime traces must be supplied by normalized JFR/OpenTelemetry producers.",
            closure_effect="block",
        ),
    )
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
        "javascript": JavaScriptProductionSourceAdapter,
        "rust": RustSourceAdapter,
        "java": JavaSourceAdapter,
    }
    try:
        return adapters[language](project_root=project_root)
    except KeyError as exc:
        raise ValueError(f"unknown production adapter language: {language}") from exc


def _definitions(path: Path, pattern: re.Pattern[str]) -> dict[str, ProductionDefinition]:
    definitions: dict[str, ProductionDefinition] = {}
    for definition in _definition_list(path, pattern):
        definitions[definition.name] = definition
    return definitions


def _definition_list(path: Path, pattern: re.Pattern[str]) -> list[ProductionDefinition]:
    text = path.read_text()
    matches = list(pattern.finditer(text))
    definitions: list[ProductionDefinition] = []
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
        definitions.append(
            ProductionDefinition(
                name=name,
                symbol_type=_symbol_type(match),
                start=start,
                end=next_start,
            )
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
