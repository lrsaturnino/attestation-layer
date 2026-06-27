# ADR 0207: Spec Partitioning as Proposal-Only with Deterministic Total Segmentation

## Status

Accepted and shipped (three-zone scope P2, Zone 1). The module `src/nlreq/spec_partition.py`, the
`partition-spec` CLI, and the `partition` role (`model_config.Role.partition`) implement spec
partitioning: a whole prose document becomes an exhaustive segmentation plus an N-sized
candidate-rule list, with every segment classified and nothing silently dropped. This is the
companion to ADR 0206 (the machine-pinning provenance axis) and ADR 0208 (the `machine_agreement`
trust state); it records the second of the scope's three ADR seeds (§10).

## Context

nlreq validates one controlled requirement at a time, and `intake-draft` is hard-pinned to one rule
per document (`intake.py`): feeding a multi-section spec yields one compressed rule, empirically
observed. Turning a multi-feature prose document into N atomic, one-meaning candidate rules was
hand-work — the first of the three manual steps the three-zone scope removes.

The scope's acceptance criterion 6 requires the partitioner's segmentation to be **deterministic and
total** ("every byte in exactly one classified segment; extracted ∪ excluded == the full
segmentation"). A prior design phrased completeness as "all behavioral-candidate spans", which had
no deterministic definition — there was no oracle a completeness test could check against. This ADR
records the resolution: the deterministic segmentation IS the oracle.

## Decision

### 1. Deterministic total segmentation runs first, before any LLM call

`spec_partition.segment_document` partitions the document into an exhaustive, ordered set of
character-disjoint segments by structural kind (`heading` / `list_item` / `paragraph` / `separator`)
using `str.splitlines(keepends=True)`, so concatenating every segment reproduces the document
exactly. The totality invariants are:

- the union of every segment's code-point span `[start, end)` is exactly `[0, len(text))` and
  consecutive segments are contiguous, so `segment.text == document[start:end]` (the in-process
  `str` round-trip), and
- the union of every segment's UTF-8 byte span `[byte_start, byte_end)` is exactly
  `[0, len(text.encode("utf-8")))` — **every byte is in exactly one segment** (AC6 literally), and
  `segment_text_from_bytes(document, segment)` recovers the same text for a byte-oriented consumer.

Both spans are carried because AC6 names the byte as the unit of totality, while a `str` can only be
sliced by code-point offsets. For ASCII the two coincide; for multibyte text the byte span is wider.
This segmentation is the **completeness oracle** the rest of Zone 3 checks against.

### 2. Every segment is classified, with a recorded reason — never a silent drop

`classify_segment` labels every segment `behavioral_candidate`, `non_behavioral`, or
`needs_clarification`, each with a recorded reason. Structural segments (headings, separators) and
clearly-meta prose (references / notes / examples / comments) are `non_behavioral` and are **excluded
from the candidate list but recorded in the artifact with their reason** — so `extracted` (the
candidate rules' source segments) ∪ `excluded` (the non-behavioral segments) equals the full
segmentation. The heuristic leans behavioral for ambiguous prose/list items to minimize silent drops
of real requirements (especially in non-English documents where modal-verb detection is unreliable).

### 3. The LLM partitioner is proposal-only

For each behavioral segment, the `partition` role (built via `build_client_for_role('partition',
config)`) proposes one or more atomic, single-meaning candidate rules **as plain language, not
controlled DSL** — drafting into the DSL is a separate, later role (`draft_candidate_rules`
generalizes `draft_controlled_rewrite_with_llm` to a batch). The partitioner never decides anything:

- each candidate's source span is computed deterministically by locating the rule text inside its
  segment (whole-segment fallback when paraphrased), never trusted from the model;
- a segment the model cannot state a clear requirement for emits the `[[NLR-CLARIFY]]` sentinel and
  routes to `needs_review` (never a guessed candidate), preserving the same low-confidence refusal
  discipline drafting uses;
- an unparseable response routes to `needs_review` rather than a silent empty candidate list.

### 4. Ensemble partitioning flags boundary disagreements, never resolves them

`partition_document_with_ensemble` runs the partitioner under ≥2 cross-provider clients. Because the
segmentation is deterministic, every member sees the same segments; the disagreement axis is the
per-segment candidate proposal. If members propose different normalized rule sets (one merges what
another splits), or some clarify while others propose, the segment routes to `needs_review` as a
`boundary_disagreement` and its candidates are NOT silently resolved — only unanimously-agreed
segments contribute candidates. The exported ensemble API REQUIRES per-member provenance (one entry
per client, from the factory's `RoleProvenance`) and enforces ≥2 distinct provider **families**
(see ADR 0208 §3 — two distinct providers can still be the same family), so a same-family ensemble
whose correlated training bias would defeat the diversity gate cannot run silently.

### 5. The role is named `partition`

The scope adds a sixth role to the per-role enum (`drafting`, `decomposition`, `impact`,
`extraction`, `audit` `+ partition`). It is named `partition`, deliberately distinct from the
existing `decomposition` (controlled requirement → IR) and `extraction` (Specula `S` extraction)
roles, to avoid collision. `partition` is an `LlmClient`-backed role (it proposes plain-language
candidate rules; it does not produce evidence).

### 6. The output is a single human-scannable manifest

`SpecPartitionArtifact` records the document hash + length + language, every classified segment (with
both spans, classification, and reason), the candidate rules (with spans and, after drafting, their
controlled text + agreement hash), the `needs_review` flags, and the ensemble member provenance. A
human scans this manifest in seconds to confirm boundaries — the one cheap early touch the scope
allows.

## Alternatives Considered

- **LLM-only segmentation (let the model partition the document).** Rejected: it leaves no
  deterministic completeness oracle, so AC6's "every byte in exactly one classified segment" is
  unprovable and a dropped requirement is undetectable. The deterministic segmentation runs first and
  is total; the LLM only proposes candidate rules within behavioral segments.

- **Reuse the `decomposition` role name.** Rejected: `decomposition` already names the
  controlled-requirement → IR role, and `extraction` names Specula `S` extraction. A document
  partitioner is a distinct concern; reusing either name would collide and confuse per-role config.

- **Trust model-reported candidate spans.** Rejected: a span must be traceable to a real document
  offset for the human to jump to. Spans are computed by locating the rule text inside its segment
  (whole-segment fallback), never read from the model.

- **Carry a single code-point span only.** Rejected: AC6 names the byte as the unit of totality, and
  a `str` cannot be sliced by byte offsets. Both a code-point span (the in-process `str` round-trip)
  and a UTF-8 byte span (the byte-totality oracle) are carried.

- **Silently resolve ensemble boundary disagreements (e.g. take the union or the first member).**
  Rejected (scope §4): a disagreement on where a rule's boundary lies is exactly the signal a human
  should see. Disagreements route to `needs_review`; only unanimous segments contribute candidates.

## Consequences

- The segmentation is deterministic and total over both code points and bytes, so a completeness test
  has a real oracle: `test_segmentation_totality_and_round_trip_hold_for_non_ascii` pins both
  totalities and both round-trips with a CJK + accented-Latin + emoji document.
- Every segment carries a classification and a reason; non-behavioral segments are excluded but
  recorded, so no requirement is silently dropped.
- The partitioner is proposal-only: it produces a manifest a human confirms, and every low-confidence
  or disagreed case routes to `needs_review` rather than a guessed candidate.
- The `SpecPartitionArtifact` is the basis the Zone 3 `attest-spec` orchestrator consumes, and its
  ensemble member provenance is the evidence the machine-agreement diversity gate (ADR 0208) checks
  the partition-ensemble against — so a deterministic or single-family partition can never let a rule
  auto-advance.
