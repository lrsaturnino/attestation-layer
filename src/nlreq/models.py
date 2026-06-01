from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


IR_V1_VERSION = "0.1"
IR_V2_VERSION = "0.2"
SUPPORTED_IR_VERSION = IR_V1_VERSION
SUPPORTED_IR_VERSIONS = {IR_V1_VERSION, IR_V2_VERSION}


class EvidenceLevel(str, Enum):
    TYPE_CHECKED = "TYPE_CHECKED"
    CONSISTENCY_CHECKED = "CONSISTENCY_CHECKED"
    STATICALLY_RESOLVED = "STATICALLY_RESOLVED"
    SMT_CHECKED = "SMT_CHECKED"
    TEST_VALIDATED = "TEST_VALIDATED"
    TRACE_VALIDATED = "TRACE_VALIDATED"
    BOUNDED_CHECKED = "BOUNDED_CHECKED"
    PROVEN_INDUCTIVE = "PROVEN_INDUCTIVE"
    REVIEWED = "REVIEWED"


class FinalStatus(str, Enum):
    ACCEPTED_WITH_EVIDENCE = "ACCEPTED_WITH_EVIDENCE"
    ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW = "ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW"
    REFUSED_AMBIGUOUS = "REFUSED_AMBIGUOUS"
    REFUSED_UNBOUND_SYMBOLS = "REFUSED_UNBOUND_SYMBOLS"
    REFUSED_UNSUPPORTED_CLAIM = "REFUSED_UNSUPPORTED_CLAIM"
    REFUSED_FAILED_CHECK = "REFUSED_FAILED_CHECK"
    REFUSED_TIMEOUT = "REFUSED_TIMEOUT"
    NEEDS_SPEC_COVERAGE = "NEEDS_SPEC_COVERAGE"


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def validate_range(self) -> SourceSpan:
        if self.end_char < self.start_char:
            raise ValueError("end_char must be greater than or equal to start_char")
        return self


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "needs_review", "rejected"]
    approved_by: str | None = None
    approved_at: str | None = None
    self_audit: bool = False


class RequirementSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str | None = None
    controlled_text: str
    controlled_text_approval: Approval | None = None


class ValueRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["identifier", "number", "string"]
    value: str | int | float


class Predicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal[
        "eq",
        "neq",
        "authorized",
        "not_authorized",
        "approved",
        "not_approved",
        "gt",
        "lt",
        "gte",
        "lte",
        "in",
    ]
    args: list[ValueRef]
    source_span: SourceSpan


class ExpectedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "rejected",
        "rejected_before",
        "succeed",
        "emit",
        "set",
        "not_change",
        "increase",
        "decrease",
    ]
    target: str | None = None
    value: ValueRef | None = None
    source_span: SourceSpan


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "authorization_precondition",
        "state_precondition",
        "state_postcondition",
        "numeric_invariant",
        "event_state_correspondence",
        "bounded_temporal",
    ]
    action: str
    forall: list[dict[str, str]]
    condition: list[Predicate]
    expected: ExpectedResult


class RequiredEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_path: str
    minimum_level: EvidenceLevel


class SymbolBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: str
    symbol: str
    symbol_type: str
    confidence: Literal["generic_symbol_table", "manual_override", "adapter_resolved", "llm_suggested"]


class BindingsArtifact(RootModel[dict[str, SymbolBinding]]):
    pass


class AssumptionsArtifact(RootModel[list[dict[str, str]]]):
    pass


class RequirementIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ir_version: str = SUPPORTED_IR_VERSION
    requirement_id: str
    title: str
    source: RequirementSource
    claim: Claim
    bindings: dict[str, SymbolBinding] = Field(default_factory=dict)
    assumptions: list[dict[str, str]] = Field(default_factory=list)
    required_evidence: list[RequiredEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ir_version(self) -> RequirementIR:
        if self.ir_version != SUPPORTED_IR_VERSION:
            raise ValueError(f"unsupported ir_version: {self.ir_version}")
        return self


SemanticConfidence = Literal[
    "reviewed",
    "deterministic_parse",
    "adapter_resolved",
    "migration_inferred",
    "llm_suggested",
    "unknown",
]


SemanticDerivationMethod = Literal[
    "deterministic_parse",
    "manual_review",
    "migration",
    "llm_draft",
    "adapter",
    "unknown",
]


SemanticNodeKind = Literal[
    "rule",
    "premise",
    "obligation",
    "action_obligation",
    "forall",
    "exists",
    "entity_scope",
    "module_scope",
    "and",
    "or",
    "not",
    "implies",
    "iff",
    "predicate",
    "comparison",
    "membership",
    "state_ref",
    "action",
    "call",
    "event",
    "transition",
    "pre_state",
    "post_state",
    "invariant",
    "state_delta",
    "always",
    "eventually",
    "until",
    "before",
    "within",
    "eq",
    "neq",
    "lt",
    "lte",
    "gt",
    "gte",
    "increase",
    "decrease",
    "system_spec_ref",
    "code_symbol_ref",
    "trace_ref",
    "policy_ref",
]


class SemanticProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document: str | None = None
    derived_from: list[str] = Field(default_factory=list)
    method: SemanticDerivationMethod
    tool: str | None = None
    tool_version: str | None = None
    model: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TemporalBound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | float
    unit: Literal["second", "minute", "hour", "day", "block"]


class SemanticNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: SemanticNodeKind
    source_spans: list[SourceSpan] = Field(default_factory=list)
    provenance: SemanticProvenance
    confidence: SemanticConfidence
    annotations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    children: list[SemanticNode] = Field(default_factory=list)
    scope: list[SemanticNode] = Field(default_factory=list)
    premise: SemanticNode | None = None
    obligation: SemanticNode | None = None
    action: SemanticNode | None = None
    must: SemanticNode | None = None
    left: SemanticNode | ValueRef | None = None
    right: SemanticNode | ValueRef | None = None
    args: list[ValueRef] = Field(default_factory=list)
    name: str | None = None
    target: str | None = None
    value: ValueRef | None = None
    temporal_bound: TemporalBound | None = None

    @model_validator(mode="after")
    def validate_node_shape(self) -> SemanticNode:
        if self.kind == "rule" and (self.premise is None or self.obligation is None):
            raise ValueError("rule nodes require premise and obligation")
        if self.kind == "action_obligation" and (self.action is None or self.must is None):
            raise ValueError("action_obligation nodes require action and must")
        if self.kind == "not" and len(self.children) != 1:
            raise ValueError("not nodes require exactly one child")
        if self.kind in {"implies", "iff"} and len(self.children) != 2:
            raise ValueError(f"{self.kind} nodes require exactly two children")
        if self.kind in {"forall", "exists", "entity_scope", "module_scope"} and not self.name:
            raise ValueError(f"{self.kind} nodes require name")
        if self.kind == "predicate" and not self.name:
            raise ValueError("predicate nodes require name")
        if self.kind in {
            "state_ref",
            "action",
            "call",
            "event",
            "transition",
            "pre_state",
            "post_state",
            "invariant",
            "state_delta",
            "system_spec_ref",
            "code_symbol_ref",
            "trace_ref",
            "policy_ref",
        } and not (self.name or self.target):
            raise ValueError(f"{self.kind} nodes require name or target")
        if self.kind in {
            "comparison",
            "membership",
            "eq",
            "neq",
            "lt",
            "lte",
            "gt",
            "gte",
            "increase",
            "decrease",
        } and not (len(self.args) >= 2 or (self.left is not None and self.right is not None)):
            raise ValueError(f"{self.kind} nodes require two operands")
        if self.kind == "within" and self.temporal_bound is None:
            raise ValueError("within nodes require temporal_bound")
        return self


class RequirementIRV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ir_version: Literal["0.2"] = IR_V2_VERSION
    requirement_id: str
    title: str
    source: RequirementSource
    semantic_ir: SemanticNode
    bindings: dict[str, SymbolBinding] = Field(default_factory=dict)
    assumptions: list[dict[str, str]] = Field(default_factory=list)
    required_evidence: list[RequiredEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_semantic_root(self) -> RequirementIRV2:
        if self.semantic_ir.kind != "rule":
            raise ValueError("semantic_ir root must be a rule node")
        return self


class MigrationDiffEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    change: Literal["added", "removed", "replaced", "moved", "refused"]
    detail: str


class RequirementIRMigrationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    migration_id: str
    source_ir_version: Literal["0.1"]
    target_ir_version: Literal["0.2"]
    source_ir_hash: str
    target_ir_hash: str
    tool: str
    tool_version: str
    timestamp: str
    diff: list[MigrationDiffEntry]


class SymbolRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expected_type: str | None = None


class Symbol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    symbol_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SymbolResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: SymbolRef
    status: Literal["resolved", "unresolved", "ambiguous"]
    symbols: list[Symbol] = Field(default_factory=list)
    reason: str | None = None


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    reason: str | None = None


class EvidenceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_level: EvidenceLevel
    description: str


class VerificationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    backend: Literal["core_smt", "adapter"]
    description: str
    input_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class VerificationTasksArtifact(RootModel[list[VerificationTask]]):
    pass


class ReviewChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controlled_form_matches_intent: Literal["pass", "fail", "n/a"]
    claim_shape_matches_controlled_form: Literal["pass", "fail", "n/a"]
    source_spans_present: Literal["pass", "fail", "n/a"]
    assumptions_explicit: Literal["pass", "fail", "n/a"]
    bindings_justified: Literal["pass", "fail", "n/a"]
    evidence_level_appropriate: Literal["pass", "fail", "n/a"]
    unsupported_claims_hidden: Literal["pass", "fail", "n/a"]


class ReviewArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    reviewer: str
    decision: Literal["approved", "needs_review", "rejected"]
    self_audit: bool = False
    reviewed_hashes: dict[str, str]
    checklist: ReviewChecklist
    timestamp: str


class BackendResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str
    status: Literal["valid", "invalid", "counterexample", "timeout", "unsupported", "needs_review"]
    evidence_level: EvidenceLevel | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BackendResultsArtifact(RootModel[list[BackendResult]]):
    pass


class Counterexample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterexample_id: str
    backend: str
    claim_id: str | None = None
    description: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: Any | None = None
    actual: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CounterexamplesArtifact(RootModel[list[Counterexample]]):
    pass


class GeneratedTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: str
    requirement_id: str
    backend: str
    task_id: str
    content: str
    content_hash: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    source_hashes: dict[str, str] = Field(default_factory=dict)


class GeneratedTestsArtifact(RootModel[list[GeneratedTest]]):
    pass


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    timestamp: str | int
    actor: str | None = None
    action: str
    pre_state: dict[str, Any] | None = None
    post_state: dict[str, Any] | None = None
    causal_predecessor: str | None = None
    language: str | None = None
    runtime: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    adapter_id: str
    source_hash: str
    language: str | None = None
    runtime: str | None = None
    events: list[TraceEvent]
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedTraceArtifact(RootModel[list[NormalizedTrace]]):
    pass


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    required_evidence: EvidenceLevel
    achieved_evidence: EvidenceLevel | None = None
    backend_results: list[BackendResult] = Field(default_factory=list)


class EvidenceObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    ir_hash: str | None = None
    claims: list[EvidenceClaim] = Field(default_factory=list)
    ambiguous: bool = False
    ambiguous_symbols: list[str] = Field(default_factory=list)
    ambiguous_symbol_spans: dict[str, SourceSpan] = Field(default_factory=dict)
    unbound_symbols: list[str] = Field(default_factory=list)
    unbound_symbol_spans: dict[str, SourceSpan] = Field(default_factory=dict)
    unsupported_claims: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    timeouts: list[str] = Field(default_factory=list)
    needs_spec_coverage: bool = False
    pending_reviews: list[str] = Field(default_factory=list)


class StatusDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FinalStatus
    reason: str
    next_actions: list[str] = Field(default_factory=list)
    source_span: SourceSpan | None = None
