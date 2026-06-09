from __future__ import annotations

from dataclasses import dataclass

from .adapter_certification import count_provenanced_traces, trace_evidence_violations
from .jsonutil import canonical_json
from .models import NormalizedTraceArtifact, SymbolRef
from .source_adapter import (
    AdapterCapabilityContract,
    CodePresentation,
    SourceBinding,
    SourceCallGraph,
    SourceLanguageAdapter,
    SourceManifest,
    SourceSymbolResolution,
)


@dataclass(frozen=True)
class SourceAdapterConformanceFixture:
    manifest: SourceManifest
    resolved_ref: SymbolRef
    unresolved_ref: SymbolRef
    ambiguous_ref: SymbolRef


@dataclass(frozen=True)
class SourceAdapterConformanceReport:
    adapter_id: str
    language: str
    checks: tuple[str, ...]


class SourceAdapterConformanceError(AssertionError):
    pass


def assert_source_adapter_conforms(
    adapter: SourceLanguageAdapter,
    fixture: SourceAdapterConformanceFixture,
) -> SourceAdapterConformanceReport:
    failures = run_source_adapter_conformance(adapter, fixture)
    if failures:
        joined = "\n".join(f"- {failure}" for failure in failures)
        raise SourceAdapterConformanceError(f"Source adapter conformance failed:\n{joined}")
    return SourceAdapterConformanceReport(
        adapter_id=adapter.adapter_id,
        language=adapter.language,
        checks=(
            "interface_methods",
            "stable_resolution",
            "resolution_statuses",
            "call_graph",
            "binding_validation",
            "code_presentation",
            "trace_extraction",
            "trace_capability_honesty",
        ),
    )


def run_source_adapter_conformance(
    adapter: SourceLanguageAdapter,
    fixture: SourceAdapterConformanceFixture,
) -> list[str]:
    failures: list[str] = []
    failures.extend(_check_interface(adapter))
    if fixture.manifest.adapter != adapter.adapter_id:
        failures.append("fixture manifest adapter must match adapter_id")
    if fixture.manifest.language != adapter.language:
        failures.append("fixture manifest language must match adapter language")

    refs = [fixture.resolved_ref, fixture.unresolved_ref, fixture.ambiguous_ref]
    first = [_safe_resolve(adapter, ref, fixture.manifest, failures) for ref in refs]
    second = [_safe_resolve(adapter, ref, fixture.manifest, failures) for ref in refs]
    if any(result is None for result in first + second):
        return failures
    if canonical_json(first) != canonical_json(second):
        failures.append("resolve_symbol must return byte-stable results")

    resolved, unresolved, ambiguous = first
    if not resolved or resolved.status != "resolved" or not resolved.symbols:
        failures.append(f"{fixture.resolved_ref.name} must resolve to at least one symbol")
    if not unresolved or unresolved.status != "unresolved":
        failures.append(f"{fixture.unresolved_ref.name} must be unresolved")
    if not ambiguous or ambiguous.status != "ambiguous" or len(ambiguous.symbols) < 2:
        failures.append(f"{fixture.ambiguous_ref.name} must be ambiguous")

    graph = _safe_call_graph(adapter, fixture.manifest, failures)
    if graph is not None and not set(graph.modules).issuperset(
        {module.module_id for module in fixture.manifest.modules}
    ):
        failures.append("call_graph must include manifest modules")

    if resolved and resolved.symbols:
        binding = SourceBinding(adapter_id=adapter.adapter_id, symbol=resolved.symbols[0])
        validation = adapter.validate_binding(binding)
        if not validation.valid:
            failures.append(f"validate_binding rejected resolved symbol: {validation.reason}")
        mismatch = adapter.validate_binding(
            SourceBinding(adapter_id="wrong-adapter", symbol=resolved.symbols[0])
        )
        if mismatch.valid:
            failures.append("validate_binding must reject adapter mismatches")

    presentation = adapter.present_to_llm([fixture.resolved_ref], fixture.manifest)
    if not isinstance(presentation, CodePresentation) or not presentation.snippets:
        failures.append("present_to_llm must return at least one snippet for resolved refs")

    traces = adapter.extract_traces(fixture.manifest)
    if not isinstance(traces, NormalizedTraceArtifact):
        failures.append("extract_traces must return a NormalizedTraceArtifact")
    else:
        # PC-1: the conformance suite enforces the same trace-evidence honesty rule certification
        # does — an adapter may not advertise a trace_capable/production_candidate level it did not
        # back by producing traces with recorded real-tool provenance. Routing through the shared
        # check means a static adapter that over-claims fails conformance, not only certification.
        # Adapters that expose no v2 capability contract (e.g. the manifest-only baselines) declare
        # no trace level, so there is nothing to over-claim and the gate simply does not apply.
        try:
            contract = adapter.capability_contract()
        except Exception:  # an adapter that cannot describe a contract declares no trace level
            contract = None
        if isinstance(contract, AdapterCapabilityContract):
            provenanced = count_provenanced_traces(traces.root)
            for _subject, message in trace_evidence_violations(contract, provenanced):
                failures.append(
                    f"trace capability over-claimed without real-tool evidence: {message}"
                )

    return failures


def _check_interface(adapter: SourceLanguageAdapter) -> list[str]:
    failures: list[str] = []
    for attr in ("adapter_id", "language"):
        value = getattr(adapter, attr, None)
        if not isinstance(value, str) or not value:
            failures.append(f"{attr} must be a non-empty string")
    for method in (
        "resolve_symbol",
        "call_graph",
        "validate_binding",
        "present_to_llm",
        "extract_traces",
        "parse_manifest",
    ):
        if not callable(getattr(adapter, method, None)):
            failures.append(f"{method} must be callable")
    return failures


def _safe_resolve(
    adapter: SourceLanguageAdapter,
    ref: SymbolRef,
    manifest: SourceManifest,
    failures: list[str],
) -> SourceSymbolResolution | None:
    try:
        result = adapter.resolve_symbol(ref, manifest)
    except Exception as exc:  # pragma: no cover - defensive conformance boundary
        failures.append(f"resolve_symbol raised {type(exc).__name__}: {exc}")
        return None
    if not isinstance(result, SourceSymbolResolution):
        failures.append("resolve_symbol must return SourceSymbolResolution")
        return None
    return result


def _safe_call_graph(
    adapter: SourceLanguageAdapter,
    manifest: SourceManifest,
    failures: list[str],
) -> SourceCallGraph | None:
    try:
        graph = adapter.call_graph(manifest)
    except Exception as exc:  # pragma: no cover - defensive conformance boundary
        failures.append(f"call_graph raised {type(exc).__name__}: {exc}")
        return None
    if not isinstance(graph, SourceCallGraph):
        failures.append("call_graph must return SourceCallGraph")
        return None
    return graph
