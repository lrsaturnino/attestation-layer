from __future__ import annotations

import re
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
    # The backend a task is routed to. ``core_smt`` is the propositional/whole-requirement SMT
    # consistency check and ``adapter`` is a source-adapter symbol/claim shape check (the source
    # adapters' own tasks). ``smt-theories`` (z3 Int/Real comparison premises) and ``apalache``
    # (state/temporal obligations via the S ∧ R model check) are the per-premise discharging backends
    # the generic adapter routes to via ``proof_closure.backend_for_proof_node`` — a routed task's
    # named backend is a producer that can actually discharge it. ``cvc5`` is the finite-set theory
    # backend that discharges a CONCRETE set-literal membership (``x is in {A, B}``); the generic v1
    # adapter never emits it, because the v1 grammar admits only the OPAQUE ``value is in value`` form
    # (no set literal), which no wired backend can discharge — such premises carry the ``unsupported``
    # sentinel so the plan shows the premise stays OPEN rather than naming a cvc5 route that would
    # decline 100% of the time. ``cvc5`` remains a valid value because the kind-only router maps
    # ``membership`` -> cvc5 for the v2 dispatch path, where a v3 set-literal membership genuinely
    # discharges on cvc5.
    backend: Literal["core_smt", "adapter", "smt-theories", "cvc5", "apalache", "unsupported"]
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


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _is_checked_proof_hash(value: Any) -> bool:
    """Whether ``value`` is a well-formed content hash of a checked proof artifact.

    A checked-proof reference must be the canonical ``sha256:<64 hex>`` digest the rest of the
    pipeline emits (see ``jsonutil.sha256_json``). A placeholder string such as
    ``"sha256:checked-proof"`` is not a hash of anything and cannot stand in for a proof.
    """
    return isinstance(value, str) and bool(_SHA256_DIGEST.match(value))


def _has_proof_artifact(details: dict[str, Any]) -> bool:
    """Whether ``details`` references a *checked* proof artifact backing a PROVEN_INDUCTIVE claim.

    The honest backing for an inductive-proof claim is a retained, content-addressed proof that a
    checker accepted — not merely the presence of some artifact. So this requires either a
    top-level ``proof_artifact_sha256`` digest, or a ``proof_artifacts`` entry whose ``kind`` is
    ``"checked_proof"`` carrying a well-formed ``sha256``. An arbitrary non-empty list (a theorem
    statement or proof script with no checked result) does not qualify.
    """
    if _is_checked_proof_hash(details.get("proof_artifact_sha256")):
        return True
    artifacts = details.get("proof_artifacts")
    if not isinstance(artifacts, list):
        return False
    return any(
        isinstance(artifact, dict)
        and artifact.get("kind") == "checked_proof"
        and _is_checked_proof_hash(artifact.get("sha256"))
        for artifact in artifacts
    )


def _has_proof_assistant_identity(details: dict[str, Any]) -> bool:
    """Whether ``details`` names the proof assistant that checked a PROVEN_INDUCTIVE claim.

    A checked inductive proof was accepted by a specific proof assistant (a TLAPS obligation, an
    Apalache inductive-invariant check). Recording which one — under ``details['proof_assistant']``
    — is what lets the evidence boundary match the claim to a registered ``proof_assistant``
    producer and what makes "an inductive proof exists" traceable to the checker that accepted it;
    an anonymous proof artifact names no checker and cannot be traced to one.
    """
    assistant = details.get("proof_assistant")
    return isinstance(assistant, str) and bool(assistant.strip())


def _has_proof_check_command(details: dict[str, Any]) -> bool:
    """Whether ``details`` records the command that ran the proof check backing PROVEN_INDUCTIVE.

    The honest backing for a checked proof includes how the proof assistant was invoked, so the
    result is replayable — the same command metadata a BOUNDED_CHECKED claim records under
    ``details['command']``. A non-empty command list or string qualifies.
    """
    command = details.get("command")
    return bool(command) and isinstance(command, (list, str))


def _has_recorded_bounds(details: dict[str, Any]) -> bool:
    """Whether ``details`` records the bounds a BOUNDED_CHECKED claim was checked under."""
    bounds = details.get("bounds")
    return isinstance(bounds, dict) and len(bounds) > 0


def _has_command_metadata(details: dict[str, Any]) -> bool:
    """Whether ``details`` records the checker command a BOUNDED_CHECKED run was produced by."""
    command = details.get("command")
    return bool(command) and isinstance(command, (list, str))


def _recorded_tool_version(details: dict[str, Any]) -> str | None:
    """The version recorded by the run that produced ``details``, top-level or nested.

    A bounded model check is backed only by the version of the checker that actually ran,
    recorded either top-level (``details['tool_version']``) or under the run's reproducibility
    metadata (``details['reproducibility']['tool_version']`` — where the solver-backed S ∧ R
    path records it under ``exclude_none``). A producer's static catalog version does not count;
    only a run-recorded one does (that is the loophole this closes)."""
    direct = details.get("tool_version")
    if isinstance(direct, str) and direct:
        return direct
    repro = details.get("reproducibility")
    if isinstance(repro, dict):
        nested = repro.get("tool_version")
        if isinstance(nested, str) and nested:
            return nested
    return None


def bounded_evidence_backing_complete(details: dict[str, Any]) -> bool:
    """Whether ``details`` carries the full backing a BOUNDED_CHECKED claim requires.

    A bounded model check is honestly BOUNDED_CHECKED only when it records all three of: the
    bounds it searched, the checker command, and the version of the checker recorded from the
    run that produced it. This is the single definition of bounded backing, shared by the
    producers — which self-gate to ``evidence_level=None`` when it is incomplete, so an unbacked
    bounded claim is never emitted — and the proof-closure / evidence-producer layer, which
    refuses an over-claimed bounded result downstream. A stub or version-less run records no
    run version and is therefore not backed."""
    return (
        _has_recorded_bounds(details)
        and _has_command_metadata(details)
        and _recorded_tool_version(details) is not None
    )


def _is_nonempty_str(value: Any) -> bool:
    """Whether ``value`` is a non-empty (non-whitespace) string."""
    return isinstance(value, str) and bool(value.strip())


def _has_trace_mapping(details: dict[str, Any]) -> bool:
    """Whether ``details`` records a non-lossy observed→fragment mapping for a TRACE_VALIDATED claim.

    TRACE_VALIDATED asserts observed runtime behavior was mapped onto the requirement's formal
    fragment. The honest, replayable backing is not merely *some* dict but a stable schema that
    pins down what was read and what it covered, so the verdict can be reconstructed:

    - ``validator_id`` and ``requirement_id`` — which validator ran, against which requirement;
    - ``trace_hash`` and ``trace_source_hash`` — the content and source digests of the exact trace,
      so the observations can be re-fetched and the mapping survives the trace file moving;
    - ``observed_event_ids`` — the concrete events read, by id, not by action string (many events
      can share an action, so an action is not an event identity). The list is empty only for an
      empty trace (a counterexample can be reached observing nothing);
    - ``fragment`` — the covered formal fragment (the obligation the validator discharged).

    A redaction-blocked or unsupported result mapped none of this, and an arbitrary dict satisfies
    none of the schema; either way the claim cannot be constructed.
    """
    mapping = details.get("trace_mapping")
    if not isinstance(mapping, dict):
        return False
    if not _is_nonempty_str(mapping.get("validator_id")):
        return False
    if not _is_nonempty_str(mapping.get("requirement_id")):
        return False
    if not _is_nonempty_str(mapping.get("trace_hash")):
        return False
    if not _is_nonempty_str(mapping.get("trace_source_hash")):
        return False
    event_ids = mapping.get("observed_event_ids")
    if not isinstance(event_ids, list) or not all(_is_nonempty_str(eid) for eid in event_ids):
        return False
    fragment = mapping.get("fragment")
    return isinstance(fragment, dict) and len(fragment) > 0


class BackendResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str
    status: Literal["valid", "invalid", "counterexample", "timeout", "unsupported", "needs_review"]
    evidence_level: EvidenceLevel | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evidence_backing(self) -> BackendResult:
        """Refuse to construct a result whose evidence level outruns its backing metadata.

        A high-assurance level is a claim about *how* a result was obtained, so it cannot be
        constructed without the metadata that backs the claim. Enforcing this at construction
        makes a dishonest result impossible to hold in memory, not merely rejected downstream;
        the proof-closure producer mapping and the evidence-boundary report keep the same checks
        as defense-in-depth. To inject a deliberately-malformed result for those downstream tests,
        bypass validation with ``BackendResult.model_construct(...)``.

        - PROVEN_INDUCTIVE has no real inductive-proof producer yet, so it may not be claimed
          without all of: (a) a ``valid`` status — a proof that did not check is not a proof; (b) a
          checked-proof artifact: a canonical ``proof_artifact_sha256`` digest or a
          ``proof_artifacts`` entry of kind ``checked_proof`` carrying a well-formed ``sha256``;
          (c) the proof assistant that accepted it, in ``details['proof_assistant']``; and (d) the
          proof-check command, in ``details['command']``, so the result is replayable. (The
          *registered*-proof-assistant-producer half of the contract needs the producer registry
          and stays in the evidence boundary as defense-in-depth; construction enforces the
          metadata a producer must carry, the boundary enforces that the producer is real.)
        - BOUNDED_CHECKED is the output of a bounded model check, so it may not be claimed without
          the full backing such a check records: the bounds it searched (a non-empty
          ``details['bounds']``), the checker command (``details['command']``), and a checker
          version recorded from the run (``details['tool_version']``, or where the solver path
          records it, ``details['reproducibility']['tool_version']`` — never a producer's static
          catalog version). This is the single definition of bounded backing,
          ``bounded_evidence_backing_complete``, that the producers self-gate on and the
          proof-closure / evidence-producer layer enforces, so an unbacked bounded claim cannot
          be held in memory, not merely rejected downstream.
        - TRACE_VALIDATED asserts observed behavior was mapped onto a formal fragment, so it may
          not be claimed without a non-lossy mapping under ``details['trace_mapping']``: the
          stable schema of validator id, requirement id, trace content + source hashes, the
          concrete event ids read, and the covered fragment (see ``_has_trace_mapping``).
        """
        if self.evidence_level == EvidenceLevel.PROVEN_INDUCTIVE:
            if self.status != "valid":
                raise ValueError(
                    "BackendResult claiming PROVEN_INDUCTIVE requires a 'valid' status; a proof "
                    f"that did not check (status '{self.status}') is not an inductive proof"
                )
            if not _has_proof_artifact(self.details):
                raise ValueError(
                    "BackendResult claiming PROVEN_INDUCTIVE requires a checked-proof artifact in "
                    "details (a canonical 'proof_artifact_sha256' digest, or a 'proof_artifacts' "
                    "entry of kind 'checked_proof' with a well-formed 'sha256'); no inductive-proof "
                    "producer exists, so the level cannot be emitted without one"
                )
            if not _has_proof_assistant_identity(self.details):
                raise ValueError(
                    "BackendResult claiming PROVEN_INDUCTIVE requires the proof assistant that "
                    "checked the artifact in details['proof_assistant'] (e.g. 'tlaps' or an "
                    "Apalache inductive-invariant check); a checked proof must name the checker "
                    "that accepted it"
                )
            if not _has_proof_check_command(self.details):
                raise ValueError(
                    "BackendResult claiming PROVEN_INDUCTIVE requires the proof-check command in "
                    "details['command']; a checked proof must record how the checker was invoked "
                    "so the result is replayable"
                )
        if (
            self.evidence_level == EvidenceLevel.BOUNDED_CHECKED
            and not bounded_evidence_backing_complete(self.details)
        ):
            missing: list[str] = []
            if not _has_recorded_bounds(self.details):
                missing.append("the bounds it searched (a non-empty details['bounds'])")
            if not _has_command_metadata(self.details):
                missing.append("the checker command (details['command'])")
            if _recorded_tool_version(self.details) is None:
                missing.append(
                    "a checker version recorded from the run (details['tool_version'] or "
                    "details['reproducibility']['tool_version'])"
                )
            raise ValueError(
                "BackendResult claiming BOUNDED_CHECKED requires the full backing a bounded model "
                "check records, missing: "
                + "; ".join(missing)
                + ". A bounded result cannot claim its evidence level without recording what it "
                "searched, how, and with which checker version, so the verdict is reproducible. To "
                "inject a deliberately-unbacked result for downstream-layer tests, bypass "
                "validation with BackendResult.model_construct(...)."
            )
        if (
            self.evidence_level == EvidenceLevel.TRACE_VALIDATED
            and not _has_trace_mapping(self.details)
        ):
            raise ValueError(
                "BackendResult claiming TRACE_VALIDATED requires the observed→fragment mapping it "
                "validated in details['trace_mapping'] — a stable schema recording validator_id, "
                "requirement_id, trace_hash, trace_source_hash, observed_event_ids, and the covered "
                "fragment; a trace result that mapped no observed behavior, or an arbitrary dict, "
                "cannot claim trace-validated evidence"
            )
        return self


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


class NormalizedTraceProducer(BaseModel):
    """Recorded real-tool provenance for a trace the adapter *produced* (not ingested).

    A trace carries a producer iff a real external tool ran to extract it — Foundry for the
    Solidity vertical (PC-4), a real OpenTelemetry/runtime producer for others. ``tool`` is the
    binary that ran and ``tool_version`` is its captured version string; together with the
    enclosing trace's ``source_hash`` (the hash of the real tool artifact the trace was projected
    from) they are the "captured tool version + real artifact hash" the capability gate requires
    before an adapter may certify a ``trace_capable``/``production_candidate`` capability. A trace
    ingested from manifest-declared JSON has ``producer == None`` on its enclosing trace and so can
    never lift a regex/static adapter above ``static_resolution``.

    ``raw_output`` carries the captured raw output of the tool run (the agnostic, opaque artifact
    the trace was projected from) so the capability gate is SOURCE-BOUND rather than shape-bound:
    certification recomputes ``sha256(raw_output)`` and requires it to equal the enclosing trace's
    ``source_hash`` AND that the bytes are a genuine tool artifact (a tool-specific shape check),
    so a producer stamped over ingested JSON — which has no real tool output to carry — cannot fake
    the gate. It stays optional and agnostic; the tool-specific validation lives in the certifier.
    See adapter_certification.trace_has_real_tool_provenance.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str
    tool_version: str
    raw_output: str | None = None


class NormalizedTrace(BaseModel):
    """The frozen, ecosystem-agnostic trace contract Pillar B consumes (a B↔C SP1 contract).

    A NormalizedTrace projects a real execution recording from one ecosystem onto a common,
    call-and-event-level shape. The projection is intentionally LOSSY — it keeps only what a
    requirement's claim can be checked against (ordered call/return/event observations and their
    pre/post state), discarding lower-level detail. The discarded detail differs by ecosystem, so
    the lossy-normalization rules are pinned here as part of the frozen contract:

    EVM (Solidity / Foundry — PC-4):
      - Opcode-level steps (SSTORE/SLOAD/stack/memory) are dropped; a state change is observed at
        call granularity via a read call's decoded return, not by tracing the SSTORE. The fixtures
        order a read → mutating call → read so "event before state change" is answerable from the
        ordered events alone (no opcode replay).
      - Each EVM call frame becomes one TraceEvent (action = decoded selector signature, or the raw
        4-byte selector when no ABI maps it); revert/success is carried in metadata; gas is dropped.
      - Each LOG/event becomes one TraceEvent ordered by its in-call position; topics/data are kept
        raw and the decoded name/params are added when the ABI resolves them, never fabricated.
      - Internal (non-CALL) calls inlined by the compiler are not separate frames; they surface in
        the call graph (PC-3 Slither), not the trace.

    Go (PC-7):
      - The trace is a real runtime/trace captured by `go test -trace` and parsed by the vendored
        golang.org/x/exp/trace reader (nlreq._go_trace_reader). Each user-meaningful, goroutine-
        attributed event becomes one TraceEvent: a runtime/trace task or region becomes an event
        whose action is the task/region type (e.g. "validate"), and a runtime/trace.Log becomes an
        event whose action is the log category, with the message carried in post_state/metadata.
      - Scheduler / GC / sync / metric events are dropped; goroutine scheduling and interleaving are
        linearized to the observed event order. The goroutine id (TraceEvent.metadata["goroutine"])
        and the observed order (TraceEvent.timestamp) are preserved, so the interleaving across
        goroutines survives even though the lower-level scheduling detail does not.
      - Unexported internal frames without runtime/trace instrumentation are not reconstructed; the
        call graph (PC-6 callgraph) is where the static call structure lives, not the trace.

    `producer` records real-tool provenance and is set ONLY when a real tool extracted the trace;
    ingested JSON leaves it None (see NormalizedTraceProducer). `source_hash` is the hash of the
    real tool artifact the trace was projected from — the "real artifact hash" the capability gate
    requires. A vertical fails its DoD if the normalized trace cannot answer the requirement's claim
    — that is the contract these rules exist to keep.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    adapter_id: str
    source_hash: str
    language: str | None = None
    runtime: str | None = None
    events: list[TraceEvent]
    # Recorded real-tool provenance, present only when the adapter extracted this trace by running
    # a real ecosystem tool. None for traces ingested from manifest-declared JSON. The adapter
    # certification suite reads this to decide the achieved capability level: a trace_capable claim
    # is unevidenced (and so blocked) unless extraction yields provenanced traces. See
    # NormalizedTraceProducer and adapter_certification.certify_adapter.
    producer: NormalizedTraceProducer | None = None
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
