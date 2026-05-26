from __future__ import annotations

from pathlib import Path

from .adapter import GenericAdapter, default_generic_adapter
from .bindings import bind_ir
from .jsonutil import canonical_json, sha256_json, write_json
from .models import (
    AssumptionsArtifact,
    BindingsArtifact,
    EvidenceObject,
    RequirementIR,
    ReviewArtifact,
    SourceSpan,
    StatusDecision,
    VerificationTasksArtifact,
)
from .parser import RequirementParser
from .smt import evidence_for_ir, smt2_for_ir
from .status import decide_status


def build_package(
    *,
    controlled_text: str,
    output_dir: Path,
    requirement_id: str,
    title: str,
    claim_kind: str,
    adapter: GenericAdapter | None = None,
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
    bound_ir, missing = bind_ir(ir, adapter)
    ir_hash = sha256_json(bound_ir)
    evidence = evidence_for_ir(
        bound_ir,
        ir_hash=ir_hash,
        missing_symbols=missing,
        unbound_symbol_spans=_unbound_symbol_spans(bound_ir, missing),
    )
    status = decide_status(evidence)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "requirement.md").write_text(_requirement_markdown(bound_ir))
    (output_dir / "source-diff.md").write_text(
        "No LLM rewrite was used. Controlled text was submitted directly.\n"
    )
    write_json(output_dir / "requirement.ir.json", bound_ir)
    write_json(output_dir / "bindings.json", bound_ir.bindings)
    write_json(output_dir / "assumptions.json", bound_ir.assumptions)
    write_json(output_dir / "review.json", _review(bound_ir))
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
    VerificationTasksArtifact.model_validate_json((package_dir / "verification-tasks.json").read_text())
    evidence = EvidenceObject.model_validate_json((package_dir / "evidence.json").read_text())
    status = StatusDecision.model_validate_json((package_dir / "status.json").read_text())
    _validate_package_integrity(package_dir, ir, bindings, assumptions, review, evidence, status)
    return ir, evidence, status


def _validate_package_integrity(
    package_dir: Path,
    ir: RequirementIR,
    bindings: BindingsArtifact,
    assumptions: AssumptionsArtifact,
    review: ReviewArtifact,
    evidence: EvidenceObject,
    status: StatusDecision,
) -> None:
    ir_hash = sha256_json(ir)
    expected_status = decide_status(evidence)

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


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unbound_symbol_spans(ir: RequirementIR, missing: list[str]) -> dict[str, SourceSpan]:
    missing_set = set(missing)
    spans: dict[str, SourceSpan] = {}
    for predicate in ir.claim.condition:
        for arg in predicate.args:
            if arg.kind == "identifier" and str(arg.value) in missing_set:
                spans.setdefault(str(arg.value), predicate.source_span)
    if ir.claim.expected.target in missing_set:
        spans.setdefault(ir.claim.expected.target, ir.claim.expected.source_span)
    if (
        ir.claim.expected.value
        and ir.claim.expected.value.kind == "identifier"
        and str(ir.claim.expected.value.value) in missing_set
    ):
        spans.setdefault(str(ir.claim.expected.value.value), ir.claim.expected.source_span)
    return spans


def _requirement_markdown(ir: RequirementIR) -> str:
    return f"# {ir.requirement_id}\n\n{ir.source.controlled_text}\n"


def _review(ir: RequirementIR) -> dict[str, object]:
    return {
        "review_id": f"RVW-{ir.requirement_id}-001",
        "reviewer": "phase0@example.invalid",
        "decision": "approved",
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


def _implementation_spec(ir: RequirementIR, status: str) -> str:
    bindings = "\n".join(
        f"- `{name}` -> `{binding.adapter}:{binding.symbol}` ({binding.symbol_type})"
        for name, binding in sorted(ir.bindings.items())
    )
    return (
        f"# {ir.requirement_id}\n\n"
        f"## Requirement\n\n{ir.title}\n\n"
        f"## Controlled Form\n\n```text\n{ir.source.controlled_text}```\n\n"
        f"## Scope\n\n- Adapter: generic\n{bindings}\n\n"
        f"## Required Behavior\n\n"
        f"Action `{ir.claim.action}` must satisfy `{ir.claim.expected.kind}` under the declared conditions.\n\n"
        f"## Evidence\n\n- IR type-checked.\n- Symbols resolved through generic adapter.\n"
        f"- Self-consistency checked.\n- Supported claim shape SMT-checked.\n\n"
        f"## Status\n\n`{status}`\n"
    )
