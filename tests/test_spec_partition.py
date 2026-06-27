"""Tests for Zone 1 deterministic spec partitioning (three-zone scope §4 / Work Item 1).

The completeness oracle hinges on the deterministic total segmentation: every CHARACTER in
exactly one classified segment (offsets are Python string offsets over Unicode code points, NOT
UTF-8 bytes), with no silent drop (``extracted ∪ excluded == the full segmentation``). These
tests pin that invariant, the span round-trip, per-segment classification reasons, the
single-client LLM refinement + clarify routing, the cross-provider ensemble boundary-
disagreement routing to the human queue, and the cross-provider-FAMILY diversity gate (scope §3).

All tests are CI-safe: the LLM cases use ``RecordedLlmClient`` (deterministic replay),
never a live model.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlreq.llm_client import RecordedLlmClient
from nlreq.spec_partition import (
    CandidateRule,
    PartitionFlag,
    PartitionFlagKind,
    SegmentClassification,
    SegmentKind,
    SpecPartitionArtifact,
    classify_segment,
    draft_candidate_rules,
    parse_candidate_rules_proposal,
    partition_document_deterministic,
    partition_document_with_client,
    partition_document_with_ensemble,
    partition_spec_document,
    segment_document,
    segment_text_from_bytes,
)
from nlreq.jsonutil import sha256_text
from nlreq.parser import normalize_controlled_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DOC = (
    "# Payments\n"
    "\n"
    "The system shall reject unauthorized transfers.\n"
    "\n"
    "- A transfer must not exceed the available balance.\n"
    "- See the fraud module for cross-checks.\n"
    "\n"
    "Note: this paragraph is descriptive only.\n"
    "\n"
    "## Refunds\n"
    "\n"
    "Refunds must be issued within 7 days of the request.\n"
)


def _client(partition_fixture: str) -> RecordedLlmClient:
    """A recorded partition client that replays the given candidate-rule JSON for every segment."""
    return RecordedLlmClient(fixture="", partition_fixture=partition_fixture)


def _prov(*families: str) -> list[dict[str, str]]:
    """Per-member partition provenance with distinct provider families (the diversity-gate input).

    Every ensemble caller now MUST supply ``member_provenance`` (HELPER iter-2: the ``None`` bypass
    was removed); offline recorded-client tests supply recorded distinct families here rather than
    skipping the gate.
    """
    return [
        {"role": "partition", "provider_family": family, "resolved_model": f"model-{family}"}
        for family in families
    ]


# ---------------------------------------------------------------------------
# Deterministic total segmentation (completeness oracle)
# ---------------------------------------------------------------------------


def test_segmentation_is_total_and_disjoint() -> None:
    """Every character (code point) is in exactly one segment; spans are contiguous and cover
    [0, len). Offsets are Python string (Unicode code-point) indices, NOT UTF-8 bytes — see
    ``test_segmentation_totality_and_round_trip_hold_for_non_ascii`` for the non-ASCII proof and
    ADR 0206 §3 for the contract decision."""
    segments = segment_document(_DOC)
    assert segments, "a non-empty document must produce segments"
    assert segments[0].start == 0
    assert segments[-1].end == len(_DOC)
    for previous, current in zip(segments, segments[1:]):
        assert previous.end == current.start, f"gap/overlap between {previous!r} and {current!r}"
    # Every code point accounted for exactly once: total span length equals the document length.
    total = sum(segment.end - segment.start for segment in segments)
    assert total == len(_DOC)


@pytest.mark.parametrize(
    "document",
    [
        "",  # empty document
        "\n\n\n",  # only blank lines
        "one line no newline",  # no trailing newline
        "# H\n\np1\n- a\n- b\n\np2\n",  # mixed structure
        "word " * 50,  # single long paragraph
    ],
)
def test_segmentation_totality_invariant_holds(document: str) -> None:
    """Totality holds across edge cases: union of spans == [0, len(document))."""
    segments = segment_document(document)
    if not segments:
        assert document == ""
        return
    assert segments[0].start == 0
    assert segments[-1].end == len(document)
    for previous, current in zip(segments, segments[1:]):
        assert previous.end == current.start
    assert sum(s.end - s.start for s in segments) == len(document)


def test_segment_span_round_trips_into_document() -> None:
    """For every segment, document[start:end] == segment.text (the code-point span locates the
    text; this round-trip only holds for Unicode code-point slicing, never UTF-8 byte offsets)."""
    segments = segment_document(_DOC)
    for segment in segments:
        assert _DOC[segment.start:segment.end] == segment.text


def test_list_items_are_atomic_segments() -> None:
    """Each list item is its own segment (fine-grained default candidate derivation)."""
    document = "- first must hold.\n- second must hold.\n- third must hold.\n"
    segments = segment_document(document)
    list_segments = [s for s in segments if s.kind is SegmentKind.list_item]
    assert len(list_segments) == 3
    # Atomic: no two list items merged into one segment.
    for segment in list_segments:
        assert segment.text.count("\n") == 1


def test_headings_and_separators_are_non_behavioral() -> None:
    """Structural segments (headings, blank separators) classify non-behavioral with a reason."""
    segments = segment_document(_DOC)
    for segment in segments:
        if segment.kind in (SegmentKind.heading, SegmentKind.separator):
            classification, reason = classify_segment(segment)
            assert classification is SegmentClassification.non_behavioral
            assert reason.strip()


# ---------------------------------------------------------------------------
# Per-segment classification + completeness (no silent drop)
# ---------------------------------------------------------------------------


def test_every_segment_is_classified_with_a_reason() -> None:
    """Every segment carries a classification and a non-empty reason (no unclassified characters)."""
    artifact = partition_document_deterministic(_DOC)
    assert len(artifact.segments) > 0
    for classified in artifact.segments:
        assert isinstance(classified.classification, SegmentClassification)
        assert classified.reason.strip(), f"segment {classified.index} lacks a reason"


def test_extracted_plus_excluded_equals_full_segmentation() -> None:
    """Completeness oracle: candidate source segments ∪ non-behavioral == all segments (no drop)."""
    artifact = partition_document_deterministic(_DOC)
    candidate_sources = {rule.source_segment_index for rule in artifact.candidate_rules}
    non_behavioral = {
        seg.index for seg in artifact.segments
        if seg.classification is SegmentClassification.non_behavioral
    }
    behavioral = {
        seg.index for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    }
    # Every behavioral segment produced a candidate (deterministic: one each); every other
    # segment is non-behavioral. Their union is the full set of segment indices — nothing dropped.
    assert candidate_sources == behavioral
    assert candidate_sources | non_behavioral == {seg.index for seg in artifact.segments}
    assert not (candidate_sources & non_behavioral)


def test_reference_and_note_segments_excluded_with_reason() -> None:
    """Clearly-meta prose ('See ...', 'Note:') is excluded as non-behavioral, not silently dropped."""
    artifact = partition_document_deterministic(_DOC)
    excluded_texts = {
        seg.text.strip(): seg.reason
        for seg in artifact.segments
        if seg.classification is SegmentClassification.non_behavioral
    }
    # The 'See the fraud module' list item and the 'Note:' paragraph are excluded.
    fraud = next(text for text in excluded_texts if "fraud module" in text)
    note = next(text for text in excluded_texts if text.startswith("Note:"))
    assert "reference" in excluded_texts[fraud].lower() or "not a testable requirement" in excluded_texts[fraud].lower()
    assert "not a testable requirement" in excluded_texts[note].lower()


# ---------------------------------------------------------------------------
# Deterministic path (no LLM)
# ---------------------------------------------------------------------------


def test_deterministic_partition_has_no_flags_and_one_candidate_per_behavioral() -> None:
    """Deterministic path: no LLM, no needs-review flags, one default candidate per behavioral segment."""
    artifact = partition_document_deterministic(_DOC)
    assert artifact.ensemble_members == 0
    assert artifact.needs_review == []
    behavioral_count = sum(
        1 for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    )
    assert len(artifact.candidate_rules) == behavioral_count
    # Default candidate spans are the whole segment and round-trip into the document.
    for rule in artifact.candidate_rules:
        assert _DOC[rule.span_start:rule.span_end].strip()
        assert rule.span_end > rule.span_start


def test_deterministic_artifact_records_document_hash_and_length() -> None:
    """The artifact is hash-bound to its source document (the completeness oracle's anchor)."""
    artifact = partition_document_deterministic(_DOC)
    assert artifact.document_hash == sha256_text(_DOC)
    assert artifact.document_length == len(_DOC)


def test_deterministic_path_is_reproducible() -> None:
    """The deterministic path is fully reproducible (same input → identical artifact JSON)."""
    first = partition_document_deterministic(_DOC)
    second = partition_document_deterministic(_DOC)
    assert first.model_dump() == second.model_dump()


# ---------------------------------------------------------------------------
# Single-client LLM refinement + clarify routing
# ---------------------------------------------------------------------------


def test_single_client_refines_candidates_from_proposal() -> None:
    """One partition client replaces the default candidates with its LLM-proposed rules per segment."""
    fixture = json.dumps([{"rule": "reject unauthorized transfers"}])
    artifact = partition_document_with_client(_DOC, _client(fixture))
    assert artifact.ensemble_members == 1
    assert artifact.needs_review == []
    # Every behavioral segment yielded the recorded candidate rule.
    behavioral = [
        seg for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    ]
    assert len(artifact.candidate_rules) == len(behavioral)
    for rule in artifact.candidate_rules:
        assert rule.text == "reject unauthorized transfers"


def test_single_client_locates_candidate_span_inside_segment() -> None:
    """A proposed candidate's span lands inside its source segment (deterministic, not model-trusted)."""
    fixture = json.dumps([{"rule": "unauthorized transfers"}])
    artifact = partition_document_with_client(_DOC, _client(fixture))
    rule = artifact.candidate_rules[0]
    source = next(seg for seg in artifact.segments if seg.index == rule.source_segment_index)
    assert source.start <= rule.span_start < rule.span_end <= source.end
    assert _DOC[rule.span_start:rule.span_end] == "unauthorized transfers"


def test_single_client_clarify_routes_to_needs_review_not_guessed() -> None:
    """A clarify sentinel routes the segment to needs_review with NO guessed candidate."""
    fixture = "[[NLR-CLARIFY]] segment is ambiguous about the threshold"
    artifact = partition_document_with_client(_DOC, _client(fixture))
    behavioral = [
        seg for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    ]
    assert len(artifact.needs_review) == len(behavioral)
    assert artifact.candidate_rules == []
    for flag in artifact.needs_review:
        assert flag.kind is PartitionFlagKind.clarify
        assert "ambiguous" in flag.reason


def test_single_client_unparseable_routes_to_needs_review() -> None:
    """A malformed (non-JSON) response routes to needs_review (unparseable), never silently empty."""
    artifact = partition_document_with_client(_DOC, _client("this is not json at all"))
    behavioral = [
        seg for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    ]
    assert len(artifact.needs_review) == len(behavioral)
    assert artifact.candidate_rules == []
    for flag in artifact.needs_review:
        assert flag.kind is PartitionFlagKind.unparseable


def test_single_client_accepts_code_fenced_json() -> None:
    """A ```json-fenced proposal parses (defensive, like the impact-estimate parser)."""
    fixture = '```json\n[{"rule": "reject unauthorized transfers"}]\n```'
    artifact = partition_document_with_client(_DOC, _client(fixture))
    assert artifact.needs_review == []
    assert len(artifact.candidate_rules) >= 1


# ---------------------------------------------------------------------------
# Cross-provider ensemble boundary-disagreement routing
# ---------------------------------------------------------------------------


def test_ensemble_boundary_disagreement_routes_to_human_queue() -> None:
    """When members split vs merge (different candidate sets) the segment flags, never auto-resolved."""
    # Member A proposes one rule; member B proposes two (a split). For every behavioral
    # segment the sets differ → every behavioral segment flags as a boundary disagreement.
    member_a = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    member_b = _client(
        json.dumps(
            [
                {"rule": "reject unauthorized transfers"},
                {"rule": "audit-log the rejection"},
            ]
        )
    )
    artifact = partition_document_with_ensemble(
        _DOC, [member_a, member_b], member_provenance=_prov("anthropic", "openai")
    )
    behavioral = [
        seg for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    ]
    assert artifact.ensemble_members == 2
    # Disagreement on every behavioral segment → all flagged, none silently resolved.
    assert len(artifact.needs_review) == len(behavioral)
    assert artifact.candidate_rules == []
    for flag in artifact.needs_review:
        assert flag.kind is PartitionFlagKind.boundary_disagreement
        assert flag.reason.strip()


def test_ensemble_agreement_yields_candidates_no_flags() -> None:
    """When members propose identical candidate sets, candidates are used with no flag."""
    member_a = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    # Same requirement differing only in case + whitespace (normalize collapses both).
    member_b = _client(json.dumps([{"rule": "  REJECT   unauthorized  transfers  "}]))
    artifact = partition_document_with_ensemble(
        _DOC, [member_a, member_b], member_provenance=_prov("anthropic", "openai")
    )
    behavioral = [
        seg for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    ]
    assert artifact.needs_review == []
    assert len(artifact.candidate_rules) == len(behavioral)


def test_ensemble_mixed_clarify_and_proposal_is_a_disagreement() -> None:
    """Some members clarifying while others propose is itself a boundary disagreement."""
    proposer = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    clarifier = _client("[[NLR-CLARIFY]] cannot state a requirement")
    artifact = partition_document_with_ensemble(
        _DOC, [proposer, clarifier], member_provenance=_prov("anthropic", "openai")
    )
    behavioral = [
        seg for seg in artifact.segments
        if seg.classification is SegmentClassification.behavioral_candidate
    ]
    assert len(artifact.needs_review) == len(behavioral)
    assert artifact.candidate_rules == []
    assert all(flag.kind is PartitionFlagKind.boundary_disagreement for flag in artifact.needs_review)


def test_ensemble_requires_at_least_two_clients() -> None:
    """A single-client ensemble is a misuse: refuse rather than silently degrade."""
    with pytest.raises(ValueError, match="at least two clients"):
        partition_document_with_ensemble(_DOC, [_client('[]')])


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_dispatch_no_clients_is_deterministic() -> None:
    artifact = partition_spec_document(_DOC)
    assert artifact.ensemble_members == 0
    assert artifact.needs_review == []


def test_dispatch_single_client_is_single_member() -> None:
    artifact = partition_spec_document(
        _DOC, clients=[_client(json.dumps([{"rule": "r"}]))]
    )
    assert artifact.ensemble_members == 1


def test_dispatch_two_clients_is_ensemble() -> None:
    artifact = partition_spec_document(
        _DOC,
        clients=[_client('[]'), _client('[]')],
        member_provenance=_prov("anthropic", "openai"),
    )
    assert artifact.ensemble_members == 2


# ---------------------------------------------------------------------------
# Proposal parsing (defensive — UNTRUSTED output)
# ---------------------------------------------------------------------------


def test_parse_extracts_rule_objects_and_bare_strings() -> None:
    parsed = parse_candidate_rules_proposal(json.dumps([{"rule": "first"}, {"rule": " second "}]))
    assert parsed.clarify_reason is None
    assert parsed.rules == ["first", "second"]

    parsed_bare = parse_candidate_rules_proposal(json.dumps(["alpha", "beta"]))
    assert parsed_bare.rules == ["alpha", "beta"]


def test_parse_clarify_sentinel_returns_reason() -> None:
    parsed = parse_candidate_rules_proposal("[[NLR-CLARIFY]] cannot identify a clear requirement")
    assert parsed.rules == []
    assert parsed.clarify_reason is not None
    assert "cannot identify" in parsed.clarify_reason


def test_parse_empty_clarify_sentinel_has_default_reason() -> None:
    parsed = parse_candidate_rules_proposal("[[NLR-CLARIFY]]   ")
    assert parsed.clarify_reason is not None
    assert parsed.clarify_reason.strip() != ""


def test_parse_malformed_returns_unparseable_reason() -> None:
    parsed = parse_candidate_rules_proposal("not json {")
    assert parsed.rules == []
    assert parsed.clarify_reason is not None
    assert "not valid JSON" in parsed.clarify_reason or "unparseable" in parsed.clarify_reason.lower()


def test_parse_empty_rule_list_returns_reason() -> None:
    """An empty-but-valid proposal is a clarify (a behavioral segment must not be silently dropped)."""
    parsed = parse_candidate_rules_proposal("[]")
    assert parsed.rules == []
    assert parsed.clarify_reason is not None


# ---------------------------------------------------------------------------
# CLI smoke (offline)
# ---------------------------------------------------------------------------


def test_cli_partition_spec_deterministic(tmp_path: Path) -> None:
    """``partition-spec`` writes a valid deterministic artifact (no LLM) for a spec document."""
    from nlreq.cli import main

    document = tmp_path / "spec.md"
    document.write_text(_DOC)
    out = tmp_path / "partition.json"
    rc = main(["partition-spec", str(document), "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["document_hash"] == sha256_text(_DOC)
    assert payload["ensemble_members"] == 0
    assert len(payload["segments"]) > 0
    assert len(payload["candidate_rules"]) >= 1
    assert payload["needs_review"] == []


def test_cli_partition_spec_rejects_bad_client_scheme(tmp_path: Path) -> None:
    """A malformed --client scheme is a structured refusal (exit 2), never a silent default."""
    from nlreq.cli import main

    document = tmp_path / "spec.md"
    document.write_text(_DOC)
    out = tmp_path / "partition.json"
    rc = main(["partition-spec", str(document), "--out", str(out), "--client", "bogus-scheme"])
    assert rc == 2


# ---------------------------------------------------------------------------
# Cross-provider-FAMILY diversity gate (scope §3) + per-member provenance
# ---------------------------------------------------------------------------


def test_ensemble_records_per_member_provider_family_provenance() -> None:
    """An ensemble partition records each member's provider family in the artifact (scope §3)."""
    member_a = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    member_b = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    provenance = [
        {"role": "partition", "provider_family": "anthropic", "resolved_model": "claude-x"},
        {"role": "partition", "provider_family": "openai", "resolved_model": "gpt-x"},
    ]
    artifact = partition_document_with_ensemble(
        _DOC, [member_a, member_b], member_provenance=provenance
    )
    families = [m.get("provider_family") for m in artifact.ensemble_member_provenance]
    assert families == ["anthropic", "openai"]


def test_ensemble_diversity_gate_rejects_a_same_family_ensemble() -> None:
    """Two members of the SAME family cannot satisfy the ≥2-distinct-family gate (scope §3)."""
    member_a = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    member_b = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    same_family = [
        {"role": "partition", "provider_family": "anthropic"},
        {"role": "partition", "provider_family": "anthropic"},
    ]
    with pytest.raises(ValueError, match="at least two distinct provider families"):
        partition_document_with_ensemble(
            _DOC, [member_a, member_b], member_provenance=same_family
        )


def test_ensemble_diversity_gate_rejects_an_unknown_family_ensemble() -> None:
    """A member whose family is blank/unknown cannot satisfy the diversity count from itself."""
    member_a = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    member_b = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    # One known family + one blank family → only 1 distinct family → refused.
    one_known = [
        {"role": "partition", "provider_family": "anthropic"},
        {"role": "partition"},  # no provider_family
    ]
    with pytest.raises(ValueError, match="at least two distinct provider families"):
        partition_document_with_ensemble(
            _DOC, [member_a, member_b], member_provenance=one_known
        )


def test_ensemble_without_provenance_is_refused() -> None:
    """An ensemble call without member_provenance is refused (the diversity gate cannot be skipped).

    HELPER iter-2: the ``None`` bypass was removed so the exported API can never be called with a
    same-family ensemble whose correlated training bias defeats the diversity the gate exists to
    catch. Offline recorded-client tests supply recorded distinct families (``_prov``) rather than
    skipping the gate; the production ``partition-spec`` CLI always supplies provenance.
    """
    member_a = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    member_b = _client(json.dumps([{"rule": "reject unauthorized transfers"}]))
    with pytest.raises(ValueError, match="requires member_provenance"):
        partition_document_with_ensemble(_DOC, [member_a, member_b])


# ---------------------------------------------------------------------------
# Non-ASCII character-total regression (offsets are code-point, not byte)
# ---------------------------------------------------------------------------


def test_segmentation_totality_and_round_trip_hold_for_non_ascii() -> None:
    """Segment offsets are CHARACTER offsets: a multibyte document's spans are code-point total.

    A UTF-8 byte-offset segmentation would break the ``document[start:end] == segment.text``
    round-trip for non-ASCII text (you cannot slice a ``str`` by byte offsets). This test pins
    that the segmentation is CHARACTER-total over Unicode code points: the union of spans covers
    ``[0, len(document))`` in CHARACTERS (not bytes), and every segment round-trips. The document
    mixes CJK + accented Latin + emoji so the byte-length strictly exceeds the character length.
    """
    document = (
        "# 支付\n\n"  # heading (CJK)
        "系统必须拒绝未授权的转账。\n\n"  # behavioral paragraph (CJK)
        "- 转账不得超过可用余额。\n"  # behavioral list item (CJK)
        "- 注释：这是描述性的。\n"  # non-behavioral note (CJK)
        "Überweisungen müssen within 7 Tagen sein.\n"  # accented Latin
        "Emoji 😎 marker line.\n"
    )
    # Sanity: byte length strictly exceeds character length (so a byte-offset bug would be caught).
    assert len(document.encode("utf-8")) > len(document)

    segments = segment_document(document)
    assert segments[0].start == 0
    assert segments[-1].end == len(document)
    for previous, current in zip(segments, segments[1:]):
        assert previous.end == current.start
    # Character totality: span length sum == character length (NOT byte length).
    assert sum(s.end - s.start for s in segments) == len(document)
    # Round-trip: every segment's text is exactly the document slice at its CHARACTER offsets.
    for segment in segments:
        assert document[segment.start:segment.end] == segment.text

    # AC6 byte-totality: EVERY BYTE is in exactly one segment. The byte spans are contiguous, cover
    # [0, len(utf-8 bytes)), and each segment's byte span round-trips to its text (the byte-offset
    # counterpart of the code-point round-trip above) — proven over a strictly-multibyte document.
    document_bytes = document.encode("utf-8")
    assert segments[0].byte_start == 0
    assert segments[-1].byte_end == len(document_bytes)
    for previous, current in zip(segments, segments[1:]):
        assert previous.byte_end == current.byte_start
    assert sum(s.byte_end - s.byte_start for s in segments) == len(document_bytes)
    for segment in segments:
        assert segment_text_from_bytes(document, segment) == segment.text
        # A genuinely multibyte segment spans strictly more bytes than code points.
        if any(ord(ch) > 127 for ch in segment.text):
            assert segment.byte_end - segment.byte_start > segment.end - segment.start

    # The deterministic partition is character-total and produces candidates whose spans round-trip.
    artifact = partition_document_deterministic(document, language="zh")
    assert artifact.document_length == len(document)
    for rule in artifact.candidate_rules:
        assert document[rule.span_start:rule.span_end] == rule.text or rule.text in document[rule.span_start:rule.span_end]


# ---------------------------------------------------------------------------
# Per-candidate drafting batch (scope §4 / HELPER iter-2)
# ---------------------------------------------------------------------------


def _drafter(controlled_text: str) -> RecordedLlmClient:
    """A recorded drafting client that replays the given controlled text for every candidate."""
    return RecordedLlmClient(fixture=controlled_text)


def _draft_artifact() -> SpecPartitionArtifact:
    """A deterministic partition whose candidates are drafted in the tests below."""
    return partition_document_deterministic(_DOC)


def test_draft_single_client_records_controlled_text_per_candidate() -> None:
    """One drafting client drafts each candidate; controlled_text is set, no agreement hash."""
    artifact = _draft_artifact()
    drafted = draft_candidate_rules(artifact, [_drafter("When X then Y must be Z.")])
    # Every candidate carries the drafted controlled text; no agreement hash (single voice).
    assert drafted.candidate_rules
    for rule in drafted.candidate_rules:
        assert rule.controlled_text == "When X then Y must be Z."
        assert rule.controlled_text_agreement_hash is None
    # No drafting flags (no clarify, no disagreement).
    assert drafted.needs_review == []


def test_draft_clarify_routes_the_candidate_to_the_human_queue() -> None:
    """A candidate the drafter cannot state (the clarify sentinel) routes to needs_review."""
    artifact = _draft_artifact()
    drafted = draft_candidate_rules(
        artifact, [_drafter("[[NLR-CLARIFY]] cannot state this requirement")]
    )
    # No candidate carries a controlled text (all clarified).
    assert all(rule.controlled_text is None for rule in drafted.candidate_rules)
    # Every candidate flagged as a clarify, with a per-candidate reason.
    assert drafted.needs_review
    assert all(flag.kind is PartitionFlagKind.clarify for flag in drafted.needs_review)
    assert all("candidate" in flag.reason for flag in drafted.needs_review)


def test_draft_ensemble_agreement_records_the_agreed_text_and_hash() -> None:
    """A cross-provider drafting ensemble that agrees records the agreed text + its hash."""
    agreed = "When an unauthorized caller performs the action then the operation must be rejected."
    artifact = _draft_artifact()
    drafted = draft_candidate_rules(artifact, [_drafter(agreed), _drafter(agreed)])
    for rule in drafted.candidate_rules:
        assert rule.controlled_text == agreed
        # The agreement hash is the canonical hash of the NORMALIZED text (the form the package
        # stores), so a downstream machine pin validates against the packaged controlled text.
        assert rule.controlled_text_agreement_hash == sha256_text(normalize_controlled_text(agreed))
    assert drafted.needs_review == []


def test_draft_ensemble_disagreement_routes_to_the_human_queue() -> None:
    """Members producing different controlled texts route the candidate to needs_review."""
    artifact = _draft_artifact()
    drafted = draft_candidate_rules(
        artifact,
        [
            _drafter("When X then Y must be Z."),
            _drafter("When X then Y must be W."),  # different text
        ],
    )
    # No agreed controlled text; every candidate flagged as a boundary disagreement.
    assert all(rule.controlled_text is None for rule in drafted.candidate_rules)
    assert drafted.needs_review
    assert all(flag.kind is PartitionFlagKind.boundary_disagreement for flag in drafted.needs_review)


def test_draft_ensemble_mixed_clarify_is_a_disagreement() -> None:
    """Some members clarifying while others draft is itself a boundary disagreement."""
    artifact = _draft_artifact()
    drafted = draft_candidate_rules(
        artifact,
        [
            _drafter("When X then Y must be Z."),
            _drafter("[[NLR-CLARIFY]] cannot state this"),
        ],
    )
    assert all(rule.controlled_text is None for rule in drafted.candidate_rules)
    assert all(flag.kind is PartitionFlagKind.boundary_disagreement for flag in drafted.needs_review)
