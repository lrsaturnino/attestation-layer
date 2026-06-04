from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .formal_claim import build_formal_claim, formal_claim_signature
from .jsonutil import canonical_json, sha256_json
from .models import Approval, RequirementIRV2, SemanticNode, SourceSpan, ValueRef


TRANSLATOR_AGREEMENT_SCHEMA_VERSION = "0.1"


class TranslationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translator_id: str
    method: Literal["deterministic", "manual", "llm"]
    requirement: RequirementIRV2
    approval: Approval | None = None
    provenance: dict[str, str] = Field(default_factory=dict)


class TranslationAgreementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATOR_AGREEMENT_SCHEMA_VERSION
    candidates: list[TranslationCandidate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_translators(self) -> TranslationAgreementInput:
        translator_ids = [candidate.translator_id for candidate in self.candidates]
        if len(translator_ids) != len(set(translator_ids)):
            raise ValueError("translator_id values must be unique")
        return self


class TranslationDisagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_translator_id: str
    right_translator_id: str
    path: str
    reason: str
    left_fragment: dict[str, Any] | None = None
    right_fragment: dict[str, Any] | None = None
    source_spans: list[SourceSpan] = Field(default_factory=list)


class TranslationClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    path: str
    translator_ids: list[str]


class TranslationAgreementReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = TRANSLATOR_AGREEMENT_SCHEMA_VERSION
    requirement_id: str
    status: Literal["agreed", "disagreed", "needs_review"]
    candidate_hashes: dict[str, str]
    disagreements: list[TranslationDisagreement] = Field(default_factory=list)
    clarifications: list[TranslationClarification] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


def build_translation_agreement_report(
    agreement_input: TranslationAgreementInput,
) -> TranslationAgreementReport:
    requirement_id = agreement_input.candidates[0].requirement.requirement_id
    candidate_hashes = {
        candidate.translator_id: sha256_json(candidate.requirement)
        for candidate in agreement_input.candidates
    }
    blockers: list[str] = []
    if len(agreement_input.candidates) < 2:
        blockers.append("translator agreement requires at least two candidates")
    for candidate in agreement_input.candidates:
        if candidate.requirement.requirement_id != requirement_id:
            blockers.append("all candidates must target the same requirement_id")
        if candidate.method == "llm" and (
            candidate.approval is None or candidate.approval.status != "approved"
        ):
            blockers.append(
                f"LLM candidate {candidate.translator_id} requires explicit approval"
            )

    # Only run the disagreement check over approved candidates: unapproved LLM
    # candidates must block as needs_review BEFORE their IR drives a disagreement
    # decision.  A missing approval is a process blocker, not a semantic finding.
    approved_candidates = [
        c for c in agreement_input.candidates
        if c.method != "llm" or (c.approval is not None and c.approval.status == "approved")
    ]
    disagreements = _disagreements(approved_candidates)
    clarifications = [
        TranslationClarification(
            question_id=f"clarify-{index}",
            question=(
                "Clarify the intended formal structure for the disagreeing "
                f"fragment at {disagreement.path}."
            ),
            path=disagreement.path,
            translator_ids=[
                disagreement.left_translator_id,
                disagreement.right_translator_id,
            ],
        )
        for index, disagreement in enumerate(disagreements, start=1)
    ]
    # Precedence: blockers (unapproved candidates, wrong ids) win over disagreements.
    if blockers:
        status: Literal["agreed", "disagreed", "needs_review"] = "needs_review"
    elif disagreements:
        status = "disagreed"
    else:
        status = "agreed"
    return TranslationAgreementReport(
        requirement_id=requirement_id,
        status=status,
        candidate_hashes=candidate_hashes,
        disagreements=disagreements,
        clarifications=clarifications,
        blockers=blockers,
    )


def _formal_claim_sig(requirement: RequirementIRV2) -> str | None:
    """Return the normalised FormalClaim signature for a requirement, or None on failure."""
    try:
        report = build_formal_claim(requirement)
        if report.formal_claim is not None:
            return formal_claim_signature(
                report.formal_claim,
                alpha_identifiers=True,
                commutative=True,
            )
    except Exception:
        pass
    return None


def _disagreements(candidates: list[TranslationCandidate]) -> list[TranslationDisagreement]:
    if len(candidates) < 2:
        return []
    baseline = candidates[0]
    baseline_fc_sig = _formal_claim_sig(baseline.requirement)
    disagreements: list[TranslationDisagreement] = []
    for candidate in candidates[1:]:
        candidate_fc_sig = _formal_claim_sig(candidate.requirement)

        # When both candidates lower to a FormalClaim, use the normalised signature
        # (alpha-renamed, commutative) as the primary agreement predicate.  Fall back
        # to the structural SemanticNode diff to find spans when the signatures differ.
        if baseline_fc_sig is not None and candidate_fc_sig is not None:
            if baseline_fc_sig == candidate_fc_sig:
                continue
            # Signatures differ — locate source spans via structural diff for UX.
            baseline_struct = _node_signature(baseline.requirement.semantic_ir)
            candidate_struct = _node_signature(candidate.requirement.semantic_ir)
            diff = _first_diff(baseline_struct, candidate_struct, path="semantic_ir")
            path = diff[0] if diff else "semantic_ir"
            left_fragment = diff[1] if diff else None
            right_fragment = diff[2] if diff else None
            reason = (
                f"formal-claim signatures differ (alpha-renamed, commutative): "
                f"baseline={baseline_fc_sig[:40]}… candidate={candidate_fc_sig[:40]}…"
            )
            disagreements.append(
                TranslationDisagreement(
                    left_translator_id=baseline.translator_id,
                    right_translator_id=candidate.translator_id,
                    path=path,
                    reason=reason,
                    left_fragment=left_fragment,
                    right_fragment=right_fragment,
                    source_spans=_spans_for_path(candidate.requirement.semantic_ir, path),
                )
            )
        else:
            # One or both candidates did not lower to a FormalClaim.  Fall back to
            # structural SemanticNode comparison so we do not silently agree.
            baseline_signature = _node_signature(baseline.requirement.semantic_ir)
            candidate_signature = _node_signature(candidate.requirement.semantic_ir)
            diff = _first_diff(baseline_signature, candidate_signature, path="semantic_ir")
            if diff is not None:
                path, left_fragment, right_fragment, reason = diff
                disagreements.append(
                    TranslationDisagreement(
                        left_translator_id=baseline.translator_id,
                        right_translator_id=candidate.translator_id,
                        path=path,
                        reason=reason,
                        left_fragment=left_fragment,
                        right_fragment=right_fragment,
                        source_spans=_spans_for_path(candidate.requirement.semantic_ir, path),
                    )
                )
    return disagreements


def _node_signature(node: SemanticNode) -> dict[str, Any]:
    return {
        "kind": node.kind,
        "name": node.name,
        "target": node.target,
        "args": [_value_signature(arg) for arg in node.args],
        "temporal_bound": (
            node.temporal_bound.model_dump(mode="json") if node.temporal_bound else None
        ),
        "scope": [_node_signature(child) for child in node.scope],
        "premise": _node_signature(node.premise) if node.premise else None,
        "obligation": _node_signature(node.obligation) if node.obligation else None,
        "action": _node_signature(node.action) if node.action else None,
        "must": _node_signature(node.must) if node.must else None,
        "children": [_node_signature(child) for child in node.children],
        "left": _edge_signature(node.left),
        "right": _edge_signature(node.right),
    }


def _value_signature(value: ValueRef) -> dict[str, Any]:
    return {"kind": value.kind, "value": value.value}


def _edge_signature(value: SemanticNode | ValueRef | None) -> dict[str, Any] | None:
    if isinstance(value, SemanticNode):
        return _node_signature(value)
    if isinstance(value, ValueRef):
        return _value_signature(value)
    return None


def _first_diff(
    left: Any, right: Any, *, path: str
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, str] | None:
    if type(left) is not type(right):
        return (path, _fragment(left), _fragment(right), "fragment type differs")
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                nested = _first_diff(left.get(key), right.get(key), path=f"{path}.{key}")
                if nested is not None:
                    return nested
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return (path, _fragment(left), _fragment(right), "list length differs")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            nested = _first_diff(left_item, right_item, path=f"{path}[{index}]")
            if nested is not None:
                return nested
        return None
    if left != right:
        return (path, _fragment(left), _fragment(right), "value differs")
    return None


def _fragment(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": value}


def spans_for_path(root: SemanticNode, path: str) -> list[SourceSpan]:
    """Return source spans from `root` for the given structural dot-path.

    Returns spans from the resolved node if it exists, or an empty list if the
    path does not resolve (e.g. the candidate IR diverged structurally from the
    original and the path has no counterpart node).
    """
    node = _node_for_path(root, path)
    return node.source_spans if node is not None else []


# Private alias kept for internal callers.
_spans_for_path = spans_for_path


def _node_for_path(root: SemanticNode, path: str) -> SemanticNode | None:
    if path == "semantic_ir":
        return root
    current: SemanticNode | None = root
    for part in path.removeprefix("semantic_ir.").split("."):
        if current is None:
            return None
        if part.startswith("children["):
            index = int(part.removeprefix("children[").removesuffix("]"))
            current = current.children[index] if index < len(current.children) else None
        elif part.startswith("scope["):
            index = int(part.removeprefix("scope[").removesuffix("]"))
            current = current.scope[index] if index < len(current.scope) else None
        elif part in {"premise", "obligation", "action", "must"}:
            current = getattr(current, part)
        else:
            return current
    return current


def structural_signature_json(candidate: TranslationCandidate) -> str:
    return canonical_json(_node_signature(candidate.requirement.semantic_ir))
