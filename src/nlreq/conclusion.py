from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CONCLUSION_SCHEMA_VERSION = "0.1"
CONCLUSION_PHASE_MIN = 46
CONCLUSION_PHASE_MAX = 82


GapType = Literal["architecture", "implementation", "research", "product", "benchmark", "adoption"]
GapStatus = Literal["implemented", "planned", "blocked", "deferred"]


class ReleaseBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["alpha", "beta", "conclusion"]
    minimum_capabilities: list[str]
    allowed_evidence_labels: list[str]
    forbidden_claims: list[str] = Field(default_factory=list)


class GapChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    capability: str
    gap_type: GapType
    status: GapStatus
    owner_phase: int
    required_adr: str
    deliverables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_phase_and_adr(self) -> GapChecklistItem:
        if not CONCLUSION_PHASE_MIN <= self.owner_phase <= CONCLUSION_PHASE_MAX:
            raise ValueError("owner_phase must reference a conclusion roadmap phase")
        expected = 55 + (self.owner_phase - 46)
        if self.required_adr != f"ADR {expected:04d}":
            raise ValueError("required_adr does not match roadmap phase numbering")
        return self


class ConclusionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CONCLUSION_SCHEMA_VERSION
    definition_id: str
    target_statement: str
    release_bars: list[ReleaseBar]
    evidence_label_policy: dict[str, str]


class ConclusionGapChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CONCLUSION_SCHEMA_VERSION
    roadmap: str
    phase_min: int = CONCLUSION_PHASE_MIN
    phase_max: int = CONCLUSION_PHASE_MAX
    items: list[GapChecklistItem]

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> ConclusionGapChecklist:
        ids = [item.capability_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("capability ids must be unique")
        return self


class ConclusionGapCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = CONCLUSION_SCHEMA_VERSION
    result: Literal["passed", "failed"]
    total_items: int
    implemented_items: int
    unknown_phase_references: list[str] = Field(default_factory=list)
    numbering_errors: list[str] = Field(default_factory=list)
    missing_owner_phases: list[int] = Field(default_factory=list)


def build_default_conclusion_definition() -> ConclusionDefinition:
    return ConclusionDefinition(
        definition_id="nl-attestation-conclusion-v1",
        target_statement=(
            "Human requirements must become approved controlled requirements, checked IR, "
            "self-consistent claims, system-compatible formal artifacts, grounded code and "
            "trace evidence, and a closed proof object before downstream action is allowed."
        ),
        release_bars=[
            ReleaseBar(
                name="alpha",
                minimum_capabilities=["approved_controlled_intake", "deterministic_ir", "explicit_refusal"],
                allowed_evidence_labels=["TYPE_CHECKED", "STATICALLY_RESOLVED", "REVIEWED", "BOUNDED_CHECKED"],
                forbidden_claims=["unbounded proof", "silent semantic rewrite"],
            ),
            ReleaseBar(
                name="beta",
                minimum_capabilities=["formal_backend_execution", "system_consistency", "trace_grounding"],
                allowed_evidence_labels=[
                    "TYPE_CHECKED",
                    "STATICALLY_RESOLVED",
                    "REVIEWED",
                    "TRACE_VALIDATED",
                    "BOUNDED_CHECKED",
                ],
                forbidden_claims=["PROVEN_INDUCTIVE without proof-producing backend"],
            ),
            ReleaseBar(
                name="conclusion",
                minimum_capabilities=["cross_language_closure", "signed_retained_evidence", "public_benchmark_accountability"],
                allowed_evidence_labels=[
                    "TYPE_CHECKED",
                    "CONSISTENCY_CHECKED",
                    "STATICALLY_RESOLVED",
                    "SMT_CHECKED",
                    "TEST_VALIDATED",
                    "TRACE_VALIDATED",
                    "BOUNDED_CHECKED",
                    "PROVEN_INDUCTIVE",
                    "REVIEWED",
                ],
                forbidden_claims=["full NL correctness", "full program correctness"],
            ),
        ],
        evidence_label_policy={
            "BOUNDED_CHECKED": "May describe bounded model checking only with recorded bounds.",
            "PROVEN_INDUCTIVE": "May be emitted only by a registered proof-producing backend.",
            "TRACE_VALIDATED": "May describe observed runtime traces, not theorem-level proof.",
            "REVIEWED": "Requires hash-bound human approval.",
        },
    )


def build_default_gap_checklist() -> ConclusionGapChecklist:
    items = [
        ("G46", "Conclusion definition and release bar discipline", "architecture", "implemented", 46, ["docs/conclusion-definition.md", "docs/conclusion-gap-audit.md"]),
        ("G47", "Approved free-form intake and controlled rewrite", "product", "implemented", 47, ["schemas/free-form-intake.schema.json", "schemas/controlled-rewrite-proposal.schema.json"]),
        ("G48", "Controlled requirement DSL v3", "implementation", "implemented", 48, ["src/nlreq/dsl_v3.py", "src/nlreq/dsl_v3.lark"]),
        ("G49", "Hash-bound requirement review workflow", "product", "implemented", 49, ["schemas/approval-workflow.schema.json"]),
        ("G50", "Product refusal surface", "product", "implemented", 50, ["schemas/product-refusal-report.schema.json"]),
        ("G51", "Multi-pass translator workbench", "implementation", "implemented", 51, ["schemas/translator-run.schema.json"]),
        ("G52", "Bidirectional provenance and clarification", "implementation", "implemented", 52, ["schemas/provenance-graph.schema.json"]),
        ("G53", "Logical translator agreement", "implementation", "implemented", 53, ["schemas/logical-translation-agreement-report.schema.json"]),
        ("G54", "Contradiction taxonomy", "implementation", "implemented", 54, ["docs/contradiction-taxonomy.md"]),
        ("G55", "Requirement translation corpus", "benchmark", "implemented", 55, ["benchmarks/requirements-translation/corpus.json"]),
        ("G56", "Apalache production backend", "implementation", "implemented", 56, ["src/nlreq/formal_backend.py", "docs/phase-56-apalache-backend-production-integration.md"]),
        ("G57", "TLC production backend", "implementation", "implemented", 57, ["src/nlreq/formal_backend.py", "docs/phase-57-tlc-backend-production-integration.md"]),
        ("G58", "TLA projection semantics", "implementation", "implemented", 58, ["src/nlreq/tla_projection.py"]),
        ("G59", "Counterexample normalization", "implementation", "implemented", 59, ["src/nlreq/counterexample_normalization.py"]),
        ("G60", "Real S and R composition report", "implementation", "implemented", 60, ["src/nlreq/system_composition.py"]),
        ("G61", "Proof-level evidence boundary", "architecture", "implemented", 61, ["src/nlreq/evidence_boundary.py"]),
        ("G62", "Specula-style extraction runner", "implementation", "implemented", 62, ["src/nlreq/spec_extraction.py"]),
        ("G63", "Code-to-spec manifest", "implementation", "implemented", 63, ["src/nlreq/spec_drift.py"]),
        ("G64", "Spec freshness lockfile", "implementation", "implemented", 64, ["src/nlreq/spec_freshness.py"]),
        ("G65", "Runtime trace extraction SDK", "implementation", "implemented", 65, ["src/nlreq/runtime_trace_sdk.py"]),
        ("G66", "Trace normalization", "implementation", "implemented", 66, ["src/nlreq/trace_normalization.py"]),
        ("G67", "Solidity adapter", "implementation", "implemented", 67, ["src/nlreq/production_source_adapters.py"]),
        ("G68", "Go adapter", "implementation", "implemented", 68, ["src/nlreq/production_source_adapters.py"]),
        ("G69", "TypeScript adapter", "implementation", "implemented", 69, ["src/nlreq/production_source_adapters.py"]),
        ("G70", "Rust or Java adapter", "implementation", "implemented", 70, ["src/nlreq/production_source_adapters.py"]),
        ("G71", "Adapter certification suite", "implementation", "implemented", 71, ["src/nlreq/adapter_certification.py"]),
        ("G72", "Cross-language proof object", "implementation", "implemented", 72, ["src/nlreq/cross_language.py"]),
        ("G73", "Evidence artifact store", "implementation", "implemented", 73, ["src/nlreq/artifact_store.py"]),
        ("G74", "Signed evidence and producer attestation", "implementation", "implemented", 74, ["src/nlreq/signed_evidence.py"]),
        ("G75", "CI and PR action gate", "adoption", "implemented", 75, ["src/nlreq/ci_pr_gate.py"]),
        ("G76", "Benchmark evaluation", "benchmark", "implemented", 76, ["src/nlreq/benchmark_reporting.py"]),
        ("G77", "Performance and caching", "implementation", "implemented", 77, ["src/nlreq/verification_cache.py"]),
        ("G78", "Policy and waiver governance", "product", "implemented", 78, ["src/nlreq/policy_governance.py"]),
        ("G79", "Threat model and TCB audit", "architecture", "implemented", 79, ["src/nlreq/threat_model.py"]),
        ("G80", "Reference brownfield demo", "adoption", "implemented", 80, ["src/nlreq/reference_demo.py"]),
        ("G81", "Public documentation and SDK", "adoption", "implemented", 81, ["src/nlreq/public_sdk.py"]),
        ("G82", "Conclusion release certification", "product", "implemented", 82, ["src/nlreq/conclusion_certification.py"]),
    ]
    return ConclusionGapChecklist(
        roadmap="docs/nl-attestation-conclusion-roadmap.md",
        items=[
            GapChecklistItem(
                capability_id=capability_id,
                capability=capability,
                gap_type=gap_type,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                owner_phase=phase,
                required_adr=f"ADR {55 + (phase - 46):04d}",
                deliverables=deliverables,
            )
            for capability_id, capability, gap_type, status, phase, deliverables in items
        ],
    )


def check_gap_checklist(checklist: ConclusionGapChecklist) -> ConclusionGapCheckReport:
    unknown_phase_refs = [
        item.capability_id
        for item in checklist.items
        if not checklist.phase_min <= item.owner_phase <= checklist.phase_max
    ]
    numbering_errors = []
    for item in checklist.items:
        expected = f"ADR {55 + (item.owner_phase - 46):04d}"
        if item.required_adr != expected:
            numbering_errors.append(f"{item.capability_id}: expected {expected}, got {item.required_adr}")
    missing_owner_phases = [
        phase
        for phase in range(checklist.phase_min, checklist.phase_max + 1)
        if phase not in {item.owner_phase for item in checklist.items}
    ]
    failed = bool(unknown_phase_refs or numbering_errors or missing_owner_phases)
    return ConclusionGapCheckReport(
        result="failed" if failed else "passed",
        total_items=len(checklist.items),
        implemented_items=sum(1 for item in checklist.items if item.status == "implemented"),
        unknown_phase_references=unknown_phase_refs,
        numbering_errors=numbering_errors,
        missing_owner_phases=missing_owner_phases,
    )
