import json
import shutil
import sys
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.contradiction_taxonomy import build_cross_requirement_contradiction_taxonomy
from nlreq.dsl_v2 import DslV2Parser
from nlreq.dsl_v3 import DslV3Parser
from nlreq.end_to_end_gate import _cover_s_and_r_fragments
from nlreq.formal_backend import FormalBackendBudget, FormalBackendExecution
from nlreq.formal_claim import build_formal_claim, build_proof_dispatch_plan_from_formal_claim
from nlreq.formal_claim_smt import smt_check_formal_claim_predicate_fragments
from nlreq.formal_lowering import (
    OutcomePredicate,
    PostStateObligation,
    build_system_spec_contribution,
    compose_s_and_r_module,
    derive_post_state_obligation,
    lower_state_postcondition_tla,
    validate_state_postcondition_shape,
)
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.models import EvidenceLevel
from nlreq.proof_closure import build_proof_object
from nlreq.system_checker import (
    APALACHE_S_AND_R_COMMAND,
    DEFAULT_S_AND_R_DEPTH,
    RequirementSetConsistencyReport,
    _solver_result,
    check_requirement_set_consistency,
    check_solver_backed_system_consistency,
    check_system_consistency_fixture,
)
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import LoweredFormalArtifact, lower_ir_v2_to_tla


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_system_consistency_returns_valid_for_fresh_specs_and_lowered_requirement(
    tmp_path: Path,
) -> None:
    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "valid"
    assert result.result.evidence_level == "CONSISTENCY_CHECKED"


def test_system_consistency_returns_counterexample_marker(tmp_path: Path) -> None:
    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_COUNTEREXAMPLE:REQ-SYS-001\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "counterexample"
    assert result.counterexamples[0].metadata["spec_id"] == "spec:redemption"


def test_system_consistency_returns_timeout_marker(tmp_path: Path) -> None:
    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=_registry(tmp_path, marker="\\* NLREQ_TIMEOUT\n"),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "timeout"


def test_system_consistency_returns_unsupported_for_stale_spec(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    data = registry.model_dump(mode="json")
    data["specs"][0]["freshness"] = "stale"

    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=SystemSpecRegistry.model_validate(data),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "unsupported"


def test_system_consistency_returns_unsupported_for_refused_lowering(tmp_path: Path) -> None:
    lowered = lower_ir_v2_to_tla(_ir())
    refused = LoweredFormalArtifact.model_validate(
        lowered.model_copy(update={"status": "refused", "content": None, "content_hash": None})
        .model_dump(mode="json", exclude_none=True)
    )

    result = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=refused,
        registry=_registry(tmp_path),
        impact=_impact(),
        project_root=tmp_path,
    )

    assert result.result.status == "unsupported"


def _set_ir(text: str, requirement_id: str):
    """Parse one v3 requirement for the cross-requirement set checker."""
    return DslV3Parser().parse_ir(text, requirement_id=requirement_id, title=requirement_id)


# Cross-requirement consistency is decided over typed FormalClaim *obligation* fragments. The unit
# of conflict is what two requirements must both make true under co-occurring premises on a shared
# scope — not their premises. Each detected class below has a positive fixture and a discrimination
# control; the four classes the v3 grammar cannot express across requirements have controls showing
# the checker does not invent a contradiction (see the taxonomy table for the reason each is
# catalogued but not emitted).


def test_requirement_set_consistency_numeric_range_disjointness() -> None:
    """Two invariant obligations on one variable, under the same condition, bound an empty interval."""
    floor = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral <= 5\n",
        "REQ-CEILING",
    )

    report = check_requirement_set_consistency([floor, ceiling])

    assert report.result == "contradiction"
    conflicts = [
        c for c in report.contradictions if c.contradiction_type == "numeric_range_disjointness"
    ]
    assert len(conflicts) == 1
    assert conflicts[0].requirement_ids == ["REQ-FLOOR", "REQ-CEILING"]
    # The offending fragments carry their source spans (no bare "set is inconsistent").
    assert [span.text for span in conflicts[0].source_spans] == [
        "keep collateral >= 10",
        "keep collateral <= 5",
    ]


def test_requirement_set_consistency_allows_compatible_numeric_bounds() -> None:
    """Discrimination control: a lower bound below the upper bound bounds a non-empty interval, so
    the same machinery must NOT flag compatible ranges — only genuinely empty ones."""
    floor = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral <= 50\n",
        "REQ-CEILING",
    )

    report = check_requirement_set_consistency([floor, ceiling])

    assert report.result == "valid"
    assert report.contradictions == []


def test_requirement_set_consistency_numeric_core_blames_only_binding_bounds() -> None:
    """Minimal conflicting core: only the strongest lower and strongest upper are blamed. A third,
    compatible bound on the same variable is not dragged into the report."""
    floor = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral <= 5 and keep collateral <= 8\n",
        "REQ-CEILING",
    )

    report = check_requirement_set_consistency([floor, ceiling])

    conflicts = [
        c for c in report.contradictions if c.contradiction_type == "numeric_range_disjointness"
    ]
    assert len(conflicts) == 1
    spans = [span.text for span in conflicts[0].source_spans]
    assert spans == ["keep collateral >= 10", "keep collateral <= 5"]
    assert "keep collateral <= 8" not in spans


def test_requirement_set_consistency_gate_skips_disjoint_premises() -> None:
    """Conditional-overlap gate: opposite premises (approved vs not approved) are the two halves of a
    complete specification, never both firing, so conflicting obligations under them are NOT a
    contradiction. The old premise-pooling checker reported this consistent pair as a conflict."""
    approve = _set_ir(
        "requirement state_precondition:\n"
        "scope operation\n"
        "when actor is approved\n"
        "then operation must succeed\n",
        "REQ-APPROVED",
    )
    reject = _set_ir(
        "requirement state_precondition:\n"
        "scope operation\n"
        "when actor is not approved\n"
        "then operation must reject before settled\n",
        "REQ-NOT-APPROVED",
    )

    report = check_requirement_set_consistency([approve, reject])

    assert report.result == "valid"
    assert report.contradictions == []


def test_requirement_set_consistency_mutual_exclusion() -> None:
    """Two post-state obligations pin the same variable to incompatible values under one condition."""
    active = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be active\n",
        "REQ-ACTIVE",
    )
    frozen = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be frozen\n",
        "REQ-FROZEN",
    )

    report = check_requirement_set_consistency([active, frozen])

    assert report.result == "contradiction"
    conflicts = [c for c in report.contradictions if c.contradiction_type == "mutual_exclusion"]
    assert len(conflicts) == 1
    assert conflicts[0].requirement_ids == ["REQ-ACTIVE", "REQ-FROZEN"]
    assert [span.text for span in conflicts[0].source_spans] == [
        "state status must be active",
        "state status must be frozen",
    ]


def test_requirement_set_consistency_allows_agreeing_post_state() -> None:
    """Discrimination control: pinning the same variable to the same value is not a conflict."""
    active = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be active\n",
        "REQ-ACTIVE-1",
    )
    also_active = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be active\n",
        "REQ-ACTIVE-2",
    )

    report = check_requirement_set_consistency([active, also_active])

    assert report.result == "valid"
    assert report.contradictions == []


def test_requirement_set_consistency_action_order_conflict() -> None:
    """One requirement requires an action to succeed, another to be rejected, under one condition."""
    succeed = _set_ir(
        "requirement state_precondition:\n"
        "scope operation\n"
        "when actor is approved\n"
        "then operation must succeed\n",
        "REQ-SUCCEED",
    )
    reject = _set_ir(
        "requirement state_precondition:\n"
        "scope operation\n"
        "when actor is approved\n"
        "then operation must reject before settled\n",
        "REQ-REJECT",
    )

    report = check_requirement_set_consistency([succeed, reject])

    assert report.result == "contradiction"
    conflicts = [
        c for c in report.contradictions if c.contradiction_type == "action_order_conflict"
    ]
    assert len(conflicts) == 1
    assert conflicts[0].requirement_ids == ["REQ-SUCCEED", "REQ-REJECT"]
    assert [span.text for span in conflicts[0].source_spans] == [
        "operation must succeed",
        "operation must reject before settled",
    ]


def test_requirement_set_consistency_skips_conflicts_across_scopes() -> None:
    """Quantifier-scope control: obligations on different scopes address different state, so a bound
    conflict across two scopes is not a contradiction (the v3 grammar has no scope subsumption)."""
    reserve = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-RESERVE",
    )
    vault = _set_ir(
        "requirement numeric_invariant:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then keep collateral <= 5\n",
        "REQ-VAULT",
    )

    report = check_requirement_set_consistency([reserve, vault])

    assert report.result == "valid"
    assert report.contradictions == []


def test_requirement_set_consistency_temporal_upper_bounds_are_not_conflict() -> None:
    """Temporal control: 'within N' is an upper bound only, so two temporal obligations can always
    both hold (the tighter wins) and never conflict across requirements."""
    six_hours = _set_ir(
        "requirement bounded_temporal:\n"
        "scope settlement\n"
        "when actor is approved\n"
        "then emit Settled within 6 hours\n",
        "REQ-6H",
    )
    three_hours = _set_ir(
        "requirement bounded_temporal:\n"
        "scope settlement\n"
        "when actor is approved\n"
        "then emit Settled within 3 hours\n",
        "REQ-3H",
    )

    report = check_requirement_set_consistency([six_hours, three_hours])

    assert report.result == "valid"
    assert report.contradictions == []


def test_requirement_set_consistency_boolean_negation_surfaces_as_mutual_exclusion() -> None:
    """Negation control: the grammar has no negatable obligation, so a direct boolean negation
    (flag true vs flag false) surfaces through the post-state channel as mutual_exclusion — exactly
    as the taxonomy entry for `negation` states."""
    flag_true = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state flag must be true\n",
        "REQ-FLAG-TRUE",
    )
    flag_false = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state flag must be false\n",
        "REQ-FLAG-FALSE",
    )

    report = check_requirement_set_consistency([flag_true, flag_false])

    assert report.result == "contradiction"
    assert [c.contradiction_type for c in report.contradictions] == ["mutual_exclusion"]
    assert [span.text for span in report.contradictions[0].source_spans] == [
        "state flag must be true",
        "state flag must be false",
    ]


def test_cross_requirement_contradiction_taxonomy_catalogues_seven_classes() -> None:
    """The taxonomy enumerates all seven contradiction classes and marks which are deterministically
    detected at the set level; the rest carry the reason they are catalogued but not emitted."""
    taxonomy = build_cross_requirement_contradiction_taxonomy()

    by_type = {entry.contradiction_type: entry for entry in taxonomy.classes}
    assert set(by_type) == {
        "negation",
        "mutual_exclusion",
        "conditional_overlap",
        "quantifier_scope_conflict",
        "numeric_range_disjointness",
        "temporal_conflict",
        "action_order_conflict",
    }
    detected = {name for name, entry in by_type.items() if entry.detected}
    assert detected == {
        "numeric_range_disjointness",
        "mutual_exclusion",
        "action_order_conflict",
    }
    # ``handling`` disambiguates the two reasons a class is not detected: a real implemented gate
    # (conditional_overlap, decided by SMT) vs a grammar limitation. A detected=False entry is never
    # an unimplemented or skipped check.
    by_handling: dict[str, set[str]] = {}
    for name, entry in by_type.items():
        by_handling.setdefault(entry.handling, set()).add(name)
    assert by_handling["emitted"] == detected
    assert by_handling["gate"] == {"conditional_overlap"}
    assert by_handling["grammar_deferred"] == {
        "negation",
        "quantifier_scope_conflict",
        "temporal_conflict",
    }
    # detected is True exactly for the emitted classes; gate/grammar-deferred classes are False.
    assert all((entry.handling == "emitted") == entry.detected for entry in taxonomy.classes)
    # Every catalogued-but-not-detected class records why, so "not detected" is never silent.
    assert all(entry.reason for entry in taxonomy.classes if not entry.detected)


def test_requirement_contradiction_requires_source_spans() -> None:
    """A deterministic contradiction must point at the offending source text: the model rejects an
    empty span list. The set checker re-exports the same model the taxonomy module owns."""
    from pydantic import ValidationError

    from nlreq.contradiction_taxonomy import RequirementContradiction as TaxonomyContradiction
    from nlreq.system_checker import RequirementContradiction as ReexportedContradiction

    assert ReexportedContradiction is TaxonomyContradiction
    with pytest.raises(ValidationError):
        TaxonomyContradiction(
            contradiction_type="numeric_range_disjointness",
            requirement_ids=["A", "B"],
            fragments=["invariant(gte(x,10))", "invariant(lte(x,5))"],
            source_spans=[],
        )


def test_requirement_set_consistency_report_shape_is_version_pinned() -> None:
    """The report's public shape and its ``schema_version`` move together, so the contract cannot
    change silently (the iter-3 regression added ``unsupported``/``unchecked`` under a stale 0.1).
    Adding a ``result`` value, an ``UncheckedRequirement`` reason, or a top-level field must come with
    a version bump — when this fails, bump ``REQUIREMENT_SET_CONSISTENCY_SCHEMA_VERSION`` and update
    these expectations deliberately, rather than ship a changed report under an old version."""
    schema = RequirementSetConsistencyReport.model_json_schema()

    assert schema["properties"]["schema_version"]["const"] == "0.2"
    assert set(schema["properties"]) == {
        "schema_version",
        "result",
        "contradictions",
        "unchecked",
    }
    assert set(schema["properties"]["result"]["enum"]) == {
        "valid",
        "contradiction",
        "unsupported",
    }
    # The two embedded models ride in the report's public shape, so their fields and enums are part
    # of the contract too: a new emitted contradiction class or a new field must bump the version.
    contradiction = schema["$defs"]["RequirementContradiction"]
    assert set(contradiction["properties"]) == {
        "contradiction_type",
        "requirement_ids",
        "fragments",
        "source_spans",
    }
    assert set(contradiction["properties"]["contradiction_type"]["enum"]) == {
        "numeric_range_disjointness",
        "mutual_exclusion",
        "action_order_conflict",
    }
    unchecked = schema["$defs"]["UncheckedRequirement"]
    assert set(unchecked["properties"]) == {
        "requirement_ids",
        "reason",
        "detail",
        "refusal_code",
        "source_spans",
    }
    assert set(unchecked["properties"]["reason"]["enum"]) == {
        "lowering_refused",
        "lowering_needs_review",
        "contradiction_without_source_span",
        "premise_overlap_undecidable",
    }


def test_cross_requirement_emitted_classes_and_reasons_stay_synchronized() -> None:
    """The emitted-class set and the unchecked-reason set are each declared in more than one place,
    and those declarations must not drift apart. The emitted classes live in the
    ``CrossRequirementContradictionType`` Literal (which the report model uses) AND in the hand-built
    taxonomy's ``handling == "emitted"`` entries; the unchecked reasons live in the
    ``UncheckedRequirementReason`` Literal and surface in the report schema. Adding a class or reason
    to one declaration but not the others is the drift that lets the docs and code disagree, so pin
    the independent declarations equal to each other. The version-pinning test above guards the
    *values*; this guards their *mutual consistency*, anchored on the Literal type rather than a
    fourth hardcoded copy."""
    from typing import get_args

    from nlreq.contradiction_taxonomy import (
        CrossRequirementContradictionType,
        UncheckedRequirementReason,
    )

    taxonomy = build_cross_requirement_contradiction_taxonomy()
    emitted_in_taxonomy = {
        entry.contradiction_type for entry in taxonomy.classes if entry.handling == "emitted"
    }
    schema = RequirementSetConsistencyReport.model_json_schema()
    report_contradiction_types = set(
        schema["$defs"]["RequirementContradiction"]["properties"]["contradiction_type"]["enum"]
    )
    report_unchecked_reasons = set(
        schema["$defs"]["UncheckedRequirement"]["properties"]["reason"]["enum"]
    )

    # The emitted-class set has three independent declarations — the Literal type, the taxonomy's
    # hand-built ``emitted`` entries, and the report enum — and all three must agree.
    assert (
        set(get_args(CrossRequirementContradictionType))
        == emitted_in_taxonomy
        == report_contradiction_types
    )
    # The report's unchecked-reason surface must expose exactly the declared reason Literal: a reason
    # added to the Literal that the report stops surfacing (or the reverse) is a silent contract break.
    assert set(get_args(UncheckedRequirementReason)) == report_unchecked_reasons


def test_requirement_set_consistency_conditional_overlap_subset_premises() -> None:
    """Conditional-overlap gate (SMT): two requirements whose premises overlap but are not identical
    still co-occur when their conjunction is satisfiable (``approved`` holds, and ``approved`` plus
    ``amount >= 5`` holds together when amount is large enough), so their conflicting numeric bounds
    ARE a contradiction. The old equal-signatures gate skipped this pair — different premise
    signatures — and falsely reported the set valid; the satisfiability gate clears the overlap and
    flags the conflict."""
    floor = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved and amount >= 5\n"
        "then keep collateral <= 5\n",
        "REQ-CEILING",
    )

    report = check_requirement_set_consistency([floor, ceiling])

    assert report.result == "contradiction"
    assert [c.contradiction_type for c in report.contradictions] == ["numeric_range_disjointness"]
    assert report.contradictions[0].requirement_ids == ["REQ-FLOOR", "REQ-CEILING"]
    assert [span.text for span in report.contradictions[0].source_spans] == [
        "keep collateral >= 10",
        "keep collateral <= 5",
    ]
    assert report.unchecked == []


def test_requirement_set_consistency_skips_jointly_unsatisfiable_premises() -> None:
    """Conditional-overlap control: premises that share a scope but are jointly unsatisfiable
    (``amount >= 10`` in one, ``amount <= 5`` in the other) can never both hold, so even directly
    conflicting obligations are NOT a contradiction — the satisfiability gate declines the pair
    rather than block a set whose conflicting rules never fire together."""
    floor = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved and amount >= 10\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved and amount <= 5\n"
        "then keep collateral <= 5\n",
        "REQ-CEILING",
    )

    report = check_requirement_set_consistency([floor, ceiling])

    assert report.result == "valid"
    assert report.contradictions == []
    assert report.unchecked == []


def test_requirement_set_consistency_flags_independent_co_occurring_premises() -> None:
    """The satisfiability gate flags independent premises that can both hold, not only identical or
    subset-compatible ones: ``actor approved`` and ``actor confirmed`` are distinct conditions whose
    conjunction is satisfiable, so two requirements pinning the same variable to different values
    under them DO conflict (both obligations are required whenever both conditions hold). This breadth
    is intentional — soundness comes from the encoding declining genuinely impossible conjunctions,
    not from restricting the gate to identical premises."""
    approved = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be active\n",
        "REQ-APPROVED",
    )
    confirmed = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is confirmed\n"
        "then state status must be frozen\n",
        "REQ-CONFIRMED",
    )

    report = check_requirement_set_consistency([approved, confirmed])

    assert report.result == "contradiction"
    assert [c.contradiction_type for c in report.contradictions] == ["mutual_exclusion"]
    assert report.contradictions[0].requirement_ids == ["REQ-APPROVED", "REQ-CONFIRMED"]
    assert report.unchecked == []


def test_requirement_set_consistency_undecidable_premise_overlap_fails_closed() -> None:
    """Fail closed on an UNDECIDABLE premise overlap: one requirement's premise has no SMT encoding
    (an opaque named-set membership, ``actor is in allowlist``), so whether the two premises co-occur
    cannot be decided. The obligations conflict on a shared scope (status active vs frozen), so the
    pair is neither a proven contradiction nor safe to drop — it is surfaced as
    ``premise_overlap_undecidable`` and the set is ``unsupported``. The old equal-signatures fallback
    returned ``valid`` here, silently hiding a possible contradiction (the iter-3 fail-open miss)."""
    allowlisted = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is in allowlist\n"
        "then state status must be active\n",
        "REQ-ALLOWLISTED",
    )
    approved = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be frozen\n",
        "REQ-APPROVED",
    )

    report = check_requirement_set_consistency([allowlisted, approved])

    assert report.result == "unsupported"
    assert report.contradictions == []
    assert len(report.unchecked) == 1
    entry = report.unchecked[0]
    assert entry.reason == "premise_overlap_undecidable"
    assert entry.requirement_ids == ["REQ-ALLOWLISTED", "REQ-APPROVED"]
    # The finding points at both the conflicting obligations and the premises whose overlap could
    # not be decided, so the undecidable pair can be reviewed by hand.
    span_texts = {span.text for span in entry.source_spans}
    assert {"state status must be active", "state status must be frozen"} <= span_texts
    assert {"actor is in allowlist", "actor is approved"} <= span_texts


def test_requirement_set_consistency_identical_opaque_premises_are_compared() -> None:
    """Identical undecidable premises trivially co-occur, so the exact-signature fallback still proves
    co-occurrence: two requirements both gated on ``actor is in allowlist`` (an opaque membership the
    SMT encoder cannot express) that pin the same variable to different values ARE a definite
    contradiction, not merely undecidable. This is the sound half of the undecidable fallback — only
    a *differing* unencodable premise becomes ``premise_overlap_undecidable``."""
    active = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is in allowlist\n"
        "then state status must be active\n",
        "REQ-ACTIVE",
    )
    frozen = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is in allowlist\n"
        "then state status must be frozen\n",
        "REQ-FROZEN",
    )

    report = check_requirement_set_consistency([active, frozen])

    assert report.result == "contradiction"
    assert [c.contradiction_type for c in report.contradictions] == ["mutual_exclusion"]
    assert report.contradictions[0].requirement_ids == ["REQ-ACTIVE", "REQ-FROZEN"]
    assert report.unchecked == []


def test_requirement_set_consistency_undecidable_premises_without_conflict_stay_valid() -> None:
    """Discrimination control for the undecidable path: an unencodable premise is surfaced only when
    the obligations actually conflict. Two requirements with an opaque membership premise and a
    predicate premise that AGREE on the post-state (both ``status must be active``) impose no
    conflicting obligation, so nothing is flagged and the set is ``valid`` — the undecidable overlap
    does not blanket-refuse every opaque-premise pair."""
    allowlisted = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is in allowlist\n"
        "then state status must be active\n",
        "REQ-ALLOWLISTED",
    )
    approved = _set_ir(
        "requirement state_postcondition:\n"
        "scope vault\n"
        "when actor is approved\n"
        "then state status must be active\n",
        "REQ-APPROVED",
    )

    report = check_requirement_set_consistency([allowlisted, approved])

    assert report.result == "valid"
    assert report.contradictions == []
    assert report.unchecked == []


def test_requirement_set_consistency_spanless_conflict_fails_closed() -> None:
    """Fail closed on a sourceless conflict: a detected obligation conflict whose binding fragment
    carries no source span is not silently dropped (which would mark a real contradiction as a
    consistent set) — it becomes an ``unchecked`` outcome so the set is not cleared. Well-formed DSL
    always attaches spans, so the path is exercised by stripping a fragment's spans directly."""
    from nlreq.contradiction_taxonomy import detect_cross_requirement_contradictions
    from nlreq.formal_claim import build_formal_claim

    active = build_formal_claim(
        _set_ir(
            "requirement state_postcondition:\nscope vault\nwhen actor is approved\n"
            "then state status must be active\n",
            "REQ-ACTIVE",
        )
    ).formal_claim
    frozen = build_formal_claim(
        _set_ir(
            "requirement state_postcondition:\nscope vault\nwhen actor is approved\n"
            "then state status must be frozen\n",
            "REQ-FROZEN",
        )
    ).formal_claim
    assert active is not None and frozen is not None
    # Strip REQ-FROZEN's obligation spans so the detected conflict cannot be tied to source text.
    frozen_spanless = frozen.model_copy(
        update={
            "obligations": [o.model_copy(update={"source_spans": []}) for o in frozen.obligations]
        }
    )

    decision = detect_cross_requirement_contradictions([active, frozen_spanless])

    assert decision.contradictions == []
    assert len(decision.unchecked) == 1
    entry = decision.unchecked[0]
    assert entry.reason == "contradiction_without_source_span"
    assert sorted(entry.requirement_ids) == ["REQ-ACTIVE", "REQ-FROZEN"]


def test_requirement_set_consistency_unsupported_when_requirement_cannot_lower() -> None:
    """Fail closed: a requirement that cannot be lowered to a formal claim is not silently dropped
    (which would let a partially-checked set read as ``valid``). The set is ``unsupported`` and the
    requirement is named in ``unchecked`` with its lowering refusal code."""
    good = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-GOOD",
    )
    unlowerable = _unlowerable_ir("REQ-BAD")

    report = check_requirement_set_consistency([good, unlowerable])

    assert report.result == "unsupported"
    assert report.contradictions == []
    assert len(report.unchecked) == 1
    entry = report.unchecked[0]
    assert entry.requirement_ids == ["REQ-BAD"]
    assert entry.reason == "lowering_refused"
    assert entry.refusal_code == "NLR-SEMANTIC-UNSUPPORTED"


def test_requirement_set_consistency_reports_contradiction_alongside_unchecked() -> None:
    """A definite contradiction among the requirements that lowered is still reported even when
    another requirement could not be lowered; the unlowerable one is additionally tracked in
    ``unchecked`` so the report never hides that the set was only partially decided."""
    floor = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral <= 5\n",
        "REQ-CEILING",
    )
    unlowerable = _unlowerable_ir("REQ-BAD")

    report = check_requirement_set_consistency([floor, ceiling, unlowerable])

    assert report.result == "contradiction"
    assert [c.contradiction_type for c in report.contradictions] == ["numeric_range_disjointness"]
    assert [u.requirement_ids for u in report.unchecked] == [["REQ-BAD"]]


def test_requirement_set_consistency_cli_fails_closed(tmp_path: Path, capsys) -> None:
    """The CLI exits non-zero on a non-valid set — a proven contradiction OR a set it could not
    fully decide (``unsupported``) — so a CI gate never passes on an inconsistent or
    incompletely-checked set; a cleanly consistent set exits zero."""

    def write(ir, name: str) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
        return path

    floor = _set_ir(
        "requirement numeric_invariant:\nscope reserve\nwhen actor is approved\n"
        "then keep collateral >= 10\n",
        "REQ-FLOOR",
    )
    ceiling_conflict = _set_ir(
        "requirement numeric_invariant:\nscope reserve\nwhen actor is approved\n"
        "then keep collateral <= 5\n",
        "REQ-CEILING",
    )
    ceiling_ok = _set_ir(
        "requirement numeric_invariant:\nscope reserve\nwhen actor is approved\n"
        "then keep collateral <= 50\n",
        "REQ-CEILING-OK",
    )

    contradiction_code = main(
        ["requirement-set-consistency", str(write(floor, "f1.json")), str(write(ceiling_conflict, "c1.json"))]
    )
    assert contradiction_code == 1
    assert json.loads(capsys.readouterr().out)["result"] == "contradiction"

    unsupported_code = main(
        ["requirement-set-consistency", str(write(floor, "f2.json")), str(write(_unlowerable_ir("REQ-BAD"), "bad.json"))]
    )
    assert unsupported_code == 1
    assert json.loads(capsys.readouterr().out)["result"] == "unsupported"

    valid_code = main(
        ["requirement-set-consistency", str(write(floor, "f3.json")), str(write(ceiling_ok, "ok.json"))]
    )
    assert valid_code == 0
    assert json.loads(capsys.readouterr().out)["result"] == "valid"


def _unlowerable_ir(requirement_id: str):
    """A v2 IR that parses but whose formal-claim lowering refuses: a well-formed requirement whose
    semantic root declares an unsupported ``requirement_class``, so ``build_formal_claim`` returns
    ``refused`` (NLR-SEMANTIC-UNSUPPORTED). Used to exercise the fail-closed path without needing a
    malformed document the DSL parser would reject before lowering."""
    base = _set_ir(
        "requirement numeric_invariant:\n"
        "scope reserve\n"
        "when actor is approved\n"
        "then keep collateral >= 10\n",
        requirement_id,
    )
    bad_root = base.semantic_ir.model_copy(
        update={
            "metadata": {**base.semantic_ir.metadata, "requirement_class": "unsupported_class"}
        }
    )
    return base.model_copy(update={"semantic_ir": bad_root})


# ---------------------------------------------------------------------------
# PB-1 solver-backed S ∧ R: a real reviewed spec S is composed into the lowered
# requirement R and a real model checker verifies S ∧ R. The reviewed S pins the
# authorization predicates R leaves abstract (the shared-predicate coupling that
# makes the check non-vacuous) and declares a named system invariant.
# ---------------------------------------------------------------------------

APALACHE = shutil.which("apalache-mc")

# The S ∧ R command is owned by system_checker (single source of truth); these tests check
# the same command the default gate and the retained benchmark corpus run.
_APALACHE_COMMAND = list(APALACHE_S_AND_R_COMMAND)


def _reviewed_s_spec_text() -> str:
    """Reviewed system spec S: interprets both authorization predicates and declares
    a named system invariant, so the composed S ∧ R is grounded and non-vacuous."""
    return (
        "---- MODULE RedemptionSystem ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "\\* System invariant: authorization defaults closed.\n"
        'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
        "====\n"
    )


def _reviewed_s_registry(
    tmp_path: Path,
    *,
    spec_text: str | None = None,
    invariants: tuple[str, ...] = ("SystemDefaultsClosed",),
    init_op: str | None = None,
    next_op: str | None = None,
) -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "RedemptionSystem.tla").write_text(
        spec_text if spec_text is not None else _reviewed_s_spec_text()
    )
    entry: dict[str, object] = {
        "spec_id": "spec:redemption",
        "module_ids": ["redemption"],
        "formalism": "tla",
        "path": "specs/RedemptionSystem.tla",
        "version": "1",
        "review_status": "reviewed",
        "freshness": "fresh",
        "invariants": list(invariants),
    }
    if init_op is not None:
        entry["init_op"] = init_op
    if next_op is not None:
        entry["next_op"] = next_op
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [entry],
        }
    )


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_s_and_r_compatible_requirement_is_valid(tmp_path: Path) -> None:
    """SP2-B: a requirement compatible with S yields a real Apalache 'valid'.

    R's premise is Pred_authorized, which S pins FALSE; the obligation is vacuously
    satisfied, so no reachable state violates the conjoined invariant.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert result.result.backend == "solver_system_checker"
    assert result.result.evidence_level.value == "BOUNDED_CHECKED"
    assert "RequirementHolds" in result.result.details["preserved_invariants"]
    assert "SystemDefaultsClosed" in result.result.details["preserved_invariants"]
    assert result.result.details["bound_predicates"] == ["Pred_authorized"]


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_s_and_r_contradicting_requirement_is_counterexample(
    tmp_path: Path,
) -> None:
    """SP2-B: a requirement that contradicts S yields a real Apalache counterexample.

    ¬R's premise is Pred_not_authorized, which S pins TRUE; the obligation fires and
    the transition system reaches "accepted", violating the conjoined invariant.
    Same S as the compatible-sibling test — the only change is the requirement.
    """
    ir = _negation_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "counterexample", result.result.details
    assert result.counterexamples
    assert result.counterexamples[0].backend == "solver_system_checker"


# state_precondition (PA-1): the affirmative dual of authorization_precondition. S interprets both
# approval predicates and declares a named invariant, so the stateless-S product is grounded.
_STATE_PRECONDITION_S_SPEC = (
    "---- MODULE RedemptionSystem ----\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_approved(a) == TRUE\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_not_approved(a) == FALSE\n"
    "\\* System invariant: approval defaults closed.\n"
    'SystemDefaultsClosed == Pred_not_approved("actor") = FALSE\n'
    "====\n"
)


def _state_precondition_ir(premise: str, requirement_id: str):
    return DslV3Parser().parse_ir(
        "requirement state_precondition:\n"
        "scope operation\n"
        f"when {premise}\n"
        "then operation must succeed\n",
        requirement_id=requirement_id,
        title="State precondition",
    )


def _state_precondition_impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["operation"],
        affected_modules=["redemption"],
    )


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_state_precondition_compatible_is_valid(tmp_path: Path) -> None:
    """PA-1: a state_precondition compatible with S yields a real Apalache 'valid'.

    R's premise is Pred_not_approved, which S pins FALSE; the 'must succeed' obligation is
    vacuously satisfied, so no reachable state lets the action fail while the precondition holds.
    """
    ir = _state_precondition_ir("actor is not approved", "REQ-SP-COMPAT")
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path, spec_text=_STATE_PRECONDITION_S_SPEC),
        impact=_state_precondition_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert result.result.backend == "solver_system_checker"
    assert result.result.evidence_level.value == "BOUNDED_CHECKED"
    assert "RequirementHolds" in result.result.details["preserved_invariants"]
    assert result.result.details["bound_predicates"] == ["Pred_not_approved"]


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_state_precondition_contradiction_is_counterexample(tmp_path: Path) -> None:
    """PA-1: a state_precondition that contradicts S yields a real Apalache counterexample.

    ¬R's premise is Pred_approved, which S pins TRUE; the obligation 'must succeed' fires and the
    harness can still reach "failed", violating the conjoined invariant. Same S as the compatible
    sibling — the only change is the premise polarity, so the two lower to checker-distinguishable
    modules (one valid, one counterexample).
    """
    ir = _state_precondition_ir("actor is approved", "REQ-SP-CONTRA")
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path, spec_text=_STATE_PRECONDITION_S_SPEC),
        impact=_state_precondition_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "counterexample", result.result.details
    assert result.counterexamples
    assert result.counterexamples[0].backend == "solver_system_checker"


def test_solver_backed_command_depth_matches_recorded_bounds(tmp_path: Path) -> None:
    """The executed ``--length`` is rendered from the same budget recorded in ``bounds``.

    Regression for the depth-provenance gap: the S ∧ R command used to hardcode ``--length=6``
    while ``bounds`` recorded the caller's ``max_depth`` separately, so a run could claim one
    depth in metadata while the checker searched another. With a non-default depth (9), the
    rendered command and the recorded bounds must agree, and the ``{max_depth}`` token must be
    substituted (never executed raw). Tool-free: composition succeeds and the command/bounds are
    recorded regardless of the (deliberately absent) checker binary, so this needs no Apalache.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=9),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=["apalache-mc-not-installed", *list(APALACHE_S_AND_R_COMMAND)[1:]],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    command = result.result.details["command"]
    assert "--length=9" in command, command
    assert "--length={max_depth}" not in command, command
    assert result.result.details["bounds"]["max_depth"] == 9


def test_solver_backed_default_depth_is_recorded_when_budget_omits_it(tmp_path: Path) -> None:
    """With no caller depth, the rendered ``--length`` and recorded ``bounds`` both fall back to
    the same DEFAULT_S_AND_R_DEPTH — never a silent depth the run does not claim."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=["apalache-mc-not-installed", *list(APALACHE_S_AND_R_COMMAND)[1:]],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert f"--length={DEFAULT_S_AND_R_DEPTH}" in result.result.details["command"]
    assert result.result.details["bounds"]["max_depth"] == DEFAULT_S_AND_R_DEPTH


def test_solver_backed_refuses_spec_without_declared_invariant(tmp_path: Path) -> None:
    """A reviewed S that declares no invariant cannot make S ∧ R non-trivial — refuse.

    Replaces the prior PB-4 guard: the refusal is now grounded in the composition
    (no system invariant to preserve), not a 'pending implementation' marker.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path, invariants=()),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "no_system_invariant"
    # Refusal happens before composition runs the checker — no artifacts written.
    assert not (tmp_path / "artifacts").exists()


def test_solver_backed_refuses_when_spec_omits_required_predicate(tmp_path: Path) -> None:
    """S declares an invariant but does not interpret the predicate R depends on — refuse.

    Without a concrete Pred_authorized definition the composed module has an undefined
    operator; the composition refuses rather than emit an unrunnable module.
    """
    ir = _authz_ir()
    spec_text = (
        "---- MODULE RedemptionSystem ----\n"
        "SystemSafety == TRUE\n"
        "====\n"
    )
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(
            tmp_path, spec_text=spec_text, invariants=("SystemSafety",)
        ),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "undefined_predicate"
    assert not (tmp_path / "artifacts").exists()


def test_solver_backed_refuses_operator_name_collision(tmp_path: Path) -> None:
    """S declares an operator whose name shadows a requirement operator — refuse.

    Honors the namespacing rule: the requirement projection's operators are not
    silently overridden by a system spec that reuses their names.
    """
    ir = _authz_ir()
    spec_text = (
        "---- MODULE RedemptionSystem ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "Obligation == TRUE\n"
        'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
        "====\n"
    )
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(
            tmp_path, spec_text=spec_text, invariants=("SystemDefaultsClosed",)
        ),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "operator_name_collision"
    assert not (tmp_path / "artifacts").exists()


def test_solver_backed_numeric_invariant_refuses_without_stateful_spec(tmp_path: Path) -> None:
    """A numeric_invariant now LOWERS (PB-4), but the default solver-backed S ∧ R still returns
    ``unsupported`` when no reviewed S can ground it — the honesty moved from translation to the
    composition's soundness guard, not away.

    The obligation is a numeric invariant over a state variable; checking it needs a stateful S that
    DECLARES and evolves that variable. The default reviewed S here is stateless (no init_op/next_op),
    so the composition refuses with ``numeric_invariant_requires_stateful_spec`` and the solver path
    surfaces ``unsupported`` — no false S ∧ R evidence. (Comparison premises are discharged separately
    by the SMT backends; this is only the S ∧ R obligation route.)
    """
    from nlreq.dsl_v3 import DslV3Parser

    ir = DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope redemption\n"
        "when collateral >= 10 and collateral <= 50\n"
        "then keep collateral >= 1\n",
        requirement_id="REQ-SYS-NUMERIC",
        title="Numeric invariant",
    )
    lowered = lower_ir_v2_to_tla(ir)
    # The lowering is now non-vacuous, not refused — the honesty has moved to the composition.
    assert lowered.status == "lowered"
    assert lowered.content is not None

    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "numeric_invariant_requires_stateful_spec"
    assert result.result.details["mode"] == "solver_backed"
    # The composition refused before the checker runs — no artifacts written.
    assert not (tmp_path / "artifacts").exists()


def _stateful_s_registry(tmp_path: Path) -> SystemSpecRegistry:
    """Registry with the reviewed stateful S (Case B: its own SInit/SNext)."""
    return _reviewed_s_registry(
        tmp_path,
        spec_text=_STATEFUL_SPEC,
        invariants=("AuthorizationDefaultsClosed",),
        init_op="SInit",
        next_op="SNext",
    )


def test_solver_backed_narrowing_path_writes_narrowing_module(tmp_path: Path) -> None:
    """A reviewed S that brings its own transition system composes end-to-end as a NARROWING
    (Case B) — it is no longer refused. The artifact on disk uses S's own Init/Next as the
    sole state machine and conjoins R's obligation as a state invariant; R contributes no
    transitions and no harness variable."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_stateful_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid"
    assert result.result.details["mode"] == "solver_backed"
    module_path = tmp_path / "artifacts" / "REQ_SYS_AUTHZ_S_AND_R.tla"
    assert module_path.is_file()
    composed = module_path.read_text()
    # S's own transitions are the only state machine; R adds none and the harness is gone.
    assert "Init == SInit\n" in composed
    assert "Next == SNext\n" in composed
    assert "Inv == AuthorizationDefaultsClosed /\\ R_Requirement\n" in composed
    assert "R_Requirement == Pred_authorized(wallet) => ~Pred_finalize_redemption(wallet)" in composed
    assert "NLRState" not in composed
    assert "SystemSpecAssumptions" not in composed


# Reviewed stateful S for the numeric_invariant narrowing: it declares and EVOLVES an Int state
# variable `collateral` (single-line typed form, which the composition re-emits as Apalache's block
# form), decrementing it from 25 toward 0. The numeric invariant binds against this real variable.
_NUMERIC_STATEFUL_SPEC = (
    "---- MODULE ReserveCollateral ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Int;\n"
    "VARIABLE collateral\n\n"
    "\\* System invariant: collateral never goes negative.\n"
    "CollateralNonNegative == collateral >= 0\n"
    "SInit == collateral = 25\n"
    "SNext == \\/ (collateral > 0 /\\ collateral' = collateral - 1)\n"
    "         \\/ UNCHANGED collateral\n"
    "====\n"
)


def _numeric_stateful_s_registry(tmp_path: Path) -> SystemSpecRegistry:
    """Registry with the reviewed numeric stateful S (Case B): its own SInit/SNext over `collateral`."""
    return _reviewed_s_registry(
        tmp_path,
        spec_text=_NUMERIC_STATEFUL_SPEC,
        invariants=("CollateralNonNegative",),
        init_op="SInit",
        next_op="SNext",
    )


def _numeric_invariant_ir(obligation_clause: str):
    """A numeric_invariant requirement bounding `collateral` to [10, 50] and keeping the obligation."""
    from nlreq.dsl_v3 import DslV3Parser

    return DslV3Parser().parse_ir(
        "requirement numeric_invariant:\n"
        "scope redemption\n"
        "when collateral >= 10 and collateral <= 50\n"
        f"then keep {obligation_clause}\n",
        requirement_id="REQ-SYS-NUMERIC",
        title="Numeric invariant",
    )


def _itf_int(value: object) -> int | None:
    """Extract an integer from an Apalache ITF cell, which may be a bare int or ``{'#bigint': '19'}``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict) and "#bigint" in value:
        return int(value["#bigint"])
    return None


def _itf_traces_under(artifact_dir: Path) -> list[dict]:
    """Load every Apalache ITF counterexample trace written under an artifact dir."""
    traces = []
    for path in sorted(artifact_dir.glob("**/violation*.itf.json")):
        traces.append(json.loads(path.read_text()))
    return traces


def _numeric_invariant_proof_from_solver_result(ir, result):
    claim = build_formal_claim(ir).formal_claim
    assert claim is not None
    covered_solver_result = _cover_s_and_r_fragments(result.result, claim)
    return build_proof_object(
        requirement=ir,
        backend_results=[
            covered_solver_result,
            *smt_check_formal_claim_predicate_fragments(claim),
        ],
        dispatch=build_proof_dispatch_plan_from_formal_claim(claim),
    )


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_narrowing_compatible_requirement_is_valid(tmp_path: Path) -> None:
    """SP2-B (stateful S): a requirement compatible with a reviewed S that has its own
    transition system yields a real Apalache 'valid'. S's premise predicate (Pred_authorized)
    stays FALSE, so the narrowing obligation Premise => ~Pred_finalize_redemption is
    vacuously satisfied even though S does reach the 'finalized' outcome."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_stateful_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert result.result.evidence_level.value == "BOUNDED_CHECKED"
    assert "AuthorizationDefaultsClosed" in result.result.details["preserved_invariants"]
    assert "R_Requirement" in result.result.details["preserved_invariants"]
    # PB-3: a bounded result records the resolved checker and its real version. The version
    # command defaults to the pinned `apalache-mc version` even though the caller did not set
    # tool_version_command, so reproducibility metadata is never blank for a real run.
    repro = result.result.details["reproducibility"]
    assert repro["tool_version_command"] == ["apalache-mc", "version"]
    assert repro["tool_version"], "expected a non-null resolved Apalache version"
    assert repro["executable_resolved"], "expected the resolved apalache-mc path"


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_narrowing_contradicting_counterexample_shows_system_step(
    tmp_path: Path,
) -> None:
    """SP2-B (stateful S): the contradicting sibling yields a real Apalache counterexample
    whose trace shows S TAKING ITS OWN TRANSITIONS to the forbidden outcome — authPhase
    walks init→denied→finalized, so Pred_finalize_redemption fires while Pred_not_authorized
    holds. The violation is a real S behavior reachable only because S's Next steps to
    'finalized'; nothing but S's transition relation produces it. Same S as the compatible
    test."""
    ir = _negation_ir()
    artifact_dir = tmp_path / "artifacts"
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_stateful_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "counterexample", result.result.details
    assert result.counterexamples

    traces = _itf_traces_under(artifact_dir)
    assert traces, "expected a retained Apalache ITF counterexample trace"
    states = traces[0]["states"]
    phases = [state.get("authPhase") for state in states]
    # The violation is a real S behavior: S must step all the way to "finalized" (where it
    # executes the action while still unauthorized), not sit at the initial state.
    assert phases[0] == "init"
    assert "finalized" in phases[1:], f"S did not reach the forbidden outcome; authPhase was {phases!r}"


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_narrowing_no_spurious_counterexample_when_outcome_unreachable(
    tmp_path: Path,
) -> None:
    """Regression for the product-vs-narrowing bug: a reviewed S that becomes unauthorized
    but has NO transition that executes the action (Pred_finalize_redemption is never true)
    yields a real Apalache 'valid'. The premise fires (S steps to 'denied'), yet the
    obligation holds because S cannot reach the forbidden outcome. The discarded synchronous
    product reported a SPURIOUS counterexample here, because R's harness reached 'accepted'
    on its own — independent of S's transitions. The narrowing must not."""
    ir = _negation_ir()
    artifact_dir = tmp_path / "artifacts"
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(
            tmp_path,
            spec_text=_REGRESSION_SPEC,
            invariants=("AuthorizationDefaultsClosed",),
            init_op="SInit",
            next_op="SNext",
        ),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=6),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert not result.counterexamples


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_numeric_invariant_compatible_is_valid(tmp_path: Path) -> None:
    """SP2-B (numeric_invariant): a numeric invariant compatible with a reviewed stateful S yields a
    real Apalache 'valid'. S declares and decrements `collateral` from 25; within the premise band
    [10, 50] the kept obligation `collateral >= 1` always holds, so no reachable S state violates the
    conjoined invariant. The obligation binds against S's REAL variable (not a stub), checked as a
    same-state invariant over S's own Init/Next — no ghost, no Pred_*."""
    ir = _numeric_invariant_ir("collateral >= 1")
    lowered = lower_ir_v2_to_tla(ir)
    assert lowered.status == "lowered"
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=_numeric_stateful_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=10),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid", result.result.details
    assert result.result.evidence_level.value == "BOUNDED_CHECKED"
    assert "CollateralNonNegative" in result.result.details["preserved_invariants"]
    assert "R_Requirement" in result.result.details["preserved_invariants"]
    # The composed module checks the numeric invariant over S's own variable as a same-state Inv.
    module_path = tmp_path / "artifacts" / "REQ_SYS_NUMERIC_S_AND_R.tla"
    composed = module_path.read_text()
    assert "R_Requirement == collateral >= 10 /\\ collateral <= 50 => collateral >= 1" in composed
    assert "nlr_prev_premise" not in composed  # numeric is a same-state invariant: no ghost variable

    proof = _numeric_invariant_proof_from_solver_result(ir, result)
    state_invariant = next(p for p in proof.premises if p.node_kind == "state_invariant")
    comparison = [p for p in proof.premises if p.node_kind == "comparison"]
    assert comparison
    assert all(p.status == "discharged" for p in comparison)
    assert state_invariant.routed_backend == "solver_system_checker"
    assert state_invariant.status == "discharged"
    assert state_invariant.producer_id == "solver_system_checker"
    assert state_invariant.achieved_evidence == EvidenceLevel.BOUNDED_CHECKED


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_solver_backed_numeric_invariant_violating_yields_counterexample(tmp_path: Path) -> None:
    """SP2-B (numeric_invariant): the violating sibling — same S, same premise, obligation
    `collateral >= 20` — yields a real Apalache counterexample. S decrements `collateral` into the
    premise band [10, 50] at a value below 20 (e.g. 19), a reachable S state that breaks the kept
    invariant. The sibling differs from the compatible test ONLY in the obligation literal, so the
    discrimination is the bound carried through value-exactly to a real model-checker verdict."""
    ir = _numeric_invariant_ir("collateral >= 20")
    artifact_dir = tmp_path / "artifacts"
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_numeric_stateful_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        budget=FormalBackendBudget(timeout_seconds=60, max_depth=10),
        execution=FormalBackendExecution(
            checker_id="apalache",
            command=_APALACHE_COMMAND,
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "counterexample", result.result.details
    assert result.counterexamples

    traces = _itf_traces_under(artifact_dir)
    assert traces, "expected a retained Apalache ITF counterexample trace"
    collaterals = [_itf_int(state.get("collateral")) for state in traces[0]["states"]]
    # The violation is a real S behavior: S steps `collateral` into the premise band yet below the
    # kept bound (in [10, 50] and < 20), reachable only via S's own decrement transition.
    assert any(c is not None and 10 <= c <= 50 and c < 20 for c in collaterals), collaterals

    proof = _numeric_invariant_proof_from_solver_result(ir, result)
    state_invariant = next(p for p in proof.premises if p.node_kind == "state_invariant")
    assert state_invariant.routed_backend == "solver_system_checker"
    assert state_invariant.status == "blocked"
    assert state_invariant.backend_status == "counterexample"


def test_solver_backed_runs_checker_over_composed_module(tmp_path: Path) -> None:
    """The composed S ∧ R module is written and the checker subprocess runs over it.

    Uses a stub checker (deterministic, tool-free) to exercise the subprocess plumbing
    and artifact recording; the composed module text asserts the tautology is gone.
    """
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('verification successful')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "valid"
    assert result.result.details["mode"] == "solver_backed"
    module_path = tmp_path / "artifacts" / "REQ_SYS_AUTHZ_S_AND_R.tla"
    assert module_path.is_file()
    composed = module_path.read_text()
    assert "Inv == RequirementHolds /\\ SystemDefaultsClosed" in composed
    assert "SystemSpecAssumptions" not in composed
    assert "Pred_authorized(a) == FALSE" in composed


def test_solver_backed_parses_counterexample_from_checker_output(tmp_path: Path) -> None:
    """A counterexample marker in the checker subprocess output maps to a counterexample."""
    ir = _authz_ir()
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_reviewed_s_registry(tmp_path),
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "print('Counterexample: state 2 violates property')"],
            artifact_dir=(tmp_path / "artifacts").as_posix(),
        ),
    )

    assert result.result.status == "counterexample"
    assert result.counterexamples[0].backend == "solver_system_checker"
    assert result.counterexamples[0].metadata["marker"] == "counterexample"


def test_solver_backed_system_consistency_blocks_stale_specs_before_execution(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    data = registry.model_dump(mode="json")
    data["specs"][0]["freshness"] = "stale"
    artifact_dir = tmp_path / "artifacts"

    result = check_solver_backed_system_consistency(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir()),
        registry=SystemSpecRegistry.model_validate(data),
        impact=_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(
            checker_id="custom",
            command=[sys.executable, "-c", "raise SystemExit(99)"],
            artifact_dir=artifact_dir.as_posix(),
        ),
    )

    assert result.result.status == "unsupported"
    assert result.result.details["reason"] == "system specs are missing, stale, or unreviewed"
    assert not artifact_dir.exists()


def test_system_consistency_fixture_cli(tmp_path: Path, capsys) -> None:
    ir = _ir()
    lowered = lower_ir_v2_to_tla(ir)
    registry = _registry(tmp_path)
    impact = _impact()
    ir_path = tmp_path / "requirement.ir.json"
    lowered_path = tmp_path / "lowered.json"
    registry_path = tmp_path / "registry.json"
    impact_path = tmp_path / "impact.json"
    out = tmp_path / "system-result.json"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    lowered_path.write_text(json.dumps(lowered.model_dump(mode="json", exclude_none=True), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))
    impact_path.write_text(json.dumps(impact.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "system-consistency-check-fixture",
            "--requirement-ir",
            str(ir_path),
            "--lowered",
            str(lowered_path),
            "--registry",
            str(registry_path),
            "--impact",
            str(impact_path),
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "System consistency result:" in output
    assert json.loads(out.read_text())["result"]["status"] == "valid"


def test_solver_backed_system_consistency_cli(tmp_path: Path, capsys) -> None:
    ir = _authz_ir()
    lowered = lower_ir_v2_to_tla(ir)
    # A reviewed spec S is composed into R; the stub checker exercises the CLI plumbing
    # over the real composed S ∧ R module.
    registry = _reviewed_s_registry(tmp_path)
    impact = _authz_impact()
    ir_path = tmp_path / "requirement.ir.json"
    lowered_path = tmp_path / "lowered.json"
    registry_path = tmp_path / "registry.json"
    impact_path = tmp_path / "impact.json"
    out = tmp_path / "solver-system-result.json"
    artifacts = tmp_path / "artifacts"
    ir_path.write_text(json.dumps(ir.model_dump(mode="json"), indent=2))
    lowered_path.write_text(json.dumps(lowered.model_dump(mode="json", exclude_none=True), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))
    impact_path.write_text(json.dumps(impact.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "solver-system-consistency-check",
            "--requirement-ir",
            str(ir_path),
            "--lowered",
            str(lowered_path),
            "--registry",
            str(registry_path),
            "--impact",
            str(impact_path),
            "--project-root",
            str(tmp_path),
            "--artifact-dir",
            str(artifacts),
            "--checker-id",
            "custom",
            "--out",
            str(out),
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Solver-backed system consistency result:" in output
    assert json.loads(out.read_text())["result"]["status"] == "valid"


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-SYS-001", title="System check")


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def _registry(tmp_path: Path, *, marker: str = "") -> SystemSpecRegistry:
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "Redemption.tla").write_text(
        "---- MODULE Redemption ----\nRedemptionInvariant == TRUE\n" + marker + "====\n"
    )
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# Z3 in-process S∧R gate tests (PA-1)
# ---------------------------------------------------------------------------

def _authz_ir():
    """DSL v3 authorization_precondition IR: wallet is authorized."""
    from nlreq.dsl_v3 import DslV3Parser
    return DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-SYS-AUTHZ",
        title="Authorization precondition",
    )


def _negation_ir():
    """DSL v3 authorization_precondition IR: wallet is not authorized (negation of _authz_ir).

    Predicate name is 'not_authorized' (DSL tokenizes "not authorized" → Pred_not_authorized).
    """
    from nlreq.dsl_v3 import DslV3Parser
    return DslV3Parser().parse_ir(
        "requirement authorization_precondition: scope redemption "
        "when wallet is not authorized then finalize_redemption must reject before rejected.",
        requirement_id="REQ-SYS-AUTHZ-NEG",
        title="Authorization precondition negation",
    )


def _z3_registry(tmp_path: Path, *, spec_content: str) -> SystemSpecRegistry:
    """Registry with a single spec whose content defines Pred_* assignments for Z3 gate."""
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "SystemConstraint.tla").write_text(spec_content)
    return SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:z3-constraint",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/SystemConstraint.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )


def _authz_impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="python-source",
        language="python",
        input_symbols=["finalize_redemption"],
        affected_modules=["redemption"],
    )


def test_z3_gate_r_plus_s_returns_valid(tmp_path: Path) -> None:
    """R + S(pred=FALSE) → Z3 UNSAT → valid.

    S assigns Pred_authorized(a) = FALSE.  Under S, the violation query
    (Pred_authorized=TRUE ∧ reached=TRUE) contradicts S → UNSAT → "valid".
    This is the PA-1 gate-path evidence: R holds under the system constraint.
    """
    from nlreq.formal_lowering import lower_authorization_precondition_tla
    ir = _authz_ir()
    lowered = lower_ir_v2_to_tla(ir)
    assert lowered.status == "lowered", f"IR must lower successfully, got: {lowered}"

    # S: Pred_authorized(a) == FALSE — R holds vacuously under this constraint.
    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "valid", (
        f"R+S must return 'valid' (UNSAT under conservative S), got {result.result.status!r}"
    )
    assert result.result.backend == "solver_system_checker"
    # Z3 in-process is a propositional SMT check, not a bounded model checker.
    assert result.result.evidence_level.value == "SMT_CHECKED"
    assert result.result.details["checker_id"] == "z3"
    assert result.result.details["z3_outcome"] == "valid"


def test_z3_gate_neg_r_plus_s_returns_counterexample(tmp_path: Path) -> None:
    """¬R + S(pred=TRUE) → Z3 SAT → counterexample.

    S assigns Pred_not_authorized(a) = TRUE.  Under S, the violation query
    (Pred_not_authorized=TRUE ∧ reached=TRUE) is consistent with S → SAT → "counterexample".
    This discriminates R from ¬R: R holds under S while ¬R fails.
    """
    ir = _negation_ir()
    lowered = lower_ir_v2_to_tla(ir)
    assert lowered.status == "lowered", f"Negation IR must lower successfully, got: {lowered}"

    # S: Pred_not_authorized(a) == TRUE — ¬R's obligation fires, violation is reachable.
    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "counterexample", (
        f"¬R+S must return 'counterexample' (SAT: ¬R fails under S), got {result.result.status!r}"
    )
    assert result.result.details["z3_outcome"] == "counterexample"


def test_z3_gate_obligation_vacuous_breaks_discrimination(tmp_path: Path) -> None:
    """Mutation: Obligation == TRUE → Z3 gate returns 'unsupported' for ¬R (no discrimination).

    When the lowered module's Obligation is replaced with TRUE (vacuous regression),
    parse_obligation_predicates returns [] and _z3_check_obligation_under_s returns
    "unknown".  The gate must NOT return "counterexample" — proving it is anchored to
    the actual Obligation line, not to CONSTANT declarations.
    """
    import re
    from nlreq.translator import LoweredFormalArtifact as LFA
    from nlreq.jsonutil import sha256_text

    ir = _negation_ir()
    normal_lowered = lower_ir_v2_to_tla(ir)
    assert normal_lowered.status == "lowered"

    # Mutate: replace "Obligation == ..." with "Obligation == TRUE"
    vacuous_content = re.sub(
        r"^Obligation == .*$",
        "Obligation == TRUE",
        normal_lowered.content,
        flags=re.MULTILINE,
    )
    vacuous_lowered = LFA.model_validate(
        normal_lowered.model_copy(
            update={"content": vacuous_content, "content_hash": sha256_text(vacuous_content)}
        ).model_dump(mode="json", exclude_none=True)
    )

    # S assigns ¬R's predicates = TRUE — would normally produce "counterexample".
    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=vacuous_lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status != "counterexample", (
        "Vacuous obligation (Obligation == TRUE) must NOT produce 'counterexample' — "
        "the Z3 gate is not anchored to CONSTANT declarations alone, only the Obligation line. "
        f"Got status: {result.result.status!r}"
    )
    assert result.result.status == "unsupported", (
        f"Vacuous obligation must return 'unsupported' (unknown Z3 outcome), "
        f"got {result.result.status!r}"
    )


def test_z3_gate_vacuous_consequent_returns_unsupported(tmp_path: Path) -> None:
    """Mutation: Obligation == Pred_foo(a) => TRUE (vacuous consequent).

    The check must return 'unsupported' (unknown Z3 outcome), NOT 'counterexample'.
    _obligation_consequent_is_real detects the absent NLRState /= constraint and
    returns unknown before encoding any Z3 formulas — anchoring the check to the
    actual obligation consequent, not just the predicate name.
    """
    import re
    from nlreq.translator import LoweredFormalArtifact as LFA
    from nlreq.jsonutil import sha256_text

    ir = _negation_ir()
    normal_lowered = lower_ir_v2_to_tla(ir)
    assert normal_lowered.status == "lowered"

    # Mutate: replace real consequent with => TRUE (vacuous, obligation never fires)
    vacuous_content = re.sub(
        r"(^Obligation == .* => )NLRState /= \"accepted\"",
        r"\1TRUE",
        normal_lowered.content,
        flags=re.MULTILINE,
    )
    assert "=> TRUE" in vacuous_content, "Mutation must insert => TRUE consequent"
    vacuous_lowered = LFA.model_validate(
        normal_lowered.model_copy(
            update={"content": vacuous_content, "content_hash": sha256_text(vacuous_content)}
        ).model_dump(mode="json", exclude_none=True)
    )

    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_not_authorized(a) == TRUE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=vacuous_lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "unsupported", (
        f"Vacuous consequent (=> TRUE) must return 'unsupported', "
        f"got {result.result.status!r}"
    )


def test_z3_gate_no_step_transitions_returns_unsupported(tmp_path: Path) -> None:
    """Mutation: Next == UNCHANGED NLRState (no real transitions).

    When the Next definition has no Step_* actions, the obligation is trivially
    satisfied because NLRState never changes from 'idle'. The check must return
    'unsupported' so this structural defect does not produce a false 'valid'.
    _next_has_steps detects the absent Step_* references before encoding Z3.
    """
    import re
    from nlreq.translator import LoweredFormalArtifact as LFA
    from nlreq.jsonutil import sha256_text

    ir = _authz_ir()
    normal_lowered = lower_ir_v2_to_tla(ir)
    assert normal_lowered.status == "lowered"

    # Mutate: remove all Step_* references from Next, leaving only UNCHANGED
    stub_content = re.sub(
        r"^Next == .*$",
        "Next == UNCHANGED NLRState",
        normal_lowered.content,
        flags=re.MULTILINE,
    )
    assert "UNCHANGED NLRState" in stub_content
    stub_lowered = LFA.model_validate(
        normal_lowered.model_copy(
            update={"content": stub_content, "content_hash": sha256_text(stub_content)}
        ).model_dump(mode="json", exclude_none=True)
    )

    s_spec = (
        "---- MODULE SystemConstraint ----\n"
        "CONSTANT a\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "====\n"
    )
    registry = _z3_registry(tmp_path, spec_content=s_spec)
    result = check_solver_backed_system_consistency(
        requirement=ir,
        lowered=stub_lowered,
        registry=registry,
        impact=_authz_impact(),
        project_root=tmp_path,
        execution=FormalBackendExecution(checker_id="z3"),
    )

    assert result.result.status == "unsupported", (
        f"No-step Next definition must return 'unsupported', got {result.result.status!r}"
    )



# ---------------------------------------------------------------------------
# compose_s_and_r_module: byte-stable composition + refusal unit tests (PB-1)
# ---------------------------------------------------------------------------

_GOLDEN_LOWERED = (
    "---- MODULE Req_GOLDEN ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "CONSTANT wallet\n\n"
    "\\* @type: (Str) => Bool;\n"
    "CONSTANT Pred_authorized(_)\n\n"
    "\\* @type: Str;\n"
    "VARIABLE NLRState\n\n"
    'Init == NLRState = "idle"\n\n'
    "Step_act ==\n"
    '  /\\ NLRState = "idle"\n'
    '  /\\ NLRState\' \\in {"rejected", "accepted"}\n\n'
    "Next == Step_act \\/ UNCHANGED NLRState\n\n"
    "Premise == Pred_authorized(wallet)\n\n"
    'Obligation == Pred_authorized(wallet) => NLRState /= "accepted"\n\n'
    "RequirementHolds == Premise => Obligation\n\n"
    "====\n"
)

_GOLDEN_SPEC = (
    "---- MODULE Sys ----\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    "====\n"
)

_GOLDEN_COMPOSED = (
    "---- MODULE Req_GOLDEN_S_AND_R ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "CONSTANT\n"
    "  \\* @type: Str;\n"
    "  wallet\n\n"
    "\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    'SystemDefaultsClosed == Pred_authorized("wallet") = FALSE\n\n'
    "VARIABLE\n"
    "  \\* @type: Str;\n"
    "  NLRState\n\n"
    "\\* ===== Requirement projection R (transition system + obligation) =====\n"
    'Init == NLRState = "idle"\n\n'
    "Step_act ==\n"
    '  /\\ NLRState = "idle"\n'
    '  /\\ NLRState\' \\in {"rejected", "accepted"}\n\n'
    "Next == Step_act \\/ UNCHANGED NLRState\n\n"
    "Premise == Pred_authorized(wallet)\n\n"
    'Obligation == Pred_authorized(wallet) => NLRState /= "accepted"\n\n'
    "RequirementHolds == Premise => Obligation\n\n"
    "\\* ===== S ∧ R: requirement obligation conjoined with system invariants =====\n"
    "Inv == RequirementHolds /\\ SystemDefaultsClosed\n"
    'ConstInit == wallet = "wallet"\n'
    "====\n"
)

# A requirement projection that binds NO CONSTANT Pred_* — the shape a claim class with no
# non-vacuous S ∧ R lowering produces (e.g. a numeric_invariant, whose comparisons range over no
# predicate S interprets, lowers to translator._tla_skeleton). It declares a VARIABLE and a
# transition body, so it clears the structural-shape guards, but it shares no predicate with any S.
_VACUOUS_LOWERED = (
    "---- MODULE Req_VACUOUS ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "VARIABLE NLRState\n\n"
    "Init == NLRState = 0\n"
    "Next == UNCHANGED NLRState\n\n"
    "collateral == 0\n\n"
    "Premise == (collateral >= 10) /\\ (collateral <= 50)\n\n"
    "Obligation == collateral >= 1\n\n"
    "RequirementHolds == Premise => Obligation\n\n"
    "====\n"
)


# A reviewed S that brings its OWN transition system (Case B). authPhase walks
# "init" -> "denied" (unauthorized) -> "finalized" (the redemption is executed while
# still unauthorized — the bug the requirement forbids). Pred_authorized stays FALSE;
# Pred_not_authorized latches once denied; Pred_finalize_redemption marks the
# accepted/executed outcome. R narrows S as a state invariant, so a counterexample is
# only reachable because S actually steps to "finalized" — a real S behavior, never a
# requirement harness moving its own variable.
_STATEFUL_SPEC = (
    "---- MODULE RedemptionAuthorization ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE authPhase\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase \\in {"denied", "finalized"}\n'
    "\\* @type: (Str) => Bool;\n"
    'Pred_finalize_redemption(a) == authPhase = "finalized"\n'
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == \\/ (authPhase = "init" /\\ authPhase\' = "denied")\n'
    '         \\/ (authPhase = "denied" /\\ authPhase\' = "finalized")\n'
    '         \\/ UNCHANGED authPhase\n'
    "====\n"
)

# A reviewed S that becomes unauthorized but has NO transition that finalizes the
# redemption (Pred_finalize_redemption is never true). The narrowing yields 'valid':
# S cannot reach the forbidden outcome, so the obligation holds even though the premise
# fires. The discarded synchronous product reported a SPURIOUS counterexample here — its
# requirement harness reached "accepted" on its own, independent of S — which is exactly
# the product-vs-narrowing bug this fixture pins (see the regression test below).
_REGRESSION_SPEC = (
    "---- MODULE RedemptionAuthorization ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE authPhase\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase = "denied"\n'
    "\\* @type: (Str) => Bool;\n"
    "Pred_finalize_redemption(a) == FALSE\n"
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == (authPhase = "init" /\\ authPhase\' = "denied") \\/ UNCHANGED authPhase\n'
    "====\n"
)

# The forbidden-outcome predicate the narrowing conjoins for the authorization_precondition
# requirements below: Pred_<action>(subject) == Pred_finalize_redemption(wallet).
_OUTCOME_FINALIZE = OutcomePredicate("Pred_finalize_redemption", ("wallet",))

# Byte-stable Case B *narrowing* of _GOLDEN_LOWERED with _STATEFUL_SPEC: S's own Init/Next
# are the only state machine and R contributes a single state invariant R_Requirement ==
# Premise => ~Pred_finalize_redemption(wallet). No R harness variable, no R_Init/R_Next.
# Validated against apalache-mc 0.58.0.
_GOLDEN_NARROWING_COMPOSED = (
    "---- MODULE Req_GOLDEN_S_AND_R ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "CONSTANT\n"
    "  \\* @type: Str;\n"
    "  wallet\n\n"
    "VARIABLE\n"
    "  \\* @type: Str;\n"
    "  authPhase\n\n"
    "\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase \\in {"denied", "finalized"}\n'
    "\\* @type: (Str) => Bool;\n"
    'Pred_finalize_redemption(a) == authPhase = "finalized"\n'
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == \\/ (authPhase = "init" /\\ authPhase\' = "denied")\n'
    '         \\/ (authPhase = "denied" /\\ authPhase\' = "finalized")\n'
    '         \\/ UNCHANGED authPhase\n\n'
    "\\* ===== Requirement R narrows S: a state invariant over S's own variables. R adds\n"
    "\\* no transitions and no variable — S's Init/Next are the only state machine. The\n"
    "\\* obligation forbids S reaching the accepted/executed outcome (Pred_finalize_redemption)\n"
    "\\* while the premise holds, so a counterexample is a real S behavior — not an artifact\n"
    "\\* of a requirement harness stepping its own state. =====\n"
    "R_Requirement == Pred_authorized(wallet) => ~Pred_finalize_redemption(wallet)\n\n"
    "\\* ===== S ∧ R: S's reachable states must preserve S's invariants and R's obligation =====\n"
    "Init == SInit\n"
    "Next == SNext\n"
    "Inv == AuthorizationDefaultsClosed /\\ R_Requirement\n"
    'ConstInit == wallet = "wallet"\n'
    "====\n"
)


def test_compose_s_and_r_module_is_byte_stable() -> None:
    """The composed S ∧ R module is byte-for-byte stable and inlines the real spec
    invariant operator — not a hash comment or a SystemSpecAssumptions tautology."""
    contribution = build_system_spec_contribution(
        "spec:sys", _GOLDEN_SPEC, ["SystemDefaultsClosed"]
    )
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "composed"
    assert composed.module_text == _GOLDEN_COMPOSED
    # The spec's invariant operator is textually present (acceptance: not just a hash).
    assert "SystemDefaultsClosed == " in composed.module_text
    assert "SystemSpecAssumptions" not in composed.module_text
    assert composed.preserved_invariants == ["RequirementHolds", "SystemDefaultsClosed"]
    assert composed.bound_predicates == ["Pred_authorized"]


def test_compose_s_and_r_module_refuses_without_invariant() -> None:
    """A spec with no declared invariant cannot yield a non-vacuous S ∧ R — refuse."""
    contribution = build_system_spec_contribution("spec:sys", _GOLDEN_SPEC, [])
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.module_text is None
    assert composed.refusal_kind == "no_system_invariant"


def test_compose_s_and_r_module_refuses_operator_name_collision() -> None:
    """A spec operator that shadows a requirement operator is refused, not overridden."""
    colliding_spec = (
        "---- MODULE Sys ----\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "RequirementHolds == TRUE\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", colliding_spec, ["RequirementHolds"]
    )
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.refusal_kind == "operator_name_collision"


def test_compose_s_and_r_module_refuses_vacuous_requirement_projection() -> None:
    """A requirement projection that binds no predicate S interprets is refused, not composed.

    S declares an invariant and even interprets ``Pred_authorized``, but the vacuous projection
    binds nothing — so the composed ``Inv == RequirementHolds /\\ SystemDefaultsClosed`` would
    leave ``RequirementHolds`` evaluated over R's disconnected harness state, checking S alone.
    The same inputs compose without this guard (the structural shape guards all pass); with it they
    refuse, so a vacuous run can never be mistaken for S ∧ R evidence. Comparison/membership
    premises are discharged by the SMT backends on their own route, not here.
    """
    contribution = build_system_spec_contribution(
        "spec:sys", _GOLDEN_SPEC, ["SystemDefaultsClosed"]
    )
    composed = compose_s_and_r_module("Req_VACUOUS_S_AND_R", _VACUOUS_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.module_text is None
    assert composed.refusal_kind == "vacuous_requirement_projection"


def test_compose_s_and_r_narrowing_module_is_byte_stable() -> None:
    """A reviewed spec that brings its own transition system (init_op/next_op) composes as
    a NARROWING: S's own Init/Next are the sole state machine and R contributes a single
    state invariant R_Requirement == Premise => ~Pred_<action>. No R harness variable, no
    R_Init/R_Next. Byte-stable; not a refusal."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "composed"
    assert composed.module_text == _GOLDEN_NARROWING_COMPOSED
    # The narrowing preserves S's named invariant and the obligation invariant.
    assert composed.preserved_invariants == ["AuthorizationDefaultsClosed", "R_Requirement"]
    assert composed.bound_predicates == ["Pred_authorized", "Pred_finalize_redemption"]
    # S's own transitions are the only state machine — R adds none, and the harness is gone.
    assert "Init == SInit\n" in composed.module_text
    assert "Next == SNext\n" in composed.module_text
    assert "NLRState" not in composed.module_text
    assert "R_Init" not in composed.module_text
    assert "R_Next" not in composed.module_text


def test_compose_s_and_r_narrowing_refuses_incomplete_transition_operators() -> None:
    """A spec that declares only one of init_op/next_op has an ill-formed transition
    system — refuse rather than narrow against half a state machine."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"], next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "incomplete_transition_operators"


def test_compose_s_and_r_narrowing_refuses_undefined_transition_operator() -> None:
    """init_op/next_op naming operators the spec body does not define is refused, so a
    typo'd transition name cannot silently fall back to a vacuous machine."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="NoSuchNext",
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "undefined_transition_operator"


def test_compose_s_and_r_narrowing_refuses_spec_constant() -> None:
    """A stateful spec that declares its own CONSTANT is refused: the composition cannot pin
    it in ConstInit, so it declines rather than leave it unconstrained."""
    spec_with_constant = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "CONSTANT threshold\n\n"
        "\\* @type: Str;\n"
        "VARIABLE authPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init"\n'
        "SNext == UNCHANGED authPhase\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_with_constant, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "unsupported_spec_constant"


def test_compose_s_and_r_narrowing_refuses_variable_name_collision() -> None:
    """Two reviewed specs that declare the SAME variable are refused: the composed state
    would conflate two machines into one variable. (R no longer contributes a harness
    variable, so the collision is now strictly between system specs.)"""
    spec_a = (
        "---- MODULE SysA ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE sharedPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosedA == Pred_authorized("wallet") = FALSE\n'
        'SInitA == sharedPhase = "init"\n'
        "SNextA == UNCHANGED sharedPhase\n"
        "====\n"
    )
    spec_b = (
        "---- MODULE SysB ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE sharedPhase\n\n"
        'SystemClosedB == TRUE\n'
        'SInitB == sharedPhase = "init"\n'
        "SNextB == UNCHANGED sharedPhase\n"
        "====\n"
    )
    contributions = [
        build_system_spec_contribution(
            "spec:a", spec_a, ["SystemClosedA"], init_op="SInitA", next_op="SNextA"
        ),
        build_system_spec_contribution(
            "spec:b", spec_b, ["SystemClosedB"], init_op="SInitB", next_op="SNextB"
        ),
    ]
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, contributions,
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "variable_name_collision"


def test_compose_s_and_r_narrowing_refuses_plural_spec_constant() -> None:
    """A spec declaring its constant with the plural ``CONSTANTS`` keyword (real TLA's form for
    several names) is refused identically to the singular ``CONSTANT`` — the declaration must
    reach the ``unsupported_spec_constant`` guard, not slip into the body unexamined."""
    spec_with_constant = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "CONSTANTS threshold\n\n"
        "\\* @type: Str;\n"
        "VARIABLE authPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init"\n'
        "SNext == UNCHANGED authPhase\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_with_constant, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "unsupported_spec_constant"


def test_compose_s_and_r_narrowing_refuses_plural_ghost_variable_collision() -> None:
    """A spec declaring the narrowing's reserved ghost variable via the plural ``VARIABLES``
    keyword is refused with ``variable_name_collision`` — the plural form must reach the
    reserved-variable guard, or the post-state history bit would be conflated with S's state."""
    spec_with_ghost = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLES nlr_prev_premise\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == nlr_prev_premise = "init"\n'
        "SNext == UNCHANGED nlr_prev_premise\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_with_ghost, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "variable_name_collision"


def test_compose_s_and_r_narrowing_refuses_ghost_collision_in_second_comma_name() -> None:
    """The reserved ghost variable as the SECOND name of a comma-separated ``VARIABLES``
    declaration is still caught. This discriminates real comma-splitting from a parser that
    reads only the first identifier or treats the whole remainder as one name — the collision
    holds only if the second token is reached."""
    spec_two_vars = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "VARIABLES authPhase, nlr_prev_premise\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == FALSE\n'
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init" /\\ nlr_prev_premise = "init"\n'
        "SNext == UNCHANGED <<authPhase, nlr_prev_premise>>\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_two_vars, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "variable_name_collision"


def test_compose_s_and_r_narrowing_composes_comma_separated_variables() -> None:
    """A reviewed spec declaring several variables on one comma-separated ``VARIABLES`` line
    composes: every name is extracted and re-emitted as its own Apalache-typed VARIABLE block,
    and the original single-line declaration is consumed (not left verbatim mid-body where the
    checker's parser would reject it)."""
    spec_multi_var = (
        "---- MODULE RedemptionAuthorizationMulti ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "VARIABLES authPhase, redeemPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_not_authorized(a) == authPhase \\in {"denied", "finalized"}\n'
        "\\* @type: (Str) => Bool;\n"
        'Pred_finalize_redemption(a) == authPhase = "finalized"\n'
        "\\* System invariant: authorization defaults closed.\n"
        'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init" /\\ redeemPhase = "idle"\n'
        'SNext == \\/ (authPhase = "init" /\\ authPhase\' = "denied" /\\ UNCHANGED redeemPhase)\n'
        "         \\/ UNCHANGED <<authPhase, redeemPhase>>\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_multi_var, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "composed"
    # Both comma-separated names are extracted and re-emitted as their own typed VARIABLE blocks.
    assert "VARIABLE\n  \\* @type: Str;\n  authPhase\n" in composed.module_text
    assert "VARIABLE\n  \\* @type: Str;\n  redeemPhase\n" in composed.module_text
    # The original single-line declaration was consumed, not kept verbatim in the inlined body.
    assert "VARIABLES authPhase, redeemPhase" not in composed.module_text


def test_compose_s_and_r_narrowing_refuses_typed_multi_name_variables() -> None:
    """A single ``\\* @type:`` comment over a comma-separated ``VARIABLES`` line is refused with
    ``unsupported_spec_variable``, not silently retyped to ``Str``. One annotation cannot type
    several names — Apalache itself rejects the form ("Expected a type annotation for VARIABLE
    <second>") — so the composition refuses rather than guess that the annotation types every name
    and check the reviewed S against a changed variable surface. A real numeric/Bool spec must use
    one supported single-name ``VARIABLE`` declaration per type annotation."""
    spec_typed_multi = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Int;\n"
        "VARIABLES collateral, debt\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_finalize_redemption(a) == FALSE\n"
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        "SInit == collateral = 0 /\\ debt = 0\n"
        "SNext == UNCHANGED <<collateral, debt>>\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_typed_multi, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "unsupported_spec_variable"
    assert "single-line VARIABLE declaration" in (composed.refusal_reason or "")
    assert "block form" not in (composed.refusal_reason or "")


def test_compose_s_and_r_narrowing_refuses_undefined_outcome_predicate() -> None:
    """If the reviewed S does not interpret the forbidden-outcome predicate Pred_<action>,
    the narrowing cannot tell whether S reaches the outcome the requirement forbids, so it
    refuses rather than emit a module whose obligation references an undefined operator."""
    spec_without_outcome = (
        "---- MODULE Sys ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE authPhase\n\n"
        "\\* @type: (Str) => Bool;\n"
        "Pred_authorized(a) == FALSE\n"
        'SystemClosed == Pred_authorized("wallet") = FALSE\n'
        'SInit == authPhase = "init"\n'
        "SNext == UNCHANGED authPhase\n"
        "====\n"
    )
    contribution = build_system_spec_contribution(
        "spec:sys", spec_without_outcome, ["SystemClosed"], init_op="SInit", next_op="SNext"
    )
    composed = compose_s_and_r_module(
        "Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution],
        outcome_predicate=_OUTCOME_FINALIZE,
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "undefined_outcome_predicate"


def test_compose_s_and_r_narrowing_refuses_missing_outcome_predicate() -> None:
    """A stateful S narrowing needs the requirement's forbidden-outcome predicate. Without
    it (the requirement shape did not yield one), the composition refuses rather than emit a
    module that constrains nothing."""
    contribution = build_system_spec_contribution(
        "spec:sys", _STATEFUL_SPEC, ["AuthorizationDefaultsClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module("Req_GOLDEN_S_AND_R", _GOLDEN_LOWERED, [contribution])

    assert composed.status == "refused"
    assert composed.refusal_kind == "missing_outcome_predicate"


# ---------------------------------------------------------------------------
# state_postcondition narrowing (PB-4): the affirmed-obligation twin of the authorization
# narrowing above. The reviewed stateful S brings TWO variables — operation_status and a distinct
# approved_flag — coupled only by transition discipline: SNext grants approval (approved_flag') in
# the SAME step it accepts (operation_status' = "accepted"), never apart. So Pred_approved
# (approved_flag = TRUE) holds only in states where operation_status is already "accepted" — a real
# fact about S's transition relation, NOT a definitional identity. The narrowing conjoins the
# AFFIRMED obligation R_Requirement == Premise => Pred_operation_status("accepted") into Inv.
# Validated against apalache-mc 0.58.0: the composed module is valid; the same S with the
# requirement demanding "rejected" yields a real counterexample; and a decoupled S that grants
# approval without acceptance makes the "accepted" requirement counterexample too — so the valid
# verdict genuinely depends on S's transitions, not a tautology.
# ---------------------------------------------------------------------------
_POST_STATE_STATEFUL_SPEC = (
    "---- MODULE Operation ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE operation_status\n"
    "\\* @type: Bool;\n"
    "VARIABLE approved_flag\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_approved(a) == approved_flag = TRUE\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_operation_status(v) == operation_status = v\n"
    "\\* System invariant: the operation status stays within its reviewed value domain.\n"
    'OperationStatusClosed == operation_status \\in {"init", "accepted"}\n'
    'SInit == operation_status = "init" /\\ approved_flag = FALSE\n'
    'SNext == \\/ (operation_status = "init" /\\ operation_status\' = "accepted" /\\ approved_flag\' = TRUE)\n'
    "         \\/ UNCHANGED <<operation_status, approved_flag>>\n"
    "====\n"
)


def _post_state_ir(value: str = "accepted", requirement_id: str = "REQ-STATEPOST"):
    from nlreq.dsl_v3 import DslV3Parser

    return DslV3Parser().parse_ir(
        "requirement state_postcondition:\n"
        "scope operation\n"
        "when actor is approved\n"
        f'then state operation_status must be "{value}"\n',
        requirement_id=requirement_id,
        title="State postcondition",
    )


# Byte-stable standalone lowering of the state_postcondition. The premise predicate is an abstract
# CONSTANT a reviewed S interprets; the obligation is an abstract reached/unmet boundary over the
# harness variable — the concrete post-state value is checked by the narrowing, not this module.
_POST_STATE_LOWERED = (
    "---- MODULE Req_REQ_STATEPOST ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* Non-vacuous state_postcondition lowering.\n"
    "\\* Generated by nlreq translator 0.2; semantics: non_vacuous.\n"
    "\\* Requirement: REQ-STATEPOST\n"
    "\\* Temporal bounds: []\n\n"
    "\\* @type: Str;\n"
    "CONSTANT actor\n"
    "\\* @type: Str;\n"
    "CONSTANT operation\n\n"
    "\\* @type: (Str) => Bool;\n"
    "CONSTANT Pred_approved(_)\n\n"
    "\\* @type: Str;\n"
    "VARIABLE NLRState\n\n"
    'Init == NLRState = "nlr_init"\n\n'
    "\\* Harness: the premise does not gate the post-state, so the checker explores both\n"
    '\\* reaching it ("nlr_post_state") and not ("nlr_unmet"). The concrete post-state value\n'
    "\\* is checked against S's own state by the stateful-S narrowing; here it is an abstract\n"
    "\\* reached/unmet boundary so the standalone module stays checker-distinguishable.\n"
    "Step_reach ==\n"
    '  /\\ NLRState = "nlr_init"\n'
    '  /\\ NLRState\' \\in {"nlr_post_state", "nlr_unmet"}\n\n'
    "Next == Step_reach \\/ UNCHANGED NLRState\n\n"
    "Premise == Pred_approved(actor)\n\n"
    'Obligation == Pred_approved(actor) => NLRState = "nlr_post_state"\n\n'
    "RequirementHolds == Premise => Obligation\n\n"
    "====\n"
)

# Byte-stable Case B narrowing of _POST_STATE_LOWERED with _POST_STATE_STATEFUL_SPEC. The
# state_postcondition is a NEXT-RELATION obligation: R adds the ghost VARIABLE nlr_prev_premise
# (recording whether the premise held in the PRE-state), Next conjoins its update, and
# R_Requirement == nlr_prev_premise => Pred_operation_status("accepted") is conjoined into Inv over
# S's own Init/Next. S's two variables (operation_status, approved_flag) plus the ghost each render
# as their own Apalache-typed VARIABLE block. Validated valid (accepted) / counterexample (rejected)
# against apalache-mc 0.58.0.
_POST_STATE_NARROWING_COMPOSED = (
    "---- MODULE REQ_STATEPOST_S_AND_R ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "CONSTANT\n"
    "  \\* @type: Str;\n"
    "  actor,\n"
    "  \\* @type: Str;\n"
    "  operation\n\n"
    "VARIABLE\n"
    "  \\* @type: Str;\n"
    "  operation_status\n\n"
    "VARIABLE\n"
    "  \\* @type: Bool;\n"
    "  approved_flag\n\n"
    "VARIABLE\n"
    "  \\* @type: Bool;\n"
    "  nlr_prev_premise\n\n"
    "\\* ===== Reviewed system spec S (inlined; operators keep their names) =====\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_approved(a) == approved_flag = TRUE\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_operation_status(v) == operation_status = v\n"
    "\\* System invariant: the operation status stays within its reviewed value domain.\n"
    'OperationStatusClosed == operation_status \\in {"init", "accepted"}\n'
    'SInit == operation_status = "init" /\\ approved_flag = FALSE\n'
    'SNext == \\/ (operation_status = "init" /\\ operation_status\' = "accepted" /\\ approved_flag\' = TRUE)\n'
    "         \\/ UNCHANGED <<operation_status, approved_flag>>\n\n"
    "\\* ===== Requirement R narrows S's TRANSITIONS into a post-state obligation. R adds\n"
    "\\* one ghost VARIABLE nlr_prev_premise recording, after each step, whether the premise held in\n"
    "\\* the PRE-state (Next conjoins nlr_prev_premise' = the premise over S's unprimed state; Init\n"
    "\\* sets it FALSE). The obligation requires every step out of a premise-state of S to establish the post-state (Pred_operation_status) — checked as the state invariant\n"
    "\\* R_Requirement == nlr_prev_premise => <post-state>, so a counterexample is a real S step out\n"
    "\\* of a premise-state that fails to establish the required post-state (the strict\n"
    "\\* next-step reading). Apalache 0.58 silently false-passes a primed-variable action\n"
    "\\* invariant over a non-establishing step, so the faithful Next-relation check is this\n"
    "\\* history-variable state invariant. =====\n"
    'R_Requirement == nlr_prev_premise => Pred_operation_status("accepted")\n\n'
    "\\* ===== S ∧ R: S's reachable states must preserve S's invariants and R's obligation =====\n"
    "Init == SInit /\\ nlr_prev_premise = FALSE\n"
    "Next == SNext /\\ nlr_prev_premise' = (Pred_approved(actor))\n"
    "Inv == OperationStatusClosed /\\ R_Requirement\n"
    'ConstInit == actor = "actor" /\\ operation = "operation"\n'
    "====\n"
)


def test_lower_state_postcondition_tla_is_byte_stable() -> None:
    """The standalone state_postcondition lowering is byte-for-byte stable and non-vacuous: the
    premise predicate is an abstract CONSTANT and the obligation is a real reached/unmet boundary
    over the harness variable, not a TRUE stub."""
    lowered = lower_state_postcondition_tla(_post_state_ir())

    assert lowered == _POST_STATE_LOWERED
    assert "CONSTANT Pred_approved(_)" in lowered
    assert 'Obligation == Pred_approved(actor) => NLRState = "nlr_post_state"' in lowered
    assert "TRUE" not in lowered.split("Premise ==", 1)[1]


def test_derive_post_state_obligation_affirms_post_state_predicate() -> None:
    """The post-state obligation derives Pred_<state> with the required value as a TLA+ literal —
    the affirmed-polarity twin of derive_outcome_predicate's forbidden Pred_<action>."""
    obligation = derive_post_state_obligation(_post_state_ir().semantic_ir)

    assert obligation == PostStateObligation(
        predicate_name="Pred_operation_status", value_literal='"accepted"'
    )


def test_validate_state_postcondition_shape_accepts_and_refuses() -> None:
    """The shape validator accepts a named-predicate premise + post_state obligation and refuses a
    premise with no named predicate (which would make the narrowing antecedent vacuously TRUE)."""
    assert validate_state_postcondition_shape(_post_state_ir().semantic_ir) == []

    from nlreq.dsl_v3 import DslV3Parser

    comparison_only = DslV3Parser().parse_ir(
        "requirement state_postcondition:\n"
        "scope operation\n"
        "when balance >= 5\n"
        'then state operation_status must be "accepted"\n',
        requirement_id="REQ-STATEPOST-VACUOUS",
        title="State postcondition",
    )
    problems = validate_state_postcondition_shape(comparison_only.semantic_ir)
    assert any(kind == "no_predicate_premise" for kind, _reason, _node in problems)


def test_compose_s_and_r_narrowing_post_state_is_byte_stable() -> None:
    """A state_postcondition narrows a reviewed stateful S into a byte-stable composed module: a
    NEXT-RELATION obligation where R adds the ghost VARIABLE nlr_prev_premise (the premise's
    pre-state value), Next conjoins its update, and Inv conjoins the AFFIRMED state invariant
    nlr_prev_premise => Pred_<state>(<value>). Both the premise predicate and the post-state
    predicate are bound."""
    lowered = lower_state_postcondition_tla(_post_state_ir())
    contribution = build_system_spec_contribution(
        "spec:op", _POST_STATE_STATEFUL_SPEC, ["OperationStatusClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module(
        "REQ_STATEPOST_S_AND_R", lowered, [contribution],
        post_state_obligation=derive_post_state_obligation(_post_state_ir().semantic_ir),
    )

    assert composed.status == "composed"
    assert composed.module_text == _POST_STATE_NARROWING_COMPOSED
    # The obligation is AFFIRMED (=> Pred_...), not negated (=> ~Pred_...) like authorization, and
    # its antecedent is the ghost history bit (the premise in the PRE-state), so the check is a
    # next-step transition obligation rather than a same-state one.
    assert (
        'R_Requirement == nlr_prev_premise => Pred_operation_status("accepted")'
        in composed.module_text
    )
    assert "Next == SNext /\\ nlr_prev_premise' = (Pred_approved(actor))" in composed.module_text
    assert "=> ~" not in composed.module_text
    assert composed.preserved_invariants == ["OperationStatusClosed", "R_Requirement"]
    # Both the premise predicate AND the post-state predicate are bound, so coverage can discharge
    # both the predicate premise and the post_state obligation from one S ∧ R verdict.
    assert composed.bound_predicates == ["Pred_approved", "Pred_operation_status"]


def test_compose_s_and_r_narrowing_post_state_multi_predicate_parenthesizes_ghost_update() -> None:
    """A state_postcondition with a CONJUNCTION premise emits the ghost update with the whole
    conjunction PARENTHESIZED: ``nlr_prev_premise' = (Pred_a(x) /\\ Pred_b(x))``.

    The parens are load-bearing — TLA+ binds ``=`` (prec 5) tighter than ``/\\`` (prec 3), so
    without them ``Next`` would parse as ``(nlr_prev_premise' = Pred_a(x)) /\\ Pred_b(x)``, silently
    narrowing Next (constraining Pred_b in the transition) and masking counterexamples — a false
    pass. Single-predicate premises hide this (no conjunction, so the parens are inert), so pin the
    multi-predicate shape against a regression that drops them. Verified valid/counterexample on
    apalache-mc 0.58.0.
    """
    from nlreq.dsl_v3 import DslV3Parser

    ir = DslV3Parser().parse_ir(
        "requirement state_postcondition:\n"
        "scope operation\n"
        "when actor is approved and actor is confirmed\n"
        'then state operation_status must be "accepted"\n',
        requirement_id="REQ-STATEPOST-MULTI", title="Post-state multi",
    )
    spec = (
        "---- MODULE Operation ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Bool;\nVARIABLE approved_flag\n"
        "\\* @type: Bool;\nVARIABLE confirmed_flag\n"
        "\\* @type: Str;\nVARIABLE operation_status\n\n"
        "\\* @type: (Str) => Bool;\nPred_approved(a) == approved_flag = TRUE\n"
        "\\* @type: (Str) => Bool;\nPred_confirmed(a) == confirmed_flag = TRUE\n"
        "\\* @type: (Str) => Bool;\nPred_operation_status(v) == operation_status = v\n"
        'OperationStatusClosed == operation_status \\in {"pending", "accepted"}\n'
        'SInit == operation_status = "pending" /\\ approved_flag = TRUE /\\ confirmed_flag = TRUE\n'
        'SNext == operation_status\' = "accepted" /\\ UNCHANGED <<approved_flag, confirmed_flag>>\n'
        "====\n"
    )
    lowered = lower_state_postcondition_tla(ir)
    contribution = build_system_spec_contribution(
        "spec:op", spec, ["OperationStatusClosed"], init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module(
        "REQ_STATEPOST_MULTI_S_AND_R", lowered, [contribution],
        post_state_obligation=derive_post_state_obligation(ir.semantic_ir),
    )

    assert composed.status == "composed"
    # The whole conjunction is parenthesized on the RHS of the ghost update.
    assert (
        "Next == SNext /\\ nlr_prev_premise' = (Pred_approved(actor) /\\ Pred_confirmed(actor))"
        in composed.module_text
    )
    assert composed.bound_predicates == [
        "Pred_approved", "Pred_confirmed", "Pred_operation_status"
    ]


def test_compose_s_and_r_narrowing_post_state_refuses_undefined_predicate() -> None:
    """If the reviewed S does not interpret the post-state predicate Pred_<state>, the narrowing
    cannot tell whether S reaches the required post-state — refuse rather than reference an
    undefined operator."""
    spec_without_post_state = (
        "---- MODULE Operation ----\n"
        "EXTENDS Naturals, TLC\n\n"
        "\\* @type: Str;\n"
        "VARIABLE operation_status\n\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_approved(a) == operation_status = "accepted"\n'
        "\\* System invariant: the operation status stays within its reviewed value domain.\n"
        'OperationStatusClosed == operation_status \\in {"init", "accepted"}\n'
        'SInit == operation_status = "init"\n'
        "SNext == UNCHANGED operation_status\n"
        "====\n"
    )
    lowered = lower_state_postcondition_tla(_post_state_ir())
    contribution = build_system_spec_contribution(
        "spec:op", spec_without_post_state, ["OperationStatusClosed"],
        init_op="SInit", next_op="SNext",
    )
    composed = compose_s_and_r_module(
        "REQ_STATEPOST_S_AND_R", lowered, [contribution],
        post_state_obligation=derive_post_state_obligation(_post_state_ir().semantic_ir),
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "undefined_outcome_predicate"


def test_compose_s_and_r_module_refuses_post_state_on_stateless_spec() -> None:
    """A state_postcondition needs a reviewed STATEFUL S to reach the post-state. A stateless S
    (no init_op/next_op) is refused rather than composed into a Case A product that would evaluate
    the post-state over R's disconnected harness variable."""
    stateless_spec = (
        "---- MODULE Operation ----\n"
        "\\* @type: (Str) => Bool;\n"
        'Pred_approved(a) == TRUE\n'
        "\\* @type: (Str) => Bool;\n"
        "Pred_operation_status(v) == TRUE\n"
        'OperationStatusClosed == TRUE\n'
        "====\n"
    )
    lowered = lower_state_postcondition_tla(_post_state_ir())
    contribution = build_system_spec_contribution(
        "spec:op", stateless_spec, ["OperationStatusClosed"]
    )
    composed = compose_s_and_r_module(
        "REQ_STATEPOST_S_AND_R", lowered, [contribution],
        post_state_obligation=derive_post_state_obligation(_post_state_ir().semantic_ir),
    )

    assert composed.status == "refused"
    assert composed.refusal_kind == "state_postcondition_requires_stateful_spec"


def test_solver_result_labels_valid_run_bounded_only_with_full_backing() -> None:
    """A valid solver run defaults to BOUNDED_CHECKED only when it recorded its full bounded
    backing — the bounds it searched, the checker command, and the version of the checker the run
    resolved. A run missing any of the three has no backing for a bounded claim, so the level
    degrades to None/unverified rather than over-claim (and rather than crash the BackendResult
    guard). The real Apalache/TLC S ∧ R path records all three — the command top-level, the
    version under reproducibility — so it stays BOUNDED_CHECKED."""
    no_bounds = _solver_result("REQ-1", "valid", ["spec:sys"], {"mode": "solver_backed"})
    bounds_only = _solver_result(
        "REQ-1", "valid", ["spec:sys"], {"mode": "solver_backed", "bounds": {"max_depth": 8}}
    )
    backed = _solver_result(
        "REQ-1",
        "valid",
        ["spec:sys"],
        {
            "mode": "solver_backed",
            "bounds": {"max_depth": 8},
            "command": ["apalache-mc", "check", "Module.tla"],
            "reproducibility": {"tool_version": "apalache 0.58.0"},
        },
    )

    assert no_bounds.result.evidence_level is None
    assert bounds_only.result.evidence_level is None
    assert backed.result.evidence_level == EvidenceLevel.BOUNDED_CHECKED
