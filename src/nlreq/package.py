from __future__ import annotations

from pathlib import Path

from .adapter import GenericAdapter, default_generic_adapter
from .bindings import bind_ir_with_diagnostics
from .jsonutil import sha256_json, sha256_text, write_json
from .models import (
    AssumptionsArtifact,
    BindingsArtifact,
    EvidenceObject,
    PinningProvenance,
    RequirementIR,
    ReviewArtifact,
    SourceSpan,
    StatusDecision,
    VerificationTasksArtifact,
    is_real_human_review,
)
from .parser import RequirementParser
from .smt import evidence_for_ir, smt2_for_ir
from .status import decide_status


# The pinning-provenance artifact filename written into a package directory when the package is
# machine-pinned (three-zone scope §6/§7). Its presence (and a ``machine_agreement`` kind) is the
# signal ``validate_package`` / ``decide_status`` consult to resolve the non-``ACCEPTED``
# machine-pinned status; its ABSENCE is the default (byte-identical to today, AC1).
PINNING_PROVENANCE_FILENAME = "pinning-provenance.json"


def build_package(
    *,
    controlled_text: str,
    output_dir: Path,
    requirement_id: str,
    title: str,
    claim_kind: str,
    adapter: GenericAdapter | None = None,
    pinning: PinningProvenance | None = None,
) -> None:
    adapter = adapter or default_generic_adapter()
    parser = RequirementParser()
    ir = parser.parse_ir(
        controlled_text,
        requirement_id=requirement_id,
        title=title,
        claim_kind=claim_kind,
        approved_by="phase0@example.invalid",
        approved_at="2026-05-26T00:00:00Z",
    )
    binding = bind_ir_with_diagnostics(ir, adapter)
    bound_ir = binding.bound_ir
    ir_hash = sha256_json(bound_ir)
    evidence = evidence_for_ir(
        bound_ir,
        ir_hash=ir_hash,
        missing_symbols=binding.missing_symbols,
        ambiguous_symbols=binding.ambiguous_symbols,
        ambiguous_symbol_spans=_symbol_spans(bound_ir, binding.ambiguous_symbols),
        unbound_symbol_spans=_symbol_spans(bound_ir, binding.missing_symbols),
    )
    # The pinning record (a separate provenance axis from evidence, scope §6) is consulted by
    # ``decide_status``: a ``machine_agreement`` pin resolves the package to the non-``ACCEPTED``
    # ``MACHINE_PINNED_PENDING_REVIEW`` status; ``None`` (the default) is byte-identical to today.
    # A machine pin is BOUND to the package's actual meaning (HELPER iter-2): the pin's
    # ``agreement_hash`` MUST equal the canonical hash of the controlled text the package embodies,
    # so a pin stamped on a package whose meaning differs from what the ensemble agreed on is
    # refused — the pin can never be detached from the meaning it pins.
    if pinning is not None and pinning.kind == "machine_agreement":
        _bind_agreement_hash(pinning, bound_ir.source.controlled_text)
    status = decide_status(evidence, pinning)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "requirement.md").write_text(_requirement_markdown(bound_ir))
    (output_dir / "source-diff.md").write_text(
        "No LLM rewrite was used. Controlled text was submitted directly.\n"
    )
    write_json(output_dir / "requirement.ir.json", bound_ir)
    write_json(output_dir / "bindings.json", bound_ir.bindings)
    write_json(output_dir / "assumptions.json", bound_ir.assumptions)
    # A machine-pinned package MUST NOT carry the fabricated ``approved`` review (scope §2/§6): it
    # carries a ``needs_review`` review (honest — the meaning was machine-pinned, pending human
    # review) PLUS the ``machine_agreement`` pinning record. A human-reviewed or default package
    # carries the fabricated/default approved review unchanged (AC1 byte-identity).
    machine_pinned = pinning is not None and pinning.kind == "machine_agreement"
    write_json(output_dir / "review.json", _review(bound_ir, machine_pinned=machine_pinned))
    if machine_pinned:
        write_json(output_dir / PINNING_PROVENANCE_FILENAME, pinning)
    write_json(output_dir / "verification-tasks.json", adapter.generate_tasks(bound_ir))
    write_json(output_dir / "evidence.json", evidence)
    write_json(output_dir / "status.json", status)
    (output_dir / "implementation-spec.md").write_text(_implementation_spec(bound_ir, status.status.value))
    (output_dir / "smt" / "C1.smt2").parent.mkdir(exist_ok=True)
    (output_dir / "smt" / "C1.smt2").write_text(smt2_for_ir(bound_ir))


def validate_package(package_dir: Path) -> tuple[RequirementIR, object, object]:
    ir = RequirementIR.model_validate_json((package_dir / "requirement.ir.json").read_text())
    bindings = BindingsArtifact.model_validate_json((package_dir / "bindings.json").read_text())
    assumptions = AssumptionsArtifact.model_validate_json((package_dir / "assumptions.json").read_text())
    review = ReviewArtifact.model_validate_json((package_dir / "review.json").read_text())
    tasks = VerificationTasksArtifact.model_validate_json(
        (package_dir / "verification-tasks.json").read_text()
    )
    evidence = EvidenceObject.model_validate_json((package_dir / "evidence.json").read_text())
    status = StatusDecision.model_validate_json((package_dir / "status.json").read_text())
    # Load the pinning record when present (a machine-pinned package carries one). Its absence is
    # the default (byte-identical to today, AC1); ``decide_status`` is then called with ``None``.
    pinning = _load_pinning(package_dir)
    _validate_package_integrity(
        package_dir, ir, bindings, assumptions, review, tasks, evidence, status, pinning
    )
    return ir, evidence, status


def promote_machine_pinned_package(
    package_dir: Path,
    *,
    review_event: ReviewArtifact,
    promoted_at: str = "2026-06-26T00:00:00Z",
) -> StatusDecision:
    """Promote a machine-pinned package to ``human_review`` after a REAL human review (scope §6).

    Promotion is upward only: the package MUST currently be machine-pinned
    (``pinning-provenance.json`` carries a ``machine_agreement`` record). An APPROVED real human
    review event (``review_origin="human"``, non-placeholder reviewer, ``decision="approved"``)
    whose ``requirement_ir`` hash matches the package's IR backs a NEW ``human_review``
    ``PinningProvenance`` — bound to the package's actual meaning (the hash the human reviewed), so
    the pin can never be detached from the meaning it pins. A ``rejected`` or ``needs_review`` human
    review is refused (it is not an upward step) and the package is left machine-pinned, unchanged. ``decide_status`` is re-resolved under the human pin: a fully-evidenced package resolves
    to ``ACCEPTED_WITH_EVIDENCE`` (human-accepted), so the former prefix-check consumers now treat
    it as accepted (acceptance #3 reversed by promotion). The package's ``review.json`` becomes the
    REAL human review (no longer the fabricated ``needs_review``), ``pinning-provenance.json``
    becomes the ``human_review`` record, and ``status.json`` / ``implementation-spec.md`` are
    re-resolved. ``validate_package`` continues to pass: the review's ``requirement_ir`` hash
    matches, the status matches ``decide_status(evidence, human_pinning)``, and the
    machine-pinning integrity branch no longer applies.
    """
    ir = RequirementIR.model_validate_json((package_dir / "requirement.ir.json").read_text())
    evidence = EvidenceObject.model_validate_json((package_dir / "evidence.json").read_text())
    existing_pinning = _load_pinning(package_dir)
    if existing_pinning is None or existing_pinning.kind != "machine_agreement":
        raise ValueError(
            "promote_machine_pinned_package requires a machine-pinned package (a "
            "machine_agreement pinning-provenance.json); promotion is upward only "
            "(machine_agreement → human_review)"
        )
    ir_hash = sha256_json(ir)
    # The human review event must be REAL (review_origin='human') and BOUND to this package's IR —
    # the meaning the human reviewed. The PinningProvenance(kind='human_review') guard re-checks
    # the human origin; this check binds it to THIS package's meaning (the hash the human reviewed).
    if not is_real_human_review(review_event):
        raise ValueError(
            "the review event is not a real human review (review_origin != 'human'); a "
            "human_review pin must be backed by a real human review event, not a fabricated "
            "package-builder approval"
        )
    # Promotion is upward ONLY: a machine-pinned rule is promoted to human_review iff a human
    # APPROVED the meaning. A real human review whose decision is ``rejected`` or ``needs_review``
    # is not an upward step — it leaves the package machine-pinned (unchanged). Refused here, BEFORE
    # constructing the pin or writing any artifact, so a non-approving review never mutates the
    # package. (The PinningProvenance(kind='human_review') construction guard enforces the same
    # invariant; this explicit check gives a clear, promotion-specific message and a no-write refusal.)
    if review_event.decision != "approved":
        raise ValueError(
            "the human review event did not approve the meaning "
            f"(decision={review_event.decision!r}); promotion is upward only — only an APPROVED "
            "human review promotes a machine-pinned rule to human_review. A 'rejected' or "
            "'needs_review' human review leaves the package machine-pinned and unchanged"
        )
    if review_event.reviewed_hashes.get("requirement_ir") != ir_hash:
        raise ValueError(
            "the human review event's requirement_ir hash does not match this package's IR; a "
            "human_review pin must be bound to the package's actual meaning (the hash the human "
            "reviewed), never detached from it"
        )
    human_pinning = PinningProvenance(
        kind="human_review",
        review_event=review_event,
        timestamp=promoted_at,
    )
    status = decide_status(evidence, human_pinning)
    # Rewrite the package: the real human review, the human_review pin, the re-resolved status.
    write_json(package_dir / "review.json", review_event)
    write_json(package_dir / PINNING_PROVENANCE_FILENAME, human_pinning)
    write_json(package_dir / "status.json", status)
    (package_dir / "implementation-spec.md").write_text(_implementation_spec(ir, status.status.value))
    return status


def _load_pinning(package_dir: Path) -> PinningProvenance | None:
    """Load the package's ``pinning-provenance.json`` when present, else None (the default)."""
    path = package_dir / PINNING_PROVENANCE_FILENAME
    if not path.is_file():
        return None
    return PinningProvenance.model_validate_json(path.read_text())


def _validate_package_integrity(
    package_dir: Path,
    ir: RequirementIR,
    bindings: BindingsArtifact,
    assumptions: AssumptionsArtifact,
    review: ReviewArtifact,
    tasks: VerificationTasksArtifact,
    evidence: EvidenceObject,
    status: StatusDecision,
    pinning: PinningProvenance | None = None,
) -> None:
    ir_hash = sha256_json(ir)
    expected_status = decide_status(evidence, pinning)

    _expect(bindings.root == ir.bindings, "bindings.json does not match requirement.ir.json")
    _expect(assumptions.root == ir.assumptions, "assumptions.json does not match requirement.ir.json")
    _expect(
        review.reviewed_hashes.get("requirement_ir") == ir_hash,
        "review.json requirement_ir hash does not match requirement.ir.json",
    )
    _expect(evidence.requirement_id == ir.requirement_id, "evidence.json requirement_id does not match IR")
    _expect(evidence.ir_hash == ir_hash, "evidence.json ir_hash does not match requirement.ir.json")
    _expect(status == expected_status, "status.json does not match pure status decision")
    _expect(
        tasks.root == default_generic_adapter().generate_tasks(ir),
        "verification-tasks.json does not match requirement.ir.json",
    )
    _expect(
        (package_dir / "requirement.md").read_text() == _requirement_markdown(ir),
        "requirement.md does not match requirement.ir.json",
    )
    _expect(
        (package_dir / "source-diff.md").read_text()
        == "No LLM rewrite was used. Controlled text was submitted directly.\n",
        "source-diff.md does not match Phase 0 package source policy",
    )
    _expect(
        (package_dir / "implementation-spec.md").read_text()
        == _implementation_spec(ir, status.status.value),
        "implementation-spec.md does not match requirement.ir.json and status.json",
    )
    _expect(
        (package_dir / "smt" / "C1.smt2").read_text() == smt2_for_ir(ir),
        "smt/C1.smt2 does not match requirement.ir.json",
    )
    # Machine-pinning integrity (scope §6): a ``machine_agreement`` pin requires a ``needs_review``
    # review (the fabricated ``approved`` review MUST NOT back a machine pin), the pinning record
    # must be present on disk, AND the pin's ``agreement_hash`` is BOUND to the package's actual
    # controlled text (HELPER iter-2): a pin whose hash differs from the packaged meaning is
    # refused. The default path (no pinning) is unconstrained (AC1).
    if pinning is not None and pinning.kind == "machine_agreement":
        _expect(
            review.decision == "needs_review",
            "a machine_agreement package must carry a needs_review review, not the fabricated "
            "approved package-builder review (a machine pin never fakes human approval)",
        )
        _expect(
            (package_dir / PINNING_PROVENANCE_FILENAME).is_file(),
            "a machine_agreement package must carry a pinning-provenance.json artifact",
        )
        _expect(
            pinning.ensemble.agreement.agreement_hash == sha256_text(ir.source.controlled_text),
            "a machine_agreement pin's agreement_hash must equal the canonical hash of the "
            "package's controlled text (the meaning the ensemble agreed on); a mismatch means the "
            "pin is not bound to this package's actual meaning",
        )
    # Promotion integrity (the upward-only path ``promote_machine_pinned_package`` is the only one
    # that writes a ``human_review`` pin): the on-disk ``review.json`` MUST be the same event the pin
    # embeds, and that event MUST be an APPROVED real human review. This ties the pin to
    # ``review.json`` so a promoted package cannot drift between ``pinning-provenance.json`` and
    # ``review.json``, and a human ``rejected`` / ``needs_review`` review can never validate as a
    # human acceptance (the construction guard refuses such a pin too; this catches on-disk tamper).
    elif pinning is not None and pinning.kind == "human_review":
        _expect(
            pinning.review_event == review,
            "a human_review pin's embedded review event must equal the package's review.json; a "
            "promoted package must not drift between pinning-provenance.json and review.json",
        )
        _expect(
            is_real_human_review(review),
            "a human_review package's review.json must be a real human review event "
            "(review_origin='human'), not a fabricated package-builder approval",
        )
        _expect(
            review.decision == "approved",
            "a human_review package's review.json must be an APPROVED human review; a 'rejected' or "
            "'needs_review' review can never pin a rule's meaning as human-accepted",
        )


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bind_agreement_hash(pinning: PinningProvenance, controlled_text: str) -> None:
    """Refuse a machine pin whose ``agreement_hash`` is not bound to the packaged controlled text.

    A ``machine_agreement`` pin records the content hash of the meaning the ensemble converged on
    (``EnsembleAgreementResult.agreement_hash``). For the pin to be MEANINGFUL it must equal the
    canonical hash of the controlled text the package actually embodies — otherwise the pin is
    detached from the meaning it claims to pin (HELPER iter-2: ``build_package`` previously accepted
    any valid ``PinningProvenance`` regardless of ``controlled_text``). Called at build time so a
    mismatched pin is refused before any artifact is written.
    """
    expected = sha256_text(controlled_text)
    if pinning.ensemble is None or pinning.ensemble.agreement.agreement_hash != expected:
        raise ValueError(
            "a machine_agreement pin's agreement_hash must equal the canonical hash of the "
            "controlled text being packaged (the meaning the ensemble agreed on); refusing to stamp "
            "a pin that is not bound to this package's actual meaning"
        )


def _symbol_spans(ir: RequirementIR, symbols: list[str]) -> dict[str, SourceSpan]:
    symbol_set = set(symbols)
    spans: dict[str, SourceSpan] = {}
    if ir.claim.action in symbol_set:
        action_span = _action_source_span(ir)
        if action_span:
            spans[ir.claim.action] = action_span
    for predicate in ir.claim.condition:
        for arg in predicate.args:
            if arg.kind == "identifier" and str(arg.value) in symbol_set:
                spans.setdefault(str(arg.value), predicate.source_span)
    if ir.claim.expected.target in symbol_set:
        spans.setdefault(ir.claim.expected.target, ir.claim.expected.source_span)
    if (
        ir.claim.expected.value
        and ir.claim.expected.value.kind == "identifier"
        and str(ir.claim.expected.value.value) in symbol_set
    ):
        spans.setdefault(str(ir.claim.expected.value.value), ir.claim.expected.source_span)
    return spans


def _action_source_span(ir: RequirementIR) -> SourceSpan | None:
    needle = f"then {ir.claim.action} must"
    start = ir.source.controlled_text.find(needle)
    if start < 0:
        return None
    start_char = start + len("then ")
    end_char = start_char + len(ir.claim.action)
    return SourceSpan(
        document="controlled_requirement",
        start_char=start_char,
        end_char=end_char,
        text=ir.source.controlled_text[start_char:end_char],
    )


def _requirement_markdown(ir: RequirementIR) -> str:
    return f"# {ir.requirement_id}\n\n{ir.source.controlled_text}\n"


def _review(ir: RequirementIR, *, reviewer: str = "phase0@example.invalid", machine_pinned: bool = False) -> dict[str, object]:
    # The fabricated default package-builder approval. This is NOT a real human review event: the
    # ``reviewer`` is a package-builder placeholder (``_is_placeholder_reviewer`` ->
    # ``phase<N>@example.invalid``). The non-human provenance is carried at the MODEL level, not
    # serialized here: ``ReviewArtifact.review_origin`` defaults to ``"package_builder"``, so a
    # review.json produced by this builder — and every legacy review.json written before that field
    # existed — loads as ``review_origin="package_builder"`` (explicitly non-human),
    # ``is_real_human_review`` returns False for it, and it can therefore never back a
    # ``PinningProvenance(kind="human_review")`` record (ADR 0206 §2; acceptance #5).
    #
    # AC1 byte-identity (acceptance #1): the ``review_origin`` field is deliberately NOT
    # serialized by the default package builders, so the default pipeline output is byte-identical
    # to the pre-machine-pinning pipeline. The stamping-path change is live: a
    # MACHINE-PINNED package (``machine_pinned=True``) carries a ``needs_review`` decision here
    # (never the fabricated ``approved``) PLUS a ``machine_agreement`` pinning record, so a machine
    # pin never fakes human approval (scope §2/§6; acceptance #2). The default/human path
    # (``machine_pinned=False``) is byte-identical to the pre-pinning pipeline.
    decision = "needs_review" if machine_pinned else "approved"
    return {
        "review_id": f"RVW-{ir.requirement_id}-001",
        "reviewer": reviewer,
        "decision": decision,
        "self_audit": False,
        "reviewed_hashes": {"requirement_ir": sha256_json(ir)},
        "checklist": {
            "controlled_form_matches_intent": "pass",
            "claim_shape_matches_controlled_form": "pass",
            "source_spans_present": "pass",
            "assumptions_explicit": "pass",
            "bindings_justified": "pass",
            "evidence_level_appropriate": "pass",
            "unsupported_claims_hidden": "pass",
        },
        "timestamp": "2026-05-26T00:00:00Z",
    }


def _implementation_spec(
    ir: RequirementIR,
    status: str,
    *,
    adapter_id: str = "generic",
    evidence_lines: list[str] | None = None,
) -> str:
    bindings = "\n".join(
        f"- `{name}` -> `{binding.adapter}:{binding.symbol}` ({binding.symbol_type})"
        for name, binding in sorted(ir.bindings.items())
    )
    if evidence_lines is None:
        evidence_lines = [
            "IR type-checked.",
            "Symbols resolved through generic adapter.",
            "Self-consistency checked.",
            "Supported claim shape SMT-checked.",
        ]
    evidence = "\n".join(f"- {line}" for line in evidence_lines)
    return (
        f"# {ir.requirement_id}\n\n"
        f"## Requirement\n\n{ir.title}\n\n"
        f"## Controlled Form\n\n```text\n{ir.source.controlled_text}```\n\n"
        f"## Scope\n\n- Adapter: {adapter_id}\n{bindings}\n\n"
        f"## Required Behavior\n\n"
        f"Action `{ir.claim.action}` must satisfy `{ir.claim.expected.kind}` under the declared conditions.\n\n"
        f"## Evidence\n\n{evidence}\n\n"
        f"## Status\n\n`{status}`\n"
    )
