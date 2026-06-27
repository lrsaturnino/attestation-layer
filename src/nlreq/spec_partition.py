"""Zone 1 — deterministic spec partitioning (document → N candidate rules).

Three-zone scope, Work Item 1 / §4. nlreq's intake-draft is hard-pinned to ONE rule per
document, so feeding a multi-section spec yields one compressed rule. This module turns a
whole spec document into an exhaustive, ordered set of segments and an N-sized candidate-rule
list, giving the completeness oracle (``attest-spec`` Zone 3) a real basis: the
segmentation itself.

Design — two stages, determinism first (scope §4):

* **Deterministic total segmentation** (``segment_document``) runs BEFORE any LLM call. It
  partitions the document into an exhaustive, ordered set of segments by heading / list /
  paragraph / blank-line structure. Each segment carries BOTH a code-point span (``[start, end)``,
  the ``str`` round-trip ``document[start:end] == segment.text``) and a UTF-8 byte span
  (``[byte_start, byte_end)``). The union of every segment's byte span is exactly
  ``[0, len(text.encode("utf-8")))`` and the spans are disjoint — every BYTE is in exactly one
  segment (AC6), and likewise every code point. This totality is the completeness oracle:
  ``segmentation`` is the deterministic definition of "all behavioral-candidate spans" the v2
  criterion lacked.

* **Per-segment classification** (``classify_segment``) labels every segment
  ``behavioral_candidate`` or ``non_behavioral`` with a recorded reason. Non-behavioral
  segments are EXCLUDED from the candidate list but RECORDED in the artifact with their
  reason — never silently dropped (``extracted ∪ excluded == the full segmentation``). The
  heuristic leans behavioral for prose/list items (minimizes silent drops of requirements);
  the LLM partitioner refines (and can mark a segment non-behavioral via the clarify
  sentinel).

* **LLM partitioner (proposal-only)** (``partition_document_with_client``). For each
  behavioral segment the ``partition`` role (built via ``build_client_for_role``) proposes
  one or more atomic, single-meaning candidate rules as PLAIN LANGUAGE (not controlled DSL —
  drafting is a later, separate role). The source span of each candidate is computed
  deterministically by locating the rule text inside the segment, never trusted from the
  model. A segment the model cannot state a clear requirement for emits the ``[[NLR-CLARIFY]]``
  sentinel and routes to ``needs_review`` (the same low-confidence refusal discipline drafting
  uses) — never a guessed candidate.

* **Ensemble partitioning** (``partition_document_with_ensemble``). Run the partitioner under
  ≥2 cross-provider clients. Boundary disagreements — one member merges what another splits,
  or one clarifies while another proposes — flag to ``needs_review`` and are never silently
  resolved.

The output ``SpecPartitionArtifact`` records the document hash, EVERY segment with its
classification, the candidate rules (with spans), and any needs-review flags — so a human can
scan the manifest in seconds to confirm boundaries (the one cheap early touch).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .jsonutil import sha256_text
from .llm_client import CROSS_LANGUAGE_CLARIFY_SENTINEL
from .parser import normalize_controlled_text


def _distinct_provider_families(member_provenance: list[dict[str, str]]) -> list[str]:
    """The sorted distinct provider families across the ensemble members (scope §3 diversity).

    A ``None``/blank ``provider_family`` (an unconfigured member) contributes nothing, so an
    ensemble with an unknown-family member cannot satisfy a ≥2-distinct-family requirement from
    that member. Mirrors ``machine_agreement.distinct_provider_families`` but operates on the
    partition artifact's flat provenance dicts (the partition members are not ``EnsembleMember``).
    """
    families: set[str] = set()
    for provenance in member_provenance:
        family = provenance.get("provider_family")
        if isinstance(family, str) and family.strip():
            families.add(family.strip())
    return sorted(families)

__all__ = [
    "SegmentKind",
    "SegmentClassification",
    "Segment",
    "ClassifiedSegment",
    "CandidateRule",
    "PartitionFlagKind",
    "PartitionFlag",
    "SpecPartitionArtifact",
    "ParsedProposal",
    "segment_document",
    "segment_text_from_bytes",
    "classify_segment",
    "parse_candidate_rules_proposal",
    "partition_document_deterministic",
    "partition_document_with_client",
    "partition_document_with_ensemble",
    "partition_spec_document",
    "draft_candidate_rules",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class SegmentKind(str, Enum):
    """Deterministic structural kind of a segment.

    The four kinds are exhaustive over a document's characters: ``heading`` (a markdown ``#`` or
    section-title line), ``list_item`` (a ``-``/``*``/``+`` or ``N.``/``N)`` prefixed line),
    ``paragraph`` (a maximal run of plain prose lines), and ``separator`` (a maximal run of
    blank/whitespace-only lines). ``list_item`` is treated atomically (one segment per item)
    so the default candidate derivation has fine granularity; the other three merge maximal
    same-kind runs.
    """

    heading = "heading"
    paragraph = "paragraph"
    list_item = "list_item"
    separator = "separator"


class SegmentClassification(str, Enum):
    """The deterministic first-pass classification of a segment.

    ``behavioral_candidate`` — the segment may state a testable requirement and is forwarded
    to the partitioner for a candidate-rule proposal. ``non_behavioral`` — structural
    (heading/separator) or clearly meta (reference/note/example/comment); excluded from the
    candidate list but recorded with its reason. ``needs_clarification`` — the partitioner
    could not state a clear requirement (the ``[[NLR-CLARIFY]]`` sentinel); the segment routes
    to the human queue, never a guessed candidate.
    """

    behavioral_candidate = "behavioral_candidate"
    non_behavioral = "non_behavioral"
    needs_clarification = "needs_clarification"


class Segment(BaseModel):
    """One segment of the document, carrying BOTH a code-point span and a byte span.

    ``[start, end)`` is a half-open span of Python string offsets (Unicode code-point indices), so
    ``text == document[start:end]`` always holds (the str round-trip — you cannot slice a ``str`` by
    byte offsets). ``[byte_start, byte_end)`` is the corresponding half-open span of UTF-8 BYTE
    offsets, so ``document.encode("utf-8")[byte_start:byte_end].decode("utf-8") == text`` holds and
    the byte spans of all segments partition ``[0, len(document.encode("utf-8")))`` — i.e. EVERY
    BYTE is in exactly one segment (AC6 byte-totality), literally provable, not only every code
    point. For an ASCII document the two spans coincide; for a non-ASCII document ``byte_end -
    byte_start >= end - start`` (a multibyte character spans more bytes than code points). Both spans
    are recorded so a byte-oriented external consumer addresses the document correctly while the
    in-process str round-trip stays exact.
    """

    model_config = ConfigDict(extra="forbid")

    index: int
    start: int
    end: int
    byte_start: int
    byte_end: int
    text: str
    kind: SegmentKind


class ClassifiedSegment(BaseModel):
    """A segment paired with its deterministic classification and the reason it was assigned.

    Flattened (rather than nesting ``Segment``) so the totality / round-trip invariants are
    asserted directly on the artifact's JSON without a nested dereference. Carries both the
    code-point span (``start``/``end``, the str round-trip) and the UTF-8 byte span
    (``byte_start``/``byte_end``, the byte-totality oracle — every byte in exactly one classified
    segment, AC6) — see ``Segment``.
    """

    model_config = ConfigDict(extra="forbid")

    index: int
    start: int
    end: int
    byte_start: int
    byte_end: int
    text: str
    segment_kind: SegmentKind
    classification: SegmentClassification
    reason: str


class CandidateRule(BaseModel):
    """One proposed atomic candidate requirement derived from a behavioral segment.

    ``[span_start, span_end)`` is a half-open span into the ORIGINAL document text locating
    the source of this candidate (so a human can jump to it). For the deterministic default
    the span is the whole segment; for an LLM-proposed candidate the span is computed by
    locating the rule text inside the segment (falling back to the whole segment when the
    model paraphrased). ``source_segment_index`` ties the candidate back to its segment.

    ``controlled_text`` / ``controlled_text_agreement_hash`` are populated by the per-candidate
    DRAFTING batch (scope §4 / HELPER iter-2): ``controlled_text`` is the DSL controlled text the
    drafting role produced for this candidate (None until drafting runs);
    ``controlled_text_agreement_hash`` is the canonical hash of the agreed controlled text when
    drafting ran under a cross-provider ensemble that AGREED (None for a single draft or a
    disagreement). A candidate the drafter could not state (the ``[[NLR-CLARIFY]]`` sentinel) or
    whose members disagreed is routed to the human queue via a ``needs_review`` flag rather than
    carrying a controlled text — clarify routing is preserved per candidate (scope §4).
    """

    model_config = ConfigDict(extra="forbid")

    index: int
    text: str
    span_start: int
    span_end: int
    source_segment_index: int
    controlled_text: str | None = None
    controlled_text_agreement_hash: str | None = None


class PartitionFlagKind(str, Enum):
    """Why a behavioral segment's candidates were routed to the human queue instead of listed.

    ``clarify`` — the partitioner emitted the ``[[NLR-CLARIFY]]`` sentinel (could not state a
    clear requirement). ``boundary_disagreement`` — ensemble members disagreed on how to
    partition the segment (one merged what another split, or some clarified while others
    proposed). ``unparseable`` — the partitioner's response could not be parsed into candidate
    rules (malformed JSON); routed to the human rather than silently dropped or guessed.
    """

    clarify = "clarify"
    boundary_disagreement = "boundary_disagreement"
    unparseable = "unparseable"


class PartitionFlag(BaseModel):
    """A human-queue flag raised during partitioning, each carrying a reason (never silent)."""

    model_config = ConfigDict(extra="forbid")

    kind: PartitionFlagKind
    segment_index: int
    reason: str


class SpecPartitionArtifact(BaseModel):
    """The Zone 1 artifact: document hash + every segment + candidate rules + needs-review flags.

    ``segments`` records EVERY segment (behavioral and non-behavioral) with its classification
    and reason, so ``extracted (candidate_rules' source segments) ∪ excluded (non-behavioral)
    == the full segmentation`` — no segment is silently dropped (completeness oracle). The
    human scans this manifest to confirm boundaries in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    document_hash: str
    document_length: int
    language: str
    segments: list[ClassifiedSegment]
    candidate_rules: list[CandidateRule]
    needs_review: list[PartitionFlag]
    # 0 = deterministic (no LLM), 1 = single partition client, ≥2 = cross-provider ensemble.
    ensemble_members: int
    provenance: dict[str, str]
    # Per-member resolved provenance for an ensemble partition (scope §3/§4): each entry carries the
    # member's provider_family / resolved_model / wrapper / client_kind / prompt_version, so the
    # artifact records WHICH providers partitioned the document and under which families — the
    # evidence the diversity gate (≥2 distinct families) is recorded against. Empty for the
    # deterministic path and the single-client path's unconfigured members.
    ensemble_member_provenance: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Deterministic total segmentation
# ---------------------------------------------------------------------------

# A markdown heading: optional leading spaces then one or more '#'. (ATX headings; the
# segmenter is deliberately structural-only — it does not interpret underlined/Setext headings
# as headings because that needs lookahead ambiguity resolution; a Setext title parses as a
# paragraph, which is the safe default for a deterministic first pass.)
_HEADING_RE = re.compile(r"^\s{0,3}#+\s+\S")
# A list-item marker: '-', '*', '+' (bullet) or 'N.' / 'N)' (ordered), each followed by space.
_BULLET_RE = re.compile(r"^\s*[-*+]\s+\S")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+\S")
# A leading list marker (for stripping before meta-content checks / default candidate text).
_LIST_MARKER_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")


def _classify_line(line_with_ending: str) -> SegmentKind:
    """Classify a single line (WITH its line ending) into a structural kind.

    The line ending is included so character offsets are exact; classification inspects the
    line's content with the ending stripped. A whitespace-only line is a ``separator``; a
    markdown ``#`` heading is a ``heading``; a bullet/ordered marker is a ``list_item``;
    anything else with content is ``paragraph``.
    """
    content = line_with_ending.rstrip("\r\n")
    if not content.strip():
        return SegmentKind.separator
    if _HEADING_RE.match(line_with_ending):
        return SegmentKind.heading
    if _BULLET_RE.match(line_with_ending) or _ORDERED_RE.match(line_with_ending):
        return SegmentKind.list_item
    return SegmentKind.paragraph


def segment_document(text: str) -> list[Segment]:
    """Segment a document into an exhaustive, ordered set of character-disjoint segments.

    Totality invariant: the union of every segment's ``[start, end)`` span is exactly
    ``[0, len(text))`` and consecutive segments are contiguous (``segments[i].end ==
    segments[i+1].start``), with ``segments[0].start == 0`` and ``segments[-1].end ==
    len(text)`` (empty document → empty list, whose empty union trivially covers ``[0, 0)``).
    Each ``segment.text == text[start:end]`` (str round-trip). The SAME totality holds over the
    UTF-8 byte spans: the union of every ``[byte_start, byte_end)`` is exactly
    ``[0, len(text.encode("utf-8")))`` — every byte is in exactly one segment (AC6) — see ``Segment``.

    Grouping: ``list_item`` lines are atomic (one segment each) so default candidate
    derivation is fine-grained; ``paragraph``, ``heading``, and ``separator`` each merge
    maximal same-kind runs. A category change always starts a new segment.
    """
    # splitlines(keepends=True) preserves every character (including newlines), so concatenating
    # all returned lines reproduces ``text`` exactly — the basis of both totality invariants.
    lines = text.splitlines(keepends=True)
    segments: list[Segment] = []
    seg_start = 0
    seg_byte_start = 0
    seg_kind: SegmentKind | None = None
    offset = 0  # running end-of-last-consumed-line offset (code points)
    byte_offset = 0  # running end-of-last-consumed-line offset (UTF-8 bytes)

    def _flush(until: int, byte_until: int) -> None:
        nonlocal seg_kind
        if seg_kind is not None:
            segments.append(
                Segment(
                    index=len(segments),
                    start=seg_start,
                    end=until,
                    byte_start=seg_byte_start,
                    byte_end=byte_until,
                    text=text[seg_start:until],
                    kind=seg_kind,
                )
            )
            seg_kind = None

    for raw in lines:
        kind = _classify_line(raw)
        line_end = offset + len(raw)
        byte_line_end = byte_offset + len(raw.encode("utf-8"))
        if kind is SegmentKind.list_item:
            # Atomic: never merge list items. Flush any open non-list segment at this line's
            # start, then emit this single line as its own segment.
            _flush(offset, byte_offset)
            segments.append(
                Segment(
                    index=len(segments),
                    start=offset,
                    end=line_end,
                    byte_start=byte_offset,
                    byte_end=byte_line_end,
                    text=text[offset:line_end],
                    kind=kind,
                )
            )
        else:
            if seg_kind is None:
                seg_start = offset
                seg_byte_start = byte_offset
                seg_kind = kind
            elif seg_kind != kind:
                _flush(offset, byte_offset)
                seg_start = offset
                seg_byte_start = byte_offset
                seg_kind = kind
            # same kind: extend the current run (seg_start unchanged; flushed later).
        offset = line_end
        byte_offset = byte_line_end
    _flush(offset, byte_offset)
    return segments


def segment_text_from_bytes(document: str, segment: "Segment | ClassifiedSegment") -> str:
    """Recover a segment's text from the document via its UTF-8 BYTE span (the byte round-trip).

    ``document.encode("utf-8")[segment.byte_start:segment.byte_end].decode("utf-8")`` reproduces
    ``segment.text`` exactly. This is the byte-offset counterpart of ``document[start:end]`` (which
    a ``str`` supports directly over code points); it lets a byte-oriented consumer address the
    document and recover the same text the code-point span yields, proving the byte span is correct.
    """
    return document.encode("utf-8")[segment.byte_start:segment.byte_end].decode("utf-8")


# ---------------------------------------------------------------------------
# Per-segment classification
# ---------------------------------------------------------------------------

# Prose/list prefixes that are clearly NOT testable requirements (commentary / references /
# examples). The heuristic leans behavioral for everything else to minimize silent drops of
# requirements, especially in non-English documents where modal-verb detection is unreliable.
_NON_BEHAVIORAL_PREFIXES = (
    "note:",
    "notes:",
    "example:",
    "examples:",
    "e.g.",
    "i.e.",
    "see ",
    "see also",
    "cf.",
    "figure ",
    "table ",
    "diagram",
    "listing",
    "reference:",
    "ref:",
    "source:",
    "todo",
    "fixme",
    "xxx",
    "//",
    "/*",
    "credit",
)


def _strip_list_marker(text: str) -> str:
    """Strip a leading list marker (bullet or ordered) so meta-checks / candidate text are clean."""
    s = text.strip()
    match = _LIST_MARKER_RE.match(s)
    if match:
        s = s[match.end():].strip()
    return s


def _looks_non_behavioral(text: str) -> bool:
    """True when prose/list content is clearly meta (a reference, note, example, or comment).

    List markers are stripped first so ``- See the fraud module.`` is detected as a reference,
    not matched against the literal ``- see`` prefix.
    """
    stripped = _strip_list_marker(text)
    if not stripped:
        return True
    if stripped.startswith(("http://", "https://", "www.", "ftp://")):
        return True
    lowered = stripped.lower()
    return any(lowered.startswith(prefix) for prefix in _NON_BEHAVIORAL_PREFIXES)


def classify_segment(segment: Segment) -> tuple[SegmentClassification, str]:
    """Deterministic first-pass classification of a segment, returning (classification, reason).

    Headings and separators are structural (non-behavioral). Prose and list items are
    ``behavioral_candidate`` unless they are clearly meta (reference/note/example/comment) —
    the heuristic leans behavioral so a requirement is forwarded to the partitioner rather
    than silently dropped. The reason is always recorded (the completeness oracle requires
    every excluded segment to state why).
    """
    if segment.kind is SegmentKind.heading:
        return (
            SegmentClassification.non_behavioral,
            "structural heading; introduces a section and asserts no testable requirement",
        )
    if segment.kind is SegmentKind.separator:
        return (
            SegmentClassification.non_behavioral,
            "whitespace separator between blocks",
        )
    if not segment.text.strip():
        return (
            SegmentClassification.non_behavioral,
            "blank/whitespace-only content",
        )
    if _looks_non_behavioral(segment.text):
        return (
            SegmentClassification.non_behavioral,
            "reference/note/example/comment, not a testable requirement",
        )
    return (
        SegmentClassification.behavioral_candidate,
        "prose or list item that may state a testable requirement; forwarded to the partitioner for a candidate-rule proposal",
    )


def _build_classified(segment: Segment) -> ClassifiedSegment:
    classification, reason = classify_segment(segment)
    return ClassifiedSegment(
        index=segment.index,
        start=segment.start,
        end=segment.end,
        byte_start=segment.byte_start,
        byte_end=segment.byte_end,
        text=segment.text,
        segment_kind=segment.kind,
        classification=classification,
        reason=reason,
    )


def _heading_contexts(segments: list[Segment]) -> list[str]:
    """The nearest preceding heading text for each segment (the partitioner's naming context)."""
    contexts: list[str] = []
    current = ""
    for segment in segments:
        if segment.kind is SegmentKind.heading:
            current = segment.text.strip()
        contexts.append(current)
    return contexts


# ---------------------------------------------------------------------------
# Candidate-rule proposal parsing (defensive — the output is UNTRUSTED)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedProposal:
    """A parsed partitioner proposal: either candidate rules or a clarify reason (never both).

    ``clarify_reason is not None`` means the partitioner could not (or did not) state a clear
    requirement — the segment routes to the human queue. ``rules`` is empty in that case.
    """

    rules: list[str]
    clarify_reason: str | None


def parse_candidate_rules_proposal(text: str) -> ParsedProposal:
    """Defensively parse an UNTRUSTED partitioner response into candidate rules or a clarify.

    Accepts a JSON array of ``{"rule": "..."}`` objects (or bare strings), tolerating a
    surrounding ```json code fence and prose wrapping — the same defensive posture as
    ``parse_impact_estimate``. The ``[[NLR-CLARIFY]]`` sentinel short-circuits to a clarify
    result (the partitioner's explicit "cannot state a clear requirement" refusal). An
    unparseable or empty response is a clarify with a descriptive reason — never a silent
    empty candidate list (which would drop a behavioral segment without a recorded flag).
    """
    if CROSS_LANGUAGE_CLARIFY_SENTINEL in text:
        _, _, remainder = text.partition(CROSS_LANGUAGE_CLARIFY_SENTINEL)
        reason = remainder.strip() or "the partitioner could not identify a clear requirement"
        return ParsedProposal(rules=[], clarify_reason=reason)

    stripped = text.strip()
    # Strip a surrounding markdown code fence (```json ... ``` or ``` ... ```) if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()

    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        return ParsedProposal(
            rules=[], clarify_reason="unparseable partition proposal (not valid JSON)"
        )

    rules: list[str] = []
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                value = item.get("rule")
                if isinstance(value, str) and value.strip():
                    rules.append(value.strip())
            elif isinstance(item, str) and item.strip():
                rules.append(item.strip())
    elif isinstance(parsed, dict):
        value = parsed.get("rule")
        if isinstance(value, str) and value.strip():
            rules.append(value.strip())

    if not rules:
        return ParsedProposal(
            rules=[], clarify_reason="partition proposal parsed but contained no candidate rules"
        )
    return ParsedProposal(rules=rules, clarify_reason=None)


# ---------------------------------------------------------------------------
# Candidate derivation
# ---------------------------------------------------------------------------


def _locate_span(rule_text: str, segment: Segment) -> tuple[int, int]:
    """Locate a candidate rule's source span inside its segment (whole-segment fallback).

    The span is computed deterministically by finding the rule text inside the segment text,
    so the candidate's ``[span_start, span_end)`` always lands within ``[segment.start,
    segment.end)``. A paraphrased rule (not found verbatim) falls back to the whole segment —
    still a correct, traceable span, never a model-trusted offset.
    """
    needle = rule_text.strip()
    if needle:
        idx = segment.text.find(needle)
        if idx >= 0:
            return segment.start + idx, segment.start + idx + len(needle)
    return segment.start, segment.end


def _normalize_rule(rule_text: str) -> str:
    """Normalize a rule for ensemble agreement comparison (whitespace-collapsed, lowercased)."""
    return " ".join(rule_text.strip().lower().split())


def _candidates_from_rules(
    segment: Segment, rules: list[str], start_index: int
) -> list[CandidateRule]:
    candidates: list[CandidateRule] = []
    for offset, rule_text in enumerate(rules):
        span_start, span_end = _locate_span(rule_text, segment)
        candidates.append(
            CandidateRule(
                index=start_index + offset,
                text=rule_text,
                span_start=span_start,
                span_end=span_end,
                source_segment_index=segment.index,
            )
        )
    return candidates


def _default_candidate(segment: Segment, start_index: int) -> CandidateRule:
    """The deterministic one-candidate-per-behavioral-segment (used when no LLM is configured).

    The candidate text is the segment content with its list marker stripped (a requirement,
    not list formatting); the span stays the whole segment so the source is traceable.
    """
    return CandidateRule(
        index=start_index,
        text=_strip_list_marker(segment.text),
        span_start=segment.start,
        span_end=segment.end,
        source_segment_index=segment.index,
    )


# ---------------------------------------------------------------------------
# Partition drivers
# ---------------------------------------------------------------------------


def partition_document_deterministic(
    text: str, *, language: str = "en", provenance: dict[str, str] | None = None
) -> SpecPartitionArtifact:
    """Partition a document with NO LLM call: deterministic segmentation + classification.

    Every behavioral-candidate segment yields one default candidate (the segment text itself
    with the whole-segment span). No needs-review flags (no model to refuse or disagree).
    This is the character-stable offline path and the basis the LLM partitioner refines.
    """
    segments = segment_document(text)
    classified = [_build_classified(segment) for segment in segments]
    candidates: list[CandidateRule] = []
    for classified_segment in classified:
        if classified_segment.classification is SegmentClassification.behavioral_candidate:
            candidates.append(_default_candidate(_segment_from_classified(classified_segment), len(candidates)))
    return SpecPartitionArtifact(
        document_hash=sha256_text(text),
        document_length=len(text),
        language=language,
        segments=classified,
        candidate_rules=candidates,
        needs_review=[],
        ensemble_members=0,
        provenance=dict(provenance) if provenance else {},
    )


def partition_document_with_client(
    text: str,
    client: object,
    *,
    language: str = "en",
    provenance: dict[str, str] | None = None,
    member_provenance: list[dict[str, str]] | None = None,
) -> SpecPartitionArtifact:
    """Partition a document with ONE partition client refining each behavioral segment.

    The partitioner (``propose_candidate_rules``) proposes one or more atomic candidate rules
    per behavioral segment as plain language. A clarify sentinel or an unparseable response
    routes the segment to ``needs_review`` (never a guessed candidate); a successful proposal
    yields candidates whose spans are located deterministically inside the segment.
    ``member_provenance`` (from the factory's ``RoleProvenance``) is recorded on the artifact so
    the single member's provider family / resolved model are self-describing (scope §3).
    """
    segments = segment_document(text)
    classified = [_build_classified(segment) for segment in segments]
    contexts = _heading_contexts(segments)
    candidates: list[CandidateRule] = []
    needs_review: list[PartitionFlag] = []

    for index, classified_segment in enumerate(classified):
        if classified_segment.classification is not SegmentClassification.behavioral_candidate:
            continue
        segment = _segment_from_classified(classified_segment)
        raw = client.propose_candidate_rules(
            segment_text=segment.text,
            document_context=contexts[index],
            language=language,
        )
        parsed = parse_candidate_rules_proposal(raw)
        if parsed.clarify_reason is not None:
            kind = (
                PartitionFlagKind.unparseable
                if parsed.clarify_reason.startswith("unparseable")
                or "not valid JSON" in parsed.clarify_reason
                else PartitionFlagKind.clarify
            )
            needs_review.append(
                PartitionFlag(
                    kind=kind, segment_index=segment.index, reason=parsed.clarify_reason
                )
            )
            continue
        new_candidates = _candidates_from_rules(segment, parsed.rules, len(candidates))
        candidates.extend(new_candidates)

    return SpecPartitionArtifact(
        document_hash=sha256_text(text),
        document_length=len(text),
        language=language,
        segments=classified,
        candidate_rules=candidates,
        needs_review=needs_review,
        ensemble_members=1,
        provenance=dict(provenance) if provenance else {},
        ensemble_member_provenance=list(member_provenance) if member_provenance else [],
    )


def partition_document_with_ensemble(
    text: str,
    clients: list[object],
    *,
    language: str = "en",
    provenance: dict[str, str] | None = None,
    member_provenance: list[dict[str, str]] | None = None,
) -> SpecPartitionArtifact:
    """Partition a document under ≥2 CROSS-PROVIDER clients; flag boundary disagreements.

    Segmentation is deterministic, so every member sees the same segments. The disagreement
    axis is the candidate-rule proposal per segment: if members propose different rule sets
    (one merges what another splits), or some clarify while others propose, the segment routes
    to ``needs_review`` as a ``boundary_disagreement`` and its candidates are NOT silently
    resolved. Only unanimously-agreed segments contribute candidates.

    CROSS-PROVIDER DIVERSITY (scope §3/§4): the ensemble must span ≥2 distinct provider
    FAMILIES (not merely ≥2 distinct providers — two wrappers can resolve to the same family).
    ``member_provenance`` (one entry per client, from the factory's ``RoleProvenance``) supplies
    each member's ``provider_family``; when it is supplied, an ensemble that does not span ≥2
    distinct families is a misconfiguration (refused, never silently run as a same-family
    ensemble whose correlated training bias defeats the diversity the gate exists to catch).
    When ``member_provenance`` is None/empty (offline recorded-client tests), no diversity check
    runs — the CLI (the production entry point) ALWAYS supplies it, so production enforces the
    gate. Per-member provenance is recorded on the artifact so the diversity is self-describing.
    """
    if len(clients) < 2:
        raise ValueError(
            "partition_document_with_ensemble requires at least two clients "
            "(use partition_document_with_client for a single client)"
        )
    # CROSS-PROVIDER DIVERSITY (scope §3/§4): the ensemble must span ≥2 distinct provider FAMILIES
    # (not merely ≥2 distinct providers — two wrappers can resolve to the same family).
    # ``member_provenance`` (one entry per client, from the factory's ``RoleProvenance``) is now
    # REQUIRED (HELPER iter-2): previously a ``None`` provenance skipped the diversity gate
    # entirely, so the exported API could be called with a same-family ensemble whose correlated
    # training bias defeats the diversity the gate exists to catch. The production entry point
    # (``partition-spec`` CLI) always supplies it; offline recorded-client tests supply recorded
    # distinct families rather than skipping the gate. Per-member provenance is recorded on the
    # artifact so the diversity is self-describing.
    if member_provenance is None:
        raise ValueError(
            "partition_document_with_ensemble requires member_provenance (one entry per client, "
            "from the factory's RoleProvenance) so each member's provider_family is known and the "
            "≥2-distinct-family diversity gate is enforced; a None provenance would skip the gate "
            "and admit a same-family ensemble. Offline tests supply recorded distinct families."
        )
    member_prov = list(member_provenance)
    if len(member_prov) != len(clients):
        raise ValueError(
            f"partition_document_with_ensemble requires one member_provenance entry per client "
            f"(got {len(member_prov)} provenance entries for {len(clients)} clients); each "
            "member's provider_family must be known to enforce the diversity gate"
        )
    families = _distinct_provider_families(member_prov)
    if len(families) < 2:
        raise ValueError(
            "partition_document_with_ensemble requires at least two distinct provider "
            f"families; the configured ensemble spans only {len(families)} "
            f"family/families ({families}). Two distinct providers can still be the same family "
            "(e.g. two wrappers both resolving to Anthropic models); configure clients from "
            "≥2 distinct families (run-claude/run-gpt/run-gemini/run-oss) so the ensemble is not "
            "dominated by correlated training bias."
        )
    segments = segment_document(text)
    classified = [_build_classified(segment) for segment in segments]
    contexts = _heading_contexts(segments)
    candidates: list[CandidateRule] = []
    needs_review: list[PartitionFlag] = []

    for index, classified_segment in enumerate(classified):
        if classified_segment.classification is not SegmentClassification.behavioral_candidate:
            continue
        segment = _segment_from_classified(classified_segment)
        member_proposals: list[ParsedProposal] = []
        for client in clients:
            # An ensemble is specifically resilient to individual member issues: a transport
            # error (e.g. a cli wrapper that fails its pure-completion contract) is recorded as
            # a clarify reason for that member and surfaced as a flag, never a silent drop and
            # never an aborted whole-document run. The reason carries the exception text.
            try:
                raw = client.propose_candidate_rules(
                    segment_text=segment.text,
                    document_context=contexts[index],
                    language=language,
                )
                member_proposals.append(parse_candidate_rules_proposal(raw))
            except Exception as exc:  # noqa: BLE001 — ensemble resilience: record + flag, never abort
                member_proposals.append(
                    ParsedProposal(
                        rules=[],
                        clarify_reason=f"partition client transport error: {type(exc).__name__}: {exc}",
                    )
                )

        clarify_members = [p for p in member_proposals if p.clarify_reason is not None]
        if clarify_members:
            # If ALL members clarify, it is a clarify; if only SOME do, members disagreed on
            # whether the segment states a requirement at all → a boundary disagreement.
            if len(clarify_members) == len(member_proposals):
                reason = clarify_members[0].clarify_reason or "all ensemble members could not identify a clear requirement"
                needs_review.append(
                    PartitionFlag(kind=PartitionFlagKind.clarify, segment_index=segment.index, reason=reason)
                )
            else:
                needs_review.append(
                    PartitionFlag(
                        kind=PartitionFlagKind.boundary_disagreement,
                        segment_index=segment.index,
                        reason=(
                            "ensemble members disagreed: some could not identify a requirement "
                            "(clarify) while others proposed candidates"
                        ),
                    )
                )
            continue

        # Compare the normalized candidate-rule sets across members.
        normalized_sets = [
            frozenset(_normalize_rule(rule) for rule in proposal.rules)
            for proposal in member_proposals
        ]
        first = normalized_sets[0]
        if any(normalized_set != first for normalized_set in normalized_sets[1:]):
            counts = [len(proposal.rules) for proposal in member_proposals]
            needs_review.append(
                PartitionFlag(
                    kind=PartitionFlagKind.boundary_disagreement,
                    segment_index=segment.index,
                    reason=(
                        f"ensemble members proposed different candidate sets "
                        f"(per-member candidate counts: {counts})"
                    ),
                )
            )
            continue

        # Unanimous agreement: use the first member's candidates (every member agreed on them).
        candidates.extend(_candidates_from_rules(segment, member_proposals[0].rules, len(candidates)))

    return SpecPartitionArtifact(
        document_hash=sha256_text(text),
        document_length=len(text),
        language=language,
        segments=classified,
        candidate_rules=candidates,
        needs_review=needs_review,
        ensemble_members=len(clients),
        provenance=dict(provenance) if provenance else {},
        ensemble_member_provenance=member_prov,
    )


def partition_spec_document(
    text: str,
    *,
    clients: list[object] | None = None,
    language: str = "en",
    provenance: dict[str, str] | None = None,
    member_provenance: list[dict[str, str]] | None = None,
) -> SpecPartitionArtifact:
    """Partition a spec document: dispatch on the number of partition clients.

    No clients → deterministic (no LLM). One client → single partitioner refinement. Two or
    more → cross-provider ensemble with boundary-disagreement flagging and the ≥2-distinct-family
    diversity check. This is the entry point ``partition-spec`` calls; it keeps the three
    drivers' preconditions in one place. ``member_provenance`` (one entry per client, from the
    factory's ``RoleProvenance``) is threaded to the LLM drivers so per-member provider families
    are recorded and the ensemble diversity is enforced.
    """
    if not clients:
        return partition_document_deterministic(text, language=language, provenance=provenance)
    if len(clients) == 1:
        return partition_document_with_client(
            text, clients[0], language=language, provenance=provenance, member_provenance=member_provenance
        )
    return partition_document_with_ensemble(
        text, clients, language=language, provenance=provenance, member_provenance=member_provenance
    )


def _segment_from_classified(classified: ClassifiedSegment) -> Segment:
    """Reconstruct the underlying ``Segment`` view of a ``ClassifiedSegment`` (flat-model helper)."""
    return Segment(
        index=classified.index,
        start=classified.start,
        end=classified.end,
        byte_start=classified.byte_start,
        byte_end=classified.byte_end,
        text=classified.text,
        kind=classified.segment_kind,
    )


# ---------------------------------------------------------------------------
# Per-candidate drafting batch (scope §4; HELPER iter-2)
# ---------------------------------------------------------------------------


def _normalize_controlled_for_agreement(text: str) -> str:
    """Normalize a drafted controlled text for ensemble agreement + the agreement hash.

    The agreement hash MUST match the form the package stores (``bound_ir.source.controlled_text``),
    which is the parser's ``normalize_controlled_text`` (dedented). Hashing the normalized text
    keeps the drafting-time agreement hash byte-consistent with the packaging-time binding
    (``_bind_agreement_hash``) so a pin stamped from an agreed draft validates.
    """
    return normalize_controlled_text(text)


def draft_candidate_rules(
    artifact: SpecPartitionArtifact,
    drafting_clients: list[object],
    *,
    language: str = "en",
    grammar_summary: str = "",
) -> SpecPartitionArtifact:
    """Draft each candidate rule into controlled text via the drafting role (scope §4).

    A generalization of ``draft_controlled_rewrite_with_llm`` to a BATCH over a partition's
    candidates. Each candidate rule (plain language) is drafted into DSL controlled text by the
    drafting client(s) (``LlmClient.propose_controlled_rewrite``). The ``[[NLR-CLARIFY]]`` sentinel
    discipline is preserved PER CANDIDATE: a candidate the drafter cannot state routes to the
    human queue via a ``needs_review`` flag (never a guessed controlled text).

      * ONE drafting client → each candidate's ``controlled_text`` is the single draft (no
        agreement hash; a single voice cannot satisfy the diversity requirement, so this path
        is for human-review routing, not machine pinning).
      * ≥2 drafting clients (a cross-provider ensemble) → each candidate is drafted under every
        member; if all members produce the SAME normalized text the candidate is AGREED and its
        ``controlled_text_agreement_hash`` is set to the canonical hash of the agreed text; a
        clarify (any member) or a disagreement (different texts) routes the candidate to the
        human queue as a ``boundary_disagreement`` / ``clarify`` flag (never silently resolved).

    Returns a NEW artifact: the partition segments are unchanged; candidates carry their drafted
    ``controlled_text`` (and ``controlled_text_agreement_hash`` when an ensemble agreed); drafting
    clarify/disagreement flags are appended to ``needs_review``. The original candidate list is
    preserved (a clarified/disagreed candidate stays listed with ``controlled_text=None`` so a
    human can see it), only the all-agreed candidates carry a controlled text.
    """
    from .intake import build_dsl_grammar_summary

    if not drafting_clients:
        raise ValueError(
            "draft_candidate_rules requires at least one drafting client (the drafting role); "
            "use partition_spec_document for partitioning without drafting"
        )
    summary = grammar_summary or build_dsl_grammar_summary()
    updated_candidates: list[CandidateRule] = []
    new_flags: list[PartitionFlag] = list(artifact.needs_review)

    for candidate in artifact.candidate_rules:
        drafts: list[str] = []
        clarify_reasons: list[str] = []
        for client in drafting_clients:
            draft = client.propose_controlled_rewrite(
                candidate.text, summary, language=language
            )
            if CROSS_LANGUAGE_CLARIFY_SENTINEL in draft:
                _, _, remainder = draft.partition(CROSS_LANGUAGE_CLARIFY_SENTINEL)
                clarify_reasons.append(remainder.strip() or "the drafter could not state the requirement")
            else:
                drafts.append(draft)

        if clarify_reasons:
            # A candidate any member could not state routes to the human queue. If ALL members
            # clarified it is a clarify; if only SOME did, members disagreed on whether the
            # candidate states a requirement at all → a boundary disagreement.
            if len(clarify_reasons) == len(drafting_clients):
                kind, reason = PartitionFlagKind.clarify, clarify_reasons[0]
            else:
                kind = PartitionFlagKind.boundary_disagreement
                reason = (
                    "drafting ensemble members disagreed: some could not state the candidate "
                    "(clarify) while others drafted it"
                )
            new_flags.append(
                PartitionFlag(
                    kind=kind,
                    segment_index=candidate.source_segment_index,
                    reason=f"candidate {candidate.index}: {reason}",
                )
            )
            updated_candidates.append(candidate)
            continue

        if len(drafting_clients) == 1:
            updated_candidates.append(
                candidate.model_copy(update={"controlled_text": drafts[0]})
            )
            continue

        # ≥2 members: compare normalized controlled texts.
        normalized = [_normalize_controlled_for_agreement(d) for d in drafts]
        if any(norm != normalized[0] for norm in normalized[1:]):
            new_flags.append(
                PartitionFlag(
                    kind=PartitionFlagKind.boundary_disagreement,
                    segment_index=candidate.source_segment_index,
                    reason=(
                        f"candidate {candidate.index}: drafting ensemble members produced "
                        "different controlled texts (boundary disagreement)"
                    ),
                )
            )
            updated_candidates.append(candidate)
            continue

        # Unanimous agreement: record the agreed controlled text + its canonical hash (the form
        # the package stores, so a downstream machine pin validates against the packaged text).
        agreed_text = drafts[0]
        agreed_hash = sha256_text(normalized[0])
        updated_candidates.append(
            candidate.model_copy(
                update={"controlled_text": agreed_text, "controlled_text_agreement_hash": agreed_hash}
            )
        )

    return SpecPartitionArtifact(
        document_hash=artifact.document_hash,
        document_length=artifact.document_length,
        language=language,
        segments=artifact.segments,
        candidate_rules=updated_candidates,
        needs_review=new_flags,
        ensemble_members=artifact.ensemble_members,
        provenance=artifact.provenance,
        ensemble_member_provenance=artifact.ensemble_member_provenance,
    )
