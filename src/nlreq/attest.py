"""Zone 3 — the ``attest-spec`` orchestrator as an artifact graph (three-zone scope §7).

Zone 3 is NOT a short chain into S&R: ``s-and-r-composition`` requires ``--requirement-ir`` (v0.2),
``--lowered``, ``--registry``, ``--impact``, ``--system-consistency`` (all required) and rejects
non-IR-v0.2 input, while the project default IR version is 0.1. The real graph per rule is:
partition → draft → route (machine-pin or human) → IR v0.2 → lower → impact → coverage gate →
system-consistency → S&R → set-consistency. This module orchestrates that graph and emits a
single consolidated human queue containing ONLY the flagged-hard items (ambiguous/clarify rules,
ensemble/boundary disagreements, set contradictions, S&R counterexamples / unsupported, needs-
coverage modules), each with its reason. A CLEAN machine-pinned rule (no downstream blocker) is
listed with its pinning provenance and requires no attention; a pin a downstream blocker pertains to
is RECONCILED to ``attention_required`` and ALSO listed in the human queue (HELPER iter-2 #2/#3), so
the report never presents a candidate with an unresolved downstream blocker as a clean pin.

This module is the PRODUCTION WIRING of the ``machine_agreement`` trust state (scope §5):
``attest-spec`` loads the opt-in ``MachinePinPolicy`` (``--machine-pin-policy`` /
``NLREQ_MACHINE_PIN``) and calls ``route_machine_pinning`` with REAL routing input derived from a
real candidate — partition boundary flags, the PARTITION-ensemble diversity (≥2 distinct provider
families, derived from the real partition artifact so a deterministic / single-provider partition
can never auto-advance — scope §4), the drafting-ensemble agreement, per-member audit verdicts (the
agreed draft parses), the deterministic-shape pass (the REAL
``deterministic_shape_for_controlled_text`` the CLI supplies — HELPER iter-3 #1, not a test-injected
check), achieved evidence levels, the calibration-derived threshold, AND the load-bearing
changed-path admission gate (HELPER iter-3 #3) — so the router is not just a unit-tested helper.
With the policy OFF (the default), every rule routes to the human queue and no pin is emitted (AC1).

Downstream honesty (scope §7 steps 3-9; HELPER iter-3 #2): the orchestrator DETERMINISTICALLY
produces IR v0.2 (parse v0.1 → migrate) + the lowered TLA artifact + ``requirement-set-
consistency`` over the IR-v0.2 set for every agreed candidate (always emitted), and runs the
spec-coverage gate when the operator supplies ``--registry`` + ``--impact`` (needs-coverage modules
queue for specula-extract) and the S ∧ R composition PER CANDIDATE when the operator supplies
``--registry`` + ``--impact`` (each candidate is one requirement, run against the shared registry +
impact, so a multi-rule spec never leaves an agreed candidate's S&R stage skipped — HELPER iter-3
followup #2; a counterexample / unsupported routes to the human queue and reverts its pin). External
artifacts the orchestrator cannot produce (impact / registry) are recorded as EXPLICIT prerequisites
in the report — never faked as a pass (scope §7 step 6 honesty: a coverage gap is never a pass).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .coverage_alignment import SpecCoverageGateReport
from .impact import ImpactAnalysisArtifact
from .machine_agreement import (
    MachinePinPolicy,
    MachineRoutingDecision,
    MachineRoutingInput,
    route_machine_pinning,
)
from .models import (
    EnsembleAgreementResult,
    EnsembleAuditVerdict,
    EnsembleMember,
    EvidenceLevel,
    PinningProvenance,
    RequirementIRV2,
)
from .spec_partition import SpecPartitionArtifact
from .system_checker import RequirementSetConsistencyReport, SystemConsistencyResult
from .system_composition import SandRCompositionReport
from .translator import LoweredFormalArtifact


__all__ = [
    "AttestQueueStage",
    "AttestHumanQueueItem",
    "AttestMachinePin",
    "AttestDownstreamStage",
    "AttestRuleDownstream",
    "AttestSetConsistency",
    "AttestCoverageGate",
    "AttestPrerequisite",
    "AttestSpecReport",
    "deterministic_shape_for_controlled_text",
    "deterministic_decomposition_audit_for_controlled_text",
    "attest_spec_document",
]


AttestQueueStage = Literal[
    "partition",
    "drafting",
    "routing",
    "needs_downstream_artifacts",
    "set_consistency",
    "needs_coverage",
    "s_and_r",
    # A machine pin REVERTED to human attention by a downstream blocker that does not already
    # carry a candidate-keyed queue item of its own (HELPER iter-2 #2/#3). Used when reconciling
    # ``machine_pinned`` against the downstream graph: a pinned candidate whose change has a
    # coverage gap (queued module-keyed, not candidate-keyed) is listed here so every
    # ``attention_required`` pin is also surfaced in the actionable human queue.
    "downstream_blocker",
]


class AttestHumanQueueItem(BaseModel):
    """One item in the consolidated human queue, each carrying its reason(s) and stage.

    The consolidated queue contains ONLY flagged-hard items (scope §7 step 10): a candidate the
    partitioner/drafter could not state (clarify), an ensemble/boundary disagreement, an unmet
    machine-pin signal, or a rule needing downstream artifacts. Each item states WHY it is queued
    and at WHICH stage, so a human can triage in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_index: int
    candidate_text: str
    stage: AttestQueueStage
    reasons: list[str] = Field(default_factory=list)


class AttestMachinePin(BaseModel):
    """A candidate rule the orchestrator machine-pinned (auto-advanced past human approval).

    Carries the agreed controlled text and the ``machine_agreement`` ``PinningProvenance`` the
    router emitted (members, resolved model ids, provider families, agreement, audit verdicts,
    policy hash). A human MAY later promote it to ``human_review`` (promotion is upward only).

    ``attention_required`` reconciles the pin against the downstream graph (HELPER iter-2 #2/#3):
    a pin records that the ensemble agreed on the rule's MEANING, but a downstream check
    (requirement-set contradiction, a coverage gap on the change, or an S ∧ R result that disproved
    OR could-not-validate the rule) means the SAME candidate ALSO needs human attention. A pin with
    ``attention_required=True`` carries its blocker reason(s) in ``attention_reasons`` AND appears in
    the consolidated ``human_queue`` — so the report never presents a candidate with an unresolved
    downstream blocker as a clean, no-attention machine pin (scope §7 step 10). A pin with
    ``attention_required=False`` passed every downstream check that RAN and requires no attention to
    establish its pinned meaning (the operator's optional next downstream step, when external impact/
    registry were not supplied, is recorded separately in the report's ``prerequisites``).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_index: int
    candidate_text: str
    controlled_text: str
    pinning: PinningProvenance
    # Set True by the post-graph reconciliation when a downstream blocker pertains to this
    # candidate (HELPER iter-2 #2/#3); the pin is then ALSO listed in ``human_queue``.
    attention_required: bool = False
    # The downstream blocker reason(s) that flagged this pin (empty when attention_required is False).
    attention_reasons: list[str] = Field(default_factory=list)


class AttestDownstreamStage(Enum):
    """The downstream-graph stage recorded per agreed candidate (Zone 3 §7 steps 3-9)."""

    # The candidate's controlled text parsed + migrated to IR v0.2 (deterministic, always).
    ir_v2_produced = "ir_v2_produced"
    # The coverage gate found an unspec'd module (needs registry+impact; queues specula-extract).
    needs_coverage = "needs_coverage"
    # The candidate could not be carried further downstream (its controlled text did not parse /
    # migrate to IR v0.2, so it is unreachable); recorded INFORMATIONALLY — the candidate is already
    # in the human queue from routing (a shape failure), never double-listed here.
    needs_downstream_artifacts = "needs_downstream_artifacts"
    # S&R DISPROVED this candidate (a counterexample / invalid / timeout under the reviewed system
    # specs). Note ``unsupported`` does NOT set this stage — it is "could not be validated" (the
    # migration-shape limitation), recorded via ``s_and_r_result`` + the human queue, not a disproof.
    s_and_r_blocked = "s_and_r_blocked"


class AttestRuleDownstream(BaseModel):
    """Per-rule downstream-graph result (Zone 3 §7 steps 3-9), one per agreed candidate.

    Records what the orchestrator PRODUCED (IR v0.2 + the lowered artifact — deterministic, always)
    and what it RAN when the operator supplied the external artifacts (coverage, S&R). A downstream
    blocker — a set contradiction/unchecked, a coverage gap, an S&R DISPROOF (counterexample /
    invalid / timeout), or an S&R that COULD-NOT-VALIDATE (``unsupported``) — is surfaced in the
    human queue with its reason AND reverts any machine pin on that candidate to attention_required
    (HELPER iter-2 #2/#3). A ``needs_downstream_artifacts`` stage (external artifacts not supplied)
    is recorded here INFORMATIONALLY — the operator's next step is the dedicated commands, not a
    queue item, so the human queue stays focused on actionable blockers (HELPER iter-3 #2).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_index: int
    requirement_id: str
    # The IR v0.2 content hash (None when the controlled text did not parse — recorded so a human
    # can see the candidate was unreachable downstream).
    ir_v2_hash: str | None = None
    ir_v2_produced: bool = False
    # The lowering status: ``lowered`` / ``refused`` (the v0.1→v0.2 migration produces a generic
    # obligation tree whose shape the live lowerer does not accept for these classes, so lowering
    # typically REFUSES — honest, surfaced here AND in the embedded ``lowered`` artifact) / None
    # (not attempted: no controlled text). Produced by the orchestrator via ``lower_ir_v2_to_tla``.
    lowered_status: str | None = None
    # The S&R composition result for THIS candidate, when registry + impact were supplied; None when
    # S&R did not run (registry/impact absent — see the report's ``prerequisites``).
    s_and_r_result: str | None = None
    # The ACTUAL graph artifacts the orchestrator PRODUCED for this candidate (HELPER iter-1 #1: the
    # report embeds the real objects, not only hashes/status). ``ir_v2`` is the migrated IR v0.2;
    # ``lowered`` is the lowered TLA artifact (carrying its refusal diagnostics when refused);
    # ``system_consistency`` is the orchestrator-PRODUCED S∧R consistency result (registry+impact
    # supplied) — never caller-supplied (HELPER iter-1 #2); ``s_and_r`` is the full composition
    # report. The CLI fans each non-None artifact out to ``--out-dir`` as a standalone file the
    # dedicated commands can consume. All None when not produced (no controlled text / inputs absent).
    ir_v2: RequirementIRV2 | None = None
    lowered: LoweredFormalArtifact | None = None
    system_consistency: SystemConsistencyResult | None = None
    s_and_r: SandRCompositionReport | None = None
    stage: AttestDownstreamStage


class AttestSetConsistency(BaseModel):
    """The ``requirement-set-consistency`` result over the IR-v0.2 set (deterministic, always run).

    Run over every candidate's IR v0.2 via ``check_requirement_set_consistency`` (no external
    inputs). A ``contradiction`` or ``unsupported`` result routes the contradicting/unchecked
    candidates to the human queue with their reason (scope §7 step 9).
    """

    model_config = ConfigDict(extra="forbid")

    result: str
    contradiction_count: int = 0
    unchecked_count: int = 0
    # The candidate indices each contradiction/unchecked entry involves (for queue routing).
    contradicted_candidates: list[int] = Field(default_factory=list)
    unchecked_candidates: list[int] = Field(default_factory=list)


class AttestCoverageGate(BaseModel):
    """The document-wide spec-coverage gate (Zone 3 §7 step 6), run when registry + impact supplied.

    Modules with no registered system spec ``S`` route to a ``needs_coverage`` human-queue bucket
    (queued for ``specula-extract``) and are NEVER reported as passing (scope §7 step 6 honesty).
    """

    model_config = ConfigDict(extra="forbid")

    result: str
    unspecified_modules: list[str] = Field(default_factory=list)


class AttestPrerequisite(BaseModel):
    """An external graph artifact the orchestrator cannot produce from the document alone.

    Zone 3's impact analysis (scope §7 step 5) is per-source: it maps a requirement's symbols to
    affected modules through the real call graph, so it needs the SOURCE TREE (a manifest), not just
    the spec document. The reviewed system-spec registry (step 6) is likewise an external input.
    When either is absent the orchestrator records an EXPLICIT, ACTIONABLE prerequisite here — the
    artifact name, why it cannot be produced, and the exact dedicated command that produces it
    (HELPER iter-1 #2: an explicitly-named prerequisite, NOT a vague ``needs_downstream_artifacts``
    note). The operator runs the named command, then re-runs ``attest-spec`` with the artifact so
    the orchestrator produces the rest of the graph (coverage gate, system-consistency, S&R).
    """

    model_config = ConfigDict(extra="forbid")

    artifact: str
    reason: str
    command: str


class AttestSpecReport(BaseModel):
    """The consolidated ``attest-spec`` report (scope §7 step 10).

    ``machine_pinned`` lists the rules auto-advanced under the machine-pin policy (with their
    pinning provenance); ``human_queue`` lists ONLY the flagged-hard items (clarify / disagreement
    / unmet machine-pin signal / set contradiction / S&R counterexample / needs-coverage module),
    each with its reason and stage; ``downstream`` records the per-rule IR-v0.2 + lowered + S&R
    results the orchestrator PRODUCED or RAN (Zone 3 §7 steps 3-9), each EMBEDDING the real artifact
    objects (``ir_v2`` / ``lowered`` / ``system_consistency`` / ``s_and_r``), not only hashes
    (HELPER iter-1 #1). ``set_consistency`` / ``coverage_gate`` are queue-routing summaries;
    ``partition`` / ``set_consistency_report`` / ``coverage_report`` embed the FULL artifacts so the
    report carries the whole graph. ``prerequisites`` names the external artifacts (impact /
    registry) the orchestrator could not produce, each with the command to produce it (HELPER
    iter-1 #2). ``policy_off`` is True when machine pinning is disabled (every rule queued — AC1).
    """

    model_config = ConfigDict(extra="forbid")

    document_hash: str
    policy_id: str | None
    policy_off: bool
    total_candidates: int
    # The FULL Zone 1 partition manifest (embedded, not just its hash) — the completeness oracle.
    partition: SpecPartitionArtifact
    # The source-impact artifact the orchestrator USED for the coverage gate + S ∧ R (Zone 3 §7
    # step 5; HELPER iter-2 #1). ``attest-spec`` PRODUCES it from the supplied source manifest +
    # changed symbols (``impact_provenance == "produced"``) — the impact producer the dedicated
    # ``python-source-impact`` command runs — or replays an operator-supplied ``--impact`` artifact
    # (``impact_provenance == "supplied"``). Embedded so the report carries the impact it actually
    # ran the graph against, and fanned out to ``--out-dir`` as a standalone, replayable file. None
    # when neither a manifest nor an ``--impact`` artifact was supplied (then ``impact`` is an
    # explicit prerequisite).
    impact: ImpactAnalysisArtifact | None = None
    impact_provenance: Literal["produced", "supplied"] | None = None
    machine_pinned: list[AttestMachinePin] = Field(default_factory=list)
    human_queue: list[AttestHumanQueueItem] = Field(default_factory=list)
    downstream: list[AttestRuleDownstream] = Field(default_factory=list)
    set_consistency: AttestSetConsistency | None = None
    coverage_gate: AttestCoverageGate | None = None
    # The FULL downstream artifacts (embedded, not only summaries; HELPER iter-1 #1).
    set_consistency_report: RequirementSetConsistencyReport | None = None
    coverage_report: SpecCoverageGateReport | None = None
    # External artifacts the orchestrator could not produce, each named with its command (HELPER
    # iter-1 #2: explicit prerequisites, not a silent informational note).
    prerequisites: list[AttestPrerequisite] = Field(default_factory=list)
    # Honest, evergreen limitations of the produced graph (e.g. the migration-shape constraint that
    # makes the migrated IR's lowering refuse, so S∧R cannot validate through attest-spec alone).
    limitations: list[str] = Field(default_factory=list)


def _ensemble_members_from_provenance(
    drafting_member_provenance: list[dict[str, str]],
) -> list[EnsembleMember]:
    """Build the ``EnsembleMember`` set for routing from the drafting-ensemble provenance.

    Each drafting member's ``provider_family`` and ``resolved_model`` (from the factory's
    ``RoleProvenance``) become an ``EnsembleMember``; ``member_id`` is the resolved model id (unique
    per member). A member whose family is blank is rejected by ``EnsembleMember``'s non-blank guard.
    """
    members: list[EnsembleMember] = []
    for index, provenance in enumerate(drafting_member_provenance):
        family = provenance.get("provider_family")
        resolved = provenance.get("resolved_model") or f"drafting-member-{index}"
        members.append(
            EnsembleMember(
                member_id=resolved,
                resolved_model_id=resolved,
                provider_family=family or "",
            )
        )
    return members


def _distinct_provider_family_count(member_provenance: list[dict[str, str]]) -> int:
    """The count of distinct, RESOLVED provider families across ensemble-member provenance.

    A blank/absent ``provider_family`` (an unresolvable wrapper) contributes nothing, so the count
    reflects only RESOLVED, distinct families — the same rule the routing diversity gate applies
    (``machine_agreement.distinct_provider_families``). The orchestrator uses this to derive the
    PARTITION ensemble's family count from the real partition artifact's
    ``ensemble_member_provenance`` (scope §4), so a deterministic / single-provider partition
    cannot be machine-pinned (the rule's boundary was not cross-checked).
    """
    families: set[str] = set()
    for provenance in member_provenance:
        family = provenance.get("provider_family")
        if isinstance(family, str) and family.strip():
            families.add(family.strip())
    return len(families)


def deterministic_shape_for_controlled_text(
    controlled_text: str,
    *,
    claim_kind: str = "authorization_precondition",
) -> tuple[bool, list[EvidenceLevel]]:
    """The REAL deterministic shape check: parse + bind + evidence → (shape_ok, achieved levels).

    This is the PRODUCTION shape check the ``attest-spec`` CLI supplies (HELPER iter-3 #1): it
    derives the deterministic-shape signal and the achieved evidence levels from the ACTUAL
    artifacts (the Lark parse, symbol binding, self-consistency, and the supported-claim SMT
    shape), never a guessed pass. ``shape_ok`` is True iff the text parses, binds, and produces no
    ambiguous / unbound / unsupported / failed / timeout / needs-coverage evidence — the same
    bar ``build_package`` applies. The achieved levels are the ``EvidenceLevel``s the package's
    claims actually achieve (``STATICALLY_RESOLVED`` / ``CONSISTENCY_CHECKED`` / ``SMT_CHECKED``),
    a MEASURABLE signal (AC7: no path depends on a model-reported confidence scalar).

    ``claim_kind`` is the requirement's semantic class, required to construct the IR. It does NOT
    affect the deterministic-shape OUTCOME: the evidence computation
    (``static_resolution_result`` / ``check_self_consistency`` / ``smt_check_requirement``) never
    consults ``claim.kind`` — it is purely structural over the parsed action / conditions /
    expected result — so the default (``authorization_precondition``, the canonical Phase 0 class)
    is correct for the shape signal regardless of the requirement's actual class. The real class is
    applied at packaging time (``build_package``'s ``claim_kind``), not here.

    A text that fails to parse returns ``(False, [])`` — a routing refusal, never an exception: a
    parse failure is an unmet deterministic-shape signal that routes the candidate to the human
    queue, not a crash of the orchestrator. This keeps ``attest_spec_document`` CI-safe while
    making the production path EXERCISE the passing machine-pin branch (closing the iter-3 gap
    where the CLI never supplied a shape check, so routing always reported shape failure and only
    tests could auto-advance by injecting one).
    """
    from .adapter import default_generic_adapter
    from .bindings import bind_ir_with_diagnostics
    from .jsonutil import sha256_json
    from .parser import RequirementParser
    from .smt import evidence_for_ir

    parser = RequirementParser()
    try:
        ir = parser.parse_ir(
            controlled_text,
            requirement_id="REQ-SHAPE-CHECK",
            title="deterministic shape check",
            claim_kind=claim_kind,
        )
    except Exception:  # noqa: BLE001 — a parse failure is an unmet signal, not a crash
        return False, []
    binding = bind_ir_with_diagnostics(ir, default_generic_adapter())
    bound_ir = binding.bound_ir
    ir_hash = sha256_json(bound_ir)
    evidence = evidence_for_ir(
        bound_ir,
        ir_hash=ir_hash,
        missing_symbols=binding.missing_symbols,
        ambiguous_symbols=binding.ambiguous_symbols,
    )
    shape_ok = not (
        evidence.ambiguous
        or evidence.unbound_symbols
        or evidence.unsupported_claims
        or evidence.failed_checks
        or evidence.timeouts
        or evidence.needs_spec_coverage
    )
    achieved = [
        claim.achieved_evidence
        for claim in evidence.claims
        if claim.achieved_evidence is not None
    ]
    return shape_ok, achieved


# Function words + DSL structural keywords that carry no DOMAIN salience for the source-fidelity
# floor (HELPER iter-2 #4). Grounding must be proven by a real domain term shared between the source
# prose and the controlled rewrite (e.g. "reject" / "authorized" / "transfer"), NOT by the
# structural scaffolding ("operation", "request", "if", "then", "must") that EVERY controlled rewrite
# carries — otherwise every rewrite would trivially "ground" on its own boilerplate.
_AUDIT_STOPWORDS = frozenset(
    {
        # articles / determiners / pronouns / quantifiers
        "the", "a", "an", "this", "that", "these", "those", "it", "its", "they", "them", "their",
        "there", "all", "any", "each", "every", "some", "no", "none", "both", "either", "neither",
        # conjunctions / prepositions
        "and", "or", "but", "if", "else", "then", "when", "while", "because", "so", "than", "as",
        "of", "to", "for", "in", "on", "at", "by", "with", "from", "into", "onto", "over", "under",
        "before", "after", "between", "within", "without", "via", "per", "upon", "about", "across",
        "through",
        # verbs / modals / auxiliaries
        "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "has", "have",
        "had", "shall", "should", "will", "would", "may", "might", "must", "can", "could", "not",
        # DSL structural scaffolding (present in every controlled rewrite)
        "operation", "request", "actor", "action", "state", "change", "precondition",
        "postcondition", "expected", "result",
        # generic, non-domain nouns
        "system", "rule", "requirement", "value", "case",
    }
)


def _salient_terms(text: str) -> set[str]:
    """The lowercased salient DOMAIN terms of a text (drop stopwords + short tokens).

    Tokenizes on word characters (so ``state_change`` stays one token), lowercases, and keeps tokens
    of length >= 3 that are not audit stopwords. Used to compare a candidate's source prose against
    its controlled rewrite for the source-fidelity floor (HELPER iter-2 #4).
    """
    import re

    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return {token for token in tokens if len(token) >= 3 and token not in _AUDIT_STOPWORDS}


def _fidelity_grounded(source_terms: set[str], controlled_terms: set[str]) -> bool:
    """Whether at least one salient SOURCE term is reflected in the CONTROLLED terms.

    A source term grounds a controlled term when they are equal OR one is a prefix of the other with
    the shorter at least 4 chars (so paraphrase inflections like ``reject``→``rejected`` and
    ``transfer``→``transfers`` ground, while unrelated short tokens do not). A deterministic FLOOR:
    it proves the rewrite is on-topic with its source span, catching gross drift / fabrication, not
    every paraphrase nuance (the second-model semantic audit's job).
    """
    for source in source_terms:
        for controlled in controlled_terms:
            if source == controlled:
                return True
            shorter, longer = (
                (source, controlled) if len(source) <= len(controlled) else (controlled, source)
            )
            if len(shorter) >= 4 and longer.startswith(shorter):
                return True
    return False


def deterministic_decomposition_audit_for_controlled_text(
    controlled_text: str,
    source_text: str | None = None,
    *,
    claim_kind: str = "authorization_precondition",
) -> tuple[bool, str]:
    """A DISTINCT deterministic audit of a drafted candidate's decomposition + source fidelity.

    This is the PA-6 audit rubric (``audit_client``) computed DETERMINISTICALLY and DISTINCTLY from
    the deterministic SHAPE check (``deterministic_shape_for_controlled_text``): the shape check asks
    "does the text parse, bind, and produce clean evidence (no ambiguity / unbound / unsupported /
    failed / timeout / needs-coverage)"; this audit asks two FIDELITY questions the shape check does
    not:

      1. DECOMPOSITION fidelity — does the parsed IR's decomposition actually COVER the drafted
         clauses (a non-vacuous premise AND a non-vacuous obligation)? A text can parse and bind
         (shape-ok) yet decompose to a vacuous IR, which this catches.
      2. SOURCE-SPAN fidelity (HELPER iter-2 #4) — when the candidate's original source prose is
         supplied (``source_text``), does the controlled rewrite REFLECT the source's salient domain
         content (share at least one salient source term)? A rewrite that drifted to an entirely
         different subject — content invented relative to its source span — shares no salient term
         and FAILS. This is a deterministic FLOOR: it catches gross drift / fabrication, not every
         paraphrase nuance (that remains the second-model semantic audit's job), but it makes the
         audit verdict a REAL source-fidelity signal, not merely a non-vacuous-syntax check.

    Returns ``(passed, detail)``. A parse failure, a vacuous decomposition, or a rewrite ungrounded
    in its source returns ``(False, reason)`` — a routing refusal, NEVER a fabricated pass derived
    from the shape result (HELPER iter-1 #3: the orchestrator no longer reuses ``shape_ok`` as the
    audit verdict). ``detail`` is stored on each member's ``EnsembleAuditVerdict`` so the pin's
    provenance records the AUDIT result distinctly from the shape check. ``source_text`` defaults to
    None (then only the decomposition-fidelity floor runs), but the ``attest-spec`` orchestrator
    always passes the candidate's source prose, so the production path exercises both floors. Every
    check is measurable (AC7) and reproducible.
    """
    from .parser import RequirementParser

    parser = RequirementParser()
    try:
        ir = parser.parse_ir(
            controlled_text,
            requirement_id="REQ-AUDIT-CHECK",
            title="decomposition audit",
            claim_kind=claim_kind,
        )
    except Exception:  # noqa: BLE001 — an unparseable draft fails audit, never crashes routing
        return False, "decomposition audit failed: drafted controlled text did not parse to an IR"
    if not ir.claim.condition:
        return (
            False,
            "decomposition audit failed: the parsed IR has no premise (the drafted condition was "
            "dropped in decomposition)",
        )
    if not ir.claim.action or ir.claim.expected is None:
        return (
            False,
            "decomposition audit failed: the parsed IR has no obligation (the drafted action / "
            "expected result was dropped in decomposition)",
        )
    # Source-span fidelity floor (HELPER iter-2 #4): the rewrite must be grounded in its source.
    if source_text:
        source_terms = _salient_terms(source_text)
        controlled_terms = _salient_terms(controlled_text)
        # Only enforce when the source carries salient domain terms (a sourceless / all-stopword
        # source cannot ground anything; the decomposition floor already covered structure).
        if source_terms and not _fidelity_grounded(source_terms, controlled_terms):
            return (
                False,
                "decomposition audit failed: the controlled rewrite shares no salient content term "
                "with its source prose (the rewrite appears to have drifted from / invented content "
                "relative to its source span)",
            )
        return (
            True,
            "deterministic decomposition audit passed: the parsed IR carries a non-vacuous premise "
            "and obligation, and the controlled rewrite is grounded in its source prose "
            "(source-span fidelity)",
        )
    return (
        True,
        "deterministic decomposition audit passed: the parsed IR carries a non-vacuous premise and "
        "obligation covering the drafted clauses",
    )


def attest_spec_document(
    document: str,
    *,
    partition_clients: list[object] | None = None,
    drafting_clients: list[object] | None = None,
    partition_member_provenance: list[dict[str, str]] | None = None,
    drafting_member_provenance: list[dict[str, str]] | None = None,
    policy: MachinePinPolicy | None = None,
    language: str = "en",
    shape_check: "object | None" = None,
    audit_check: "object | None" = None,
    changed_paths: list[str] | None = None,
    # Zone 3 downstream-graph inputs (scope §7 steps 3-9; HELPER iter-1 #1/#2). The orchestrator
    # PRODUCES IR v0.2 + the lowered artifact + system-consistency + S&R + requirement-set-
    # consistency itself (no longer caller-supplied ``lowered`` / ``system_consistency`` — HELPER
    # iter-1 #2). ``registry`` + ``impact`` remain external inputs because the impact analysis is
    # per-SOURCE (it maps symbols to modules through the real call graph, needing the source tree,
    # not the spec document); when absent the orchestrator records an EXPLICIT prerequisite with the
    # command to produce it (never a vague ``needs_downstream_artifacts`` — HELPER iter-1 #2).
    registry: "object | None" = None,
    impact: ImpactAnalysisArtifact | None = None,
    impact_producer: "object | None" = None,
    project_root: "object | None" = None,
    claim_kind: str = "authorization_precondition",
) -> AttestSpecReport:
    """Orchestrate Zone 1 + Zone 2 + Zone 3 for a spec document → a consolidated human queue.

    Zone 1: ``partition_spec_document`` (deterministic, or an LLM ensemble whose boundary
    disagreements flag). Zone 2: ``draft_candidate_rules`` drafts each candidate through the
    drafting role (one or a cross-provider ensemble); a cross-provider ensemble that AGREES records
    the agreed controlled text + its canonical hash per candidate. For each agreed candidate the
    orchestrator builds the REAL routing input and calls ``route_machine_pinning`` (the production
    wiring of the ``machine_agreement`` trust state, scope §5): a clean, cross-provider-agreed,
    calibrated candidate whose changed paths the default-deny gate admits is machine-pinned; ANY
    unmet signal (including a policy that is OFF — the default) routes to the human queue.

    Zone 3 (scope §7 steps 3-9; HELPER iter-1 #1/#2): for each agreed candidate the orchestrator
    parses the controlled text to IR v0.1 and migrates to IR v0.2, lowers it to a TLA artifact, and
    runs ``requirement-set-consistency`` over the whole IR-v0.2 set — and EMBEDS the real artifact
    objects (``ir_v2`` / ``lowered`` / ``set_consistency_report``) in the report, not only hashes
    (HELPER iter-1 #1). When ``registry`` + ``impact`` are supplied it PRODUCES the spec-coverage
    gate (needs-coverage modules queue for specula-extract), PRODUCES the S∧R system-consistency
    result from its OWN lowered artifact (never caller-supplied — HELPER iter-1 #2), and PRODUCES
    the S∧R composition report (a counterexample / unsupported routes to the human queue). When
    ``registry`` / ``impact`` are absent the orchestrator records an EXPLICIT prerequisite (the
    artifact name + the command to produce it) in ``prerequisites`` (HELPER iter-1 #2), never a
    vague informational note. The CLI fans every embedded artifact out to ``--out-dir`` as a
    standalone file the dedicated commands can consume.

    ``shape_check`` is an optional callable ``(controlled_text) -> tuple[bool, list[EvidenceLevel]]``
    returning (deterministic-shape pass, achieved evidence levels) for a controlled text. The CLI
    supplies the REAL ``deterministic_shape_for_controlled_text``; when omitted, the deterministic-
    shape signal is conservatively False and no evidence levels are achieved, so routing requires a
    real shape check to ever auto-advance (never a guessed pass).

    ``audit_check`` is an optional callable ``(controlled_text, source_text) -> tuple[bool, str]``
    returning (audit pass, detail) — the DISTINCT per-member audit (HELPER iter-1 #3 / iter-2 #4).
    The orchestrator passes the candidate's ORIGINAL source prose (``candidate.text``) as
    ``source_text`` so the audit can verify the controlled rewrite is FAITHFUL to its source span,
    not merely non-vacuous (HELPER iter-2 #4). The CLI supplies the REAL
    ``deterministic_decomposition_audit_for_controlled_text``; when omitted, NO audit verdict is
    produced (the orchestrator no longer fabricates a verdict from ``shape_ok``), so the audit
    signal is unmet and the candidate routes to the human queue. This keeps the orchestrator CI-safe
    while making the audit a real computation distinct from the shape check.

    ``impact_producer`` is an optional zero-arg callable ``() -> ImpactAnalysisArtifact`` (HELPER
    iter-2 #1). When ``impact`` is not supplied AND a producer is given, the orchestrator INVOKES
    it to PRODUCE the source-impact artifact (the CLI builds it from ``--manifest`` / ``--symbol``
    over the real call graph), then runs the coverage gate + S ∧ R against the produced impact and
    EMBEDS it in the report (``impact_provenance == "produced"``). A directly-supplied ``impact``
    (``--impact``) takes precedence as a replay/override (``impact_provenance == "supplied"``); when
    neither is given the impact stays None and is recorded as an explicit prerequisite (AC8).
    """
    from .jsonutil import sha256_text
    from .parser import normalize_controlled_text
    from .spec_partition import draft_candidate_rules, partition_spec_document

    # --- Zone 1: partition (deterministic, or cross-provider ensemble) ---
    partition = partition_spec_document(
        document,
        clients=partition_clients,
        language=language,
        member_provenance=partition_member_provenance,
    )

    # Partition boundary / clarify flags seed the human queue (scope §4/§7).
    human_queue: list[AttestHumanQueueItem] = []
    flagged_segments = {flag.segment_index for flag in partition.needs_review}
    for flag in partition.needs_review:
        human_queue.append(
            AttestHumanQueueItem(
                candidate_index=flag.segment_index,
                candidate_text=partition.segments[flag.segment_index].text
                if flag.segment_index < len(partition.segments)
                else "",
                stage="partition",
                reasons=[f"{flag.kind.value}: {flag.reason}"],
            )
        )

    # --- Zone 1 step 2: per-candidate drafting (the drafting role) ---
    drafted = partition
    if drafting_clients:
        drafted = draft_candidate_rules(partition, drafting_clients, language=language)

    # Drafting clarify/disagreement flags route candidates to the human queue (scope §4). A
    # drafting-time flag is one NOT already present in the partition's needs_review; each carries a
    # per-candidate reason (``"candidate N: ..."``) whose index is recovered to list the candidate.
    for flag in drafted.needs_review:
        if flag in partition.needs_review:
            continue  # a partition-time flag already queued above
        candidate_index = _candidate_index_from_reason(flag.reason)
        human_queue.append(
            AttestHumanQueueItem(
                candidate_index=candidate_index,
                candidate_text=_candidate_text(drafted, candidate_index),
                stage="drafting",
                reasons=[f"{flag.kind.value}: {flag.reason}"],
            )
        )

    members = (
        _ensemble_members_from_provenance(drafting_member_provenance)
        if drafting_member_provenance
        else []
    )
    machine_pinned: list[AttestMachinePin] = []
    policy_off = policy is None

    # The Zone 1 PARTITION ensemble's measured composition (scope §4) — derived from the REAL
    # partition artifact, NOT the caller's intent: ``ensemble_members`` is 0 (deterministic), 1
    # (single client), or ≥2 (cross-provider ensemble), and ``ensemble_member_provenance`` carries
    # each member's resolved provider family. A machine pin requires the rule's BOUNDARY to have
    # been cross-checked by a cross-provider partition ensemble, so a deterministic / single-provider
    # partition (families < the policy's required minimum) routes every candidate to the human queue
    # — "no partition ensemble ran" is now distinguishable from "the partition ensemble agreed".
    partition_ensemble_size = partition.ensemble_members
    partition_ensemble_families = _distinct_provider_family_count(
        partition.ensemble_member_provenance
    )

    # --- Zone 2: route each drafted candidate through the machine_agreement trust state ---
    for candidate in drafted.candidate_rules:
        # A candidate with no controlled text was already queued at the partition/drafting stage
        # (clarify / disagreement); it has nothing to route. Skip it here so it is not double-listed.
        if candidate.controlled_text is None or candidate.controlled_text_agreement_hash is None:
            if candidate.index not in {item.candidate_index for item in human_queue}:
                human_queue.append(
                    AttestHumanQueueItem(
                        candidate_index=candidate.index,
                        candidate_text=candidate.text,
                        stage="drafting" if drafting_clients else "partition",
                        reasons=[
                            "no agreed controlled text (single-voice draft or unpartitioned); "
                            "machine pinning requires a cross-provider-agreed draft"
                        ],
                    )
                )
            continue

        # The deterministic-shape signal + achieved evidence levels (MEASURABLE, AC7). A default
        # shape check invents no evidence: the caller must supply one to ever auto-advance.
        if shape_check is not None:
            shape_ok, achieved_levels = shape_check(candidate.controlled_text)
        else:
            shape_ok, achieved_levels = False, []

        # The routing agreement: the drafting ensemble agreed (controlled_text_agreement_hash is
        # set), and the agreement hash binds the pin to the agreed meaning. Re-derived here as the
        # canonical hash of the normalized agreed text (the form the package stores).
        agreement = EnsembleAgreementResult(
            agreed=True,
            agreement_hash=sha256_text(normalize_controlled_text(candidate.controlled_text)),
        )
        # Per-member audit verdicts (HELPER iter-1 #3): the audit is a DISTINCT computation from the
        # shape check — the orchestrator no longer fabricates a verdict from ``shape_ok``. Under
        # agreement every member produced the SAME controlled text, so each member's decomposition is
        # audited by the same ``audit_check`` (the CLI's real deterministic decomposition audit),
        # producing one verdict per member with the audit's own ``detail`` (recorded on the pin's
        # provenance distinctly from the shape result). When NO ``audit_check`` is supplied, NO
        # verdict is produced: ``audit_verdicts`` is empty, ``audit_verdicts_pass`` fails (the member
        # set is uncovered), and the candidate routes to the human queue — never a fabricated pass.
        audit_verdicts: list[EnsembleAuditVerdict] = []
        if audit_check is not None:
            # Pass the candidate's ORIGINAL source prose so the audit can check source-span fidelity
            # (HELPER iter-2 #4), not merely non-vacuous syntax.
            audit_ok, audit_detail = audit_check(candidate.controlled_text, candidate.text)
            routed_members = members or [
                EnsembleMember(
                    member_id="drafting-ensemble",
                    resolved_model_id="drafting-ensemble",
                    provider_family="unknown",
                )
            ]
            audit_verdicts = [
                EnsembleAuditVerdict(
                    member_id=member.member_id,
                    verdict="passed" if audit_ok else "failed",
                    detail=audit_detail,
                )
                for member in routed_members
            ]

        from .machine_agreement import MachineRoutingInput

        routing_input = MachineRoutingInput(
            members=members or [
                EnsembleMember(
                    member_id="drafting-ensemble",
                    resolved_model_id="drafting-ensemble",
                    provider_family="unknown",
                )
            ],
            audit_verdicts=audit_verdicts,
            agreement=agreement,
            deterministic_shape_ok=shape_ok,
            no_clarify_sentinel=True,
            boundary_disagreement=candidate.source_segment_index in flagged_segments,
            timestamp="2026-06-26T00:00:00Z",
            achieved_evidence_levels=achieved_levels,
            changed_paths=list(changed_paths) if changed_paths else [],
            partition_ensemble_size=partition_ensemble_size,
            partition_ensemble_families=partition_ensemble_families,
        )
        decision: MachineRoutingDecision = route_machine_pinning(routing_input, policy=policy)

        if decision.auto_advance and decision.pinning is not None:
            machine_pinned.append(
                AttestMachinePin(
                    candidate_index=candidate.index,
                    candidate_text=candidate.text,
                    controlled_text=candidate.controlled_text,
                    pinning=decision.pinning,
                )
            )
        else:
            human_queue.append(
                AttestHumanQueueItem(
                    candidate_index=candidate.index,
                    candidate_text=candidate.text,
                    stage="routing" if not policy_off else "routing",
                    reasons=decision.unmet_signals or ["machine pinning is disabled"],
                )
            )

    # --- Resolve the source-impact artifact (HELPER iter-2 #1). A directly-supplied ``impact``
    #     (--impact, a replay/override) takes precedence; otherwise, when an ``impact_producer`` is
    #     given (the CLI builds it from --manifest/--symbol over the real call graph), PRODUCE the
    #     impact here so attest-spec genuinely produces the impact artifact before the coverage gate
    #     + S∧R (AC8). None when neither was supplied → recorded as an explicit prerequisite. ---
    resolved_impact: ImpactAnalysisArtifact | None = impact
    impact_provenance: Literal["produced", "supplied"] | None = (
        "supplied" if impact is not None else None
    )
    if resolved_impact is None and impact_producer is not None:
        produced = impact_producer()
        if produced is not None:
            resolved_impact = produced
            impact_provenance = "produced"

    # --- Zone 3: the downstream artifact graph (scope §7 steps 3-9; HELPER iter-1 #1/#2) ---
    # The orchestrator PRODUCES IR v0.2 + the lowered artifact for each agreed candidate, runs
    # requirement-set-consistency over the set, and — when registry+impact are supplied — produces
    # the coverage gate, the S∧R system-consistency (from its OWN lowered), and the S∧R composition.
    # Every produced artifact is EMBEDDED in the returned report (not only its hash). Blockers route
    # to the human queue with their reason; absent external inputs (impact/registry) are recorded as
    # EXPLICIT prerequisites with the command to produce them (never a vague informational note).
    graph = _run_downstream_graph(
        drafted=drafted,
        human_queue=human_queue,
        claim_kind=claim_kind,
        registry=registry,
        impact=resolved_impact,
        project_root=project_root,
    )

    # --- Reconcile machine pins against the downstream graph (HELPER iter-2 #2/#3). A pinned
    #     candidate with a downstream blocker (set contradiction/unchecked, a coverage gap on its
    #     change, or an S∧R result that disproved OR could-not-validate the rule) is marked
    #     attention_required and surfaced in the human queue, so the report never presents a
    #     candidate with an unresolved downstream blocker as a clean, no-attention machine pin. ---
    machine_pinned = _reconcile_machine_pins_with_downstream(
        machine_pinned, graph.attention_by_candidate, human_queue
    )

    return AttestSpecReport(
        document_hash=partition.document_hash,
        policy_id=policy.policy_id if policy is not None else None,
        policy_off=policy_off,
        total_candidates=len(drafted.candidate_rules),
        partition=partition,
        impact=resolved_impact,
        impact_provenance=impact_provenance,
        machine_pinned=machine_pinned,
        human_queue=human_queue,
        downstream=graph.downstream,
        set_consistency=graph.set_consistency,
        coverage_gate=graph.coverage_gate,
        set_consistency_report=graph.set_consistency_report,
        coverage_report=graph.coverage_report,
        prerequisites=graph.prerequisites,
        limitations=graph.limitations,
    )


def _candidate_index_from_reason(reason: str) -> int:
    """Extract the candidate index from a drafting flag reason (``"candidate N: ..."``)."""
    marker = "candidate "
    if marker in reason:
        rest = reason.split(marker, 1)[1]
        head = rest.split(":", 1)[0].strip()
        if head.isdigit():
            return int(head)
    return -1


def _candidate_text(drafted: "object", candidate_index: int) -> str:
    """Look up a candidate's plain text by index (best-effort; '' when not found)."""
    for candidate in getattr(drafted, "candidate_rules", []):
        if candidate.index == candidate_index:
            return candidate.text
    return ""


def _reconcile_machine_pins_with_downstream(
    machine_pinned: list[AttestMachinePin],
    attention_by_candidate: dict[int, list[str]],
    human_queue: list[AttestHumanQueueItem],
) -> list[AttestMachinePin]:
    """Mark machine pins a downstream blocker pertains to, and surface them in the human queue.

    A machine pin records that the ensemble agreed on the rule's MEANING (scope §5). The downstream
    graph (scope §7 steps 3-9) runs AFTER routing and can find a blocker for the SAME candidate: a
    requirement-set contradiction/unchecked, a coverage gap on the change, or an S∧R result that
    disproved OR could-not-validate the rule. Such a candidate ALSO needs human attention, so
    presenting it as a clean, no-attention machine pin would be dishonest (HELPER iter-2 #2/#3).
    This reconciliation marks each affected pin ``attention_required`` with its blocker reason(s)
    and ensures it is listed in ``human_queue`` — the pin keeps its provenance (the meaning WAS
    machine-agreed) but is never presented as requiring no attention while a blocker is unresolved.

    A candidate flagged by a candidate-keyed downstream stage (set-consistency, S∧R) is ALREADY in
    ``human_queue`` from that stage, so no duplicate item is added; a candidate flagged only by a
    module-keyed stage (a coverage gap, queued by module not by candidate) gets one
    ``downstream_blocker`` item so every ``attention_required`` pin is in the actionable queue.
    """
    if not attention_by_candidate:
        return machine_pinned
    queued_candidate_indices = {
        item.candidate_index for item in human_queue if item.candidate_index >= 0
    }
    reconciled: list[AttestMachinePin] = []
    for pin in machine_pinned:
        reasons = attention_by_candidate.get(pin.candidate_index)
        if not reasons:
            reconciled.append(pin)
            continue
        reconciled.append(
            pin.model_copy(
                update={"attention_required": True, "attention_reasons": list(reasons)}
            )
        )
        if pin.candidate_index not in queued_candidate_indices:
            human_queue.append(
                AttestHumanQueueItem(
                    candidate_index=pin.candidate_index,
                    candidate_text=pin.candidate_text,
                    stage="downstream_blocker",
                    reasons=list(reasons),
                )
            )
            queued_candidate_indices.add(pin.candidate_index)
    return reconciled


@dataclass
class _DownstreamGraph:
    """The produced Zone 3 graph (HELPER iter-1 #1/#2): the per-rule downstream entries (each
    EMBEDDING the real ``ir_v2`` / ``lowered`` / ``system_consistency`` / ``s_and_r`` objects), the
    full set-consistency + coverage reports, the queue-routing summaries, the explicit prerequisites
    for the external artifacts the orchestrator could not produce, and the honest limitations.

    ``attention_by_candidate`` maps a candidate index → the downstream blocker reason(s) that
    pertain to it (HELPER iter-2 #2/#3): a requirement-set contradiction/unchecked, a coverage gap
    on its change, or an S∧R result that disproved OR could-not-validate the rule. The orchestrator
    reconciles ``machine_pinned`` against this map so a pinned candidate with an unresolved
    downstream blocker is marked ``attention_required`` and listed in the human queue.
    """

    downstream: list[AttestRuleDownstream]
    set_consistency: AttestSetConsistency | None
    coverage_gate: AttestCoverageGate | None
    set_consistency_report: RequirementSetConsistencyReport | None
    coverage_report: SpecCoverageGateReport | None
    prerequisites: list[AttestPrerequisite] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    attention_by_candidate: dict[int, list[str]] = field(default_factory=dict)


def _run_downstream_graph(
    *,
    drafted: object,
    human_queue: list[AttestHumanQueueItem],
    claim_kind: str,
    registry: object | None,
    impact: object | None,
    project_root: object | None,
) -> _DownstreamGraph:
    """Zone 3 steps 3-9 (scope §7): PRODUCE + EMBED IR v0.2, lowering, set-consistency, coverage,
    system-consistency, and S&R (HELPER iter-1 #1/#2).

    PRODUCED + always emitted (no external inputs needed), each EMBEDDED in the report:
      * IR v0.2 per agreed candidate (parse v0.1 → migrate v0.2) — embedded as ``ir_v2``;
      * the lowered TLA artifact per candidate (``lower_ir_v2_to_tla``) — embedded as ``lowered``.
        The v0.1→v0.2 migration builds a generic obligation tree the live lowerer does not accept
        for these classes, so lowering typically REFUSES; that refusal (with diagnostics) is HONEST
        and surfaced in the embedded artifact, never hidden;
      * ``requirement-set-consistency`` over the IR-v0.2 set — embedded as ``set_consistency_report``;
        contradictions/unchecked route to the human queue (scope §7 step 9).

    PRODUCED when ``registry`` + ``impact`` are supplied (the impact analysis is per-SOURCE, so the
    source-derived impact + reviewed registry remain external inputs — see ``prerequisites``):
      * the spec-coverage gate — embedded as ``coverage_report``; needs-coverage modules queue for
        specula-extract (scope §7 step 6, never a pass);
      * the S∧R system-consistency result, PRODUCED from the orchestrator's OWN lowered artifact
        (never caller-supplied — HELPER iter-1 #2) via ``check_solver_backed_system_consistency`` —
        embedded as ``system_consistency``; for a refused lowering it is honestly ``unsupported``;
      * the S∧R composition report — embedded as ``s_and_r``; a non-valid result routes to the queue.
        Produced PER CANDIDATE (each candidate is one requirement, run against the shared registry +
        impact), so a multi-rule spec never leaves an agreed candidate's S&R stage silently skipped
        (HELPER iter-3 followup #2).

    When ``registry`` / ``impact`` are absent the graph records an EXPLICIT prerequisite (the
    artifact name + the command to produce it) — NOT a silent ``needs_downstream_artifacts`` note
    (HELPER iter-1 #2). Mutates ``human_queue`` in place with downstream blockers (set
    contradictions, needs-coverage modules, S&R counterexamples / unsupported), each with its
    reason, AND returns ``attention_by_candidate`` (candidate index → blocker reasons) so the caller
    reconciles ``machine_pinned`` — a pinned candidate with a blocker is reverted to
    ``attention_required`` and listed in the queue (HELPER iter-2 #2/#3).
    """
    from pathlib import Path

    from .compositional_ir import migrate_requirement_ir_v1_to_v2
    from .coverage_alignment import build_spec_coverage_gate
    from .jsonutil import sha256_json
    from .parser import RequirementParser
    from .system_checker import (
        check_requirement_set_consistency,
        check_solver_backed_system_consistency,
    )
    from .system_composition import build_s_and_r_composition_report
    from .translator import lower_ir_v2_to_tla

    downstream: list[AttestRuleDownstream] = []
    parser = RequirementParser()

    # requirement_id ↔ candidate_index map (for set-consistency queue routing).
    id_to_index: dict[str, int] = {}
    ir_v2_by_index: dict[int, object] = {}
    any_lowering_refused = False

    # Downstream blocker reasons per candidate index (HELPER iter-2 #2/#3): the orchestrator
    # reconciles ``machine_pinned`` against this map after the graph so a pinned candidate with an
    # unresolved downstream blocker is marked attention_required and listed in the human queue.
    attention_by_candidate: dict[int, list[str]] = {}

    def _flag(candidate_index: int, reason: str) -> None:
        attention_by_candidate.setdefault(candidate_index, []).append(reason)

    for candidate in getattr(drafted, "candidate_rules", []):
        # Zone 3 processes candidates that reached an AGREED controlled text (machine-pinned or
        # human-queued-but-parseable). A candidate with no controlled text (clarify/disagreement)
        # was already queued upstream and has no meaning to lower.
        controlled = getattr(candidate, "controlled_text", None)
        if not controlled:
            continue
        requirement_id = f"REQ-ATTEST-{candidate.index:03d}"
        id_to_index[requirement_id] = candidate.index

        # Parse v0.1 → migrate v0.2 (deterministic). A parse failure is recorded (ir_v2_produced=
        # False) and the candidate is skipped downstream — it is already in the human queue from
        # routing (shape-fail), and its embedded artifacts stay None (unreachable downstream).
        try:
            ir_v1 = parser.parse_ir(
                controlled,
                requirement_id=requirement_id,
                title=getattr(candidate, "text", "")[:80] or requirement_id,
                claim_kind=claim_kind,
            )
            ir_v2, _record = migrate_requirement_ir_v1_to_v2(ir_v1)
        except Exception:  # noqa: BLE001 — a parse/migrate failure is recorded, not a crash
            downstream.append(
                AttestRuleDownstream(
                    candidate_index=candidate.index,
                    requirement_id=requirement_id,
                    ir_v2_produced=False,
                    stage=AttestDownstreamStage.needs_downstream_artifacts,
                )
            )
            continue

        ir_v2_by_index[candidate.index] = ir_v2
        ir_v2_hash = sha256_json(ir_v2)

        # Lower the IR v0.2 to a TLA artifact (deterministic). The migrated obligation tree's shape
        # is not accepted by the live lowerer for these classes, so lowering REFUSES — that refusal
        # (with diagnostics) is honest and surfaced in the embedded ``lowered`` artifact.
        lowered_artifact: object | None = None
        lowered_status: str | None = None
        try:
            lowered_artifact = lower_ir_v2_to_tla(ir_v2)
            lowered_status = lowered_artifact.status
        except Exception:  # noqa: BLE001 — a lowering failure is recorded, not a crash
            lowered_artifact = None
            lowered_status = None
        if lowered_status == "refused":
            any_lowering_refused = True

        downstream.append(
            AttestRuleDownstream(
                candidate_index=candidate.index,
                requirement_id=requirement_id,
                ir_v2_hash=ir_v2_hash,
                ir_v2_produced=True,
                lowered_status=lowered_status,
                ir_v2=ir_v2,
                lowered=lowered_artifact,
                stage=AttestDownstreamStage.ir_v2_produced,
            )
        )

    # --- requirement-set-consistency over the IR-v0.2 set (deterministic, always; embed full) ---
    set_consistency: AttestSetConsistency | None = None
    set_consistency_report: RequirementSetConsistencyReport | None = None
    if ir_v2_by_index:
        report = check_requirement_set_consistency(list(ir_v2_by_index.values()))
        set_consistency_report = report
        contradicted: list[int] = []
        unchecked: list[int] = []
        for contradiction in getattr(report, "contradictions", []):
            for rid in getattr(contradiction, "requirement_ids", []):
                if rid in id_to_index:
                    contradicted.append(id_to_index[rid])
        for unchecked_entry in getattr(report, "unchecked", []):
            for rid in getattr(unchecked_entry, "requirement_ids", []):
                if rid in id_to_index:
                    unchecked.append(id_to_index[rid])
        set_consistency = AttestSetConsistency(
            result=report.result,
            contradiction_count=len(getattr(report, "contradictions", [])),
            unchecked_count=len(getattr(report, "unchecked", [])),
            contradicted_candidates=sorted(set(contradicted)),
            unchecked_candidates=sorted(set(unchecked)),
        )
        # Route contradicting/unchecked candidates to the human queue with their reason, and flag
        # them for machine-pin reconciliation (HELPER iter-2 #2: a contradicting/undecided candidate
        # is never a clean machine pin).
        for candidate_index in sorted(set(contradicted)):
            reason = (
                "this candidate's IR v0.2 contradicts another candidate's IR v0.2 in the "
                "requirement-set-consistency check (a definite conflict was proven)"
            )
            human_queue.append(
                AttestHumanQueueItem(
                    candidate_index=candidate_index,
                    candidate_text=_candidate_text(drafted, candidate_index),
                    stage="set_consistency",
                    reasons=[reason],
                )
            )
            _flag(candidate_index, reason)
        for candidate_index in sorted(set(unchecked)):
            reason = (
                "this candidate's IR v0.2 could not be decided in the requirement-set-"
                "consistency check (lowering refused/needs_review, or a sourceless "
                "conflict); the set is not cleared"
            )
            human_queue.append(
                AttestHumanQueueItem(
                    candidate_index=candidate_index,
                    candidate_text=_candidate_text(drafted, candidate_index),
                    stage="set_consistency",
                    reasons=[reason],
                )
            )
            _flag(candidate_index, reason)

    # --- spec-coverage gate (needs registry + impact; scope §7 step 6; embed full report) ---
    coverage_gate: AttestCoverageGate | None = None
    coverage_report: SpecCoverageGateReport | None = None
    if registry is not None and impact is not None:
        coverage_report = build_spec_coverage_gate(impact=impact, registry=registry)
        coverage_gate = AttestCoverageGate(
            result=coverage_report.result,
            unspecified_modules=list(coverage_report.unspecified_modules),
        )
        for module_id in coverage_report.unspecified_modules:
            human_queue.append(
                AttestHumanQueueItem(
                    candidate_index=-1,
                    candidate_text=module_id,
                    stage="needs_coverage",
                    reasons=[
                        f"affected module {module_id} has no registered system spec S; queued for "
                        "specula-extract — a coverage gap is never a pass (scope §7 step 6)"
                    ],
                )
            )
        # A coverage gap on the change flags EVERY agreed candidate's pin (HELPER iter-2 #2). The
        # module-keyed items above are the actionable specula-extract steps; the impact is the WHOLE
        # change's impact and does not map modules → candidates, so conservatively every candidate of
        # a change that touches an unmodeled module is reverted from a clean pin (a coverage gap is
        # never a pass). The reconciliation lists each flagged pin in the human queue. This is the
        # SINGLE coverage-attribution point — it covers both the document-wide set and the per-
        # candidate S&R path below, so neither re-flags coverage (no duplicate reason per candidate).
        if coverage_report.unspecified_modules:
            modules = ", ".join(coverage_report.unspecified_modules)
            coverage_reason = (
                f"this candidate's change touches module(s) with no registered system spec S "
                f"({modules}); queued for specula-extract — a coverage gap is never a pass"
            )
            for candidate_index in ir_v2_by_index:
                _flag(candidate_index, coverage_reason)

    # --- system-consistency + S∧R, PRODUCED PER CANDIDATE from the orchestrator's OWN lowered
    #     (every agreed candidate when registry + impact are supplied; HELPER iter-3 followup #2 — no
    #     longer gated to a single-candidate change, so a MULTI-rule spec can never report clean
    #     machine pins while its per-rule S&R stage was silently skipped). Each candidate is one
    #     requirement, so S∧R runs once per candidate against the shared reviewed registry + the
    #     change's impact. The orchestrator PRODUCES the consistency result for each (never caller-
    #     supplied — HELPER iter-1 #2): for a refused lowering it is honestly ``unsupported``, which
    #     makes that candidate's S∧R ``unsupported`` and routes it to the human queue. ---
    if registry is not None and impact is not None:
        root = Path(project_root) if project_root is not None else Path.cwd()
        # A DISPROOF (counterexample/invalid/timeout) marks the entry s_and_r_blocked. ``unsupported``
        # is NOT a disproof — it means the orchestrator's own lowering refused (the v0.1→v0.2
        # migration-shape limitation), so S∧R never validated the rule — but it is STILL an
        # unresolved blocker: an unverified S∧R stage must not let a machine-pinned candidate appear
        # clean (HELPER iter-2 #3). Only an explicit ``valid`` clears the candidate.
        disproving = {"counterexample", "invalid", "timeout"}
        for candidate_index, ir_v2 in ir_v2_by_index.items():
            own_lowered = next(
                (entry.lowered for entry in downstream if entry.candidate_index == candidate_index),
                None,
            )
            consistency = None
            if own_lowered is not None:
                try:
                    consistency = check_solver_backed_system_consistency(
                        requirement=ir_v2,
                        lowered=own_lowered,
                        registry=registry,
                        impact=impact,
                        project_root=root,
                    )
                except Exception:  # noqa: BLE001 — a consistency failure is recorded, not a crash
                    consistency = None
            sandr = None
            if consistency is not None and own_lowered is not None:
                try:
                    sandr = build_s_and_r_composition_report(
                        requirement=ir_v2,
                        lowered=own_lowered,
                        registry=registry,
                        impact=impact,
                        project_root=root,
                        consistency=consistency,
                    )
                except Exception:  # noqa: BLE001 — an S&R failure is recorded, not a crash
                    sandr = None
            sandr_result = getattr(sandr, "result", None) if sandr is not None else None
            # Reconcile the downstream result for THIS candidate (HELPER iter-2 #2/#3).
            for entry in downstream:
                if entry.candidate_index == candidate_index:
                    entry.system_consistency = consistency
                    entry.s_and_r = sandr
                    entry.s_and_r_result = sandr_result
                    if sandr_result in disproving:
                        entry.stage = AttestDownstreamStage.s_and_r_blocked
                    break

            # NB: a coverage gap on this candidate's change was ALREADY attributed to its pin by the
            # document-wide coverage block above (it flags every agreed candidate in
            # ``ir_v2_by_index``). Re-flagging it here would record the identical reason twice in the
            # pin's ``attention_reasons`` — coverage attribution lives in exactly one place.

            # Route a non-``valid`` S∧R result to the human queue and flag the pin (HELPER iter-2 #3).
            if sandr_result in disproving:
                reason = (
                    f"S ∧ R composition returned {sandr_result!r} (a counterexample/invalid/timeout "
                    "disproves the requirement under the reviewed system specs)"
                )
                human_queue.append(
                    AttestHumanQueueItem(
                        candidate_index=candidate_index,
                        candidate_text=_candidate_text(drafted, candidate_index),
                        stage="s_and_r",
                        reasons=[reason],
                    )
                )
                _flag(candidate_index, reason)
            elif sandr_result != "valid":
                # ``unsupported`` (the common migration-shape case) or a could-not-produce error
                # (None): S∧R did not validate the rule, so it is not cleared. Distinguish the two
                # for the human, but both queue the candidate and flag its pin.
                if sandr_result == "unsupported":
                    reason = (
                        "S ∧ R composition returned 'unsupported' — the orchestrator's own lowering "
                        "refused (the v0.1→v0.2 migration-shape limitation), so S ∧ R never validated "
                        "the rule; the rule is NOT cleared (run the dedicated native lowering + "
                        "s-and-r-composition on the reviewed requirement, or human-review it)"
                    )
                else:
                    reason = (
                        "S ∧ R composition could not be produced for this candidate (the lowering or "
                        "the consistency/composition step did not complete); the rule is NOT "
                        "validated — run the dedicated lowering + s-and-r-composition, or human-"
                        "review it"
                    )
                human_queue.append(
                    AttestHumanQueueItem(
                        candidate_index=candidate_index,
                        candidate_text=_candidate_text(drafted, candidate_index),
                        stage="s_and_r",
                        reasons=[reason],
                    )
                )
                _flag(candidate_index, reason)

    # --- explicit prerequisites for the external artifacts the orchestrator cannot produce from the
    #     document alone (HELPER iter-1 #2: named, actionable — not a silent informational note). ---
    prerequisites: list[AttestPrerequisite] = []
    if ir_v2_by_index:
        if impact is None:
            prerequisites.append(
                AttestPrerequisite(
                    artifact="impact",
                    reason=(
                        "the source-impact analysis is per-SOURCE (it maps the requirement's symbols "
                        "to affected modules through the real call graph), so it needs the source "
                        "tree, not the spec document; supply it with --impact to run the coverage "
                        "gate and produce the S∧R system-consistency"
                    ),
                    command=(
                        "nlreq python-source-impact <manifest> --symbol <changed-symbol> "
                        "--project-root <root> --out impact.json"
                    ),
                )
            )
        if registry is None:
            prerequisites.append(
                AttestPrerequisite(
                    artifact="registry",
                    reason=(
                        "the reviewed system-spec registry (the set of S specs) is an external "
                        "input; supply it with --registry to run the coverage gate and produce the "
                        "S∧R system-consistency"
                    ),
                    command="supply the reviewed system-spec registry via --registry <registry.json>",
                )
            )

    # --- honest limitations of the produced graph (evergreen). ---
    limitations: list[str] = []
    if any_lowering_refused:
        limitations.append(
            "The drafting role emits v1-form controlled text, which attest-spec parses to IR v0.1 "
            "and migrates to IR v0.2; the migrated obligation tree's shape is not accepted by the "
            "live TLA lowering for these classes, so the produced lowering REFUSES and the produced "
            "S∧R system-consistency is therefore 'unsupported'. A valid S∧R requires a native DSL "
            "v3 lowering produced after human review — run the dedicated lower-ir-v2 / "
            "s-and-r-composition commands on the reviewed requirement."
        )

    return _DownstreamGraph(
        downstream=downstream,
        set_consistency=set_consistency,
        coverage_gate=coverage_gate,
        set_consistency_report=set_consistency_report,
        coverage_report=coverage_report,
        prerequisites=prerequisites,
        limitations=limitations,
        attention_by_candidate=attention_by_candidate,
    )
