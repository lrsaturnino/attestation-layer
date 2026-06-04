"""PA-6 audit client — second-model rubric for LLM decomposition results.

Every LLM-produced decomposition is audited by an independent model before its
verdict can be treated as a gate-level authority.  The rubric asks two questions:
  1. Does the decomposed IR cover every clause in the approved controlled text?
  2. Does the IR add any premise or obligation that is not in the controlled text?

An invented-premise finding causes the verdict to fail; missing clause coverage
causes failure.  Only a passing audit unlocks is_audited=True in DecompositionResult.

The LLM is an auditor, not a prover — it can flag invented/missing content that
a deterministic check would miss, but its verdict is not a formal proof.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.types import StrictBool

from .jsonutil import sha256_text


_DEFAULT_AUDIT_MODEL = "claude-haiku-4-5-20251001"

# Bump this when the semantic content of the audit prompt changes.
_AUDIT_PROMPT_VERSION = "0.1"

_AUDIT_PROMPT_TEMPLATE = (
    "You are a rigorous requirements auditor. "
    "You will receive an APPROVED CONTROLLED TEXT (the authoritative DSL v3 requirement) "
    "and a DECOMPOSED IR SUMMARY (a structured representation produced by an independent model).\n\n"
    "Answer ONLY with a JSON object in exactly this schema — no markdown, no commentary:\n"
    '{{"covers_all_clauses": true|false, "invented_premises": ["...", ...], "verdict": "passed"|"failed"}}\n\n'
    "Rules:\n"
    "- covers_all_clauses: true if every clause, condition, and obligation in the controlled text "
    "appears in the IR. false if any clause is missing or weakened.\n"
    "- invented_premises: list every IR premise, condition, or obligation that is NOT in the "
    "controlled text. Empty list [] if none.\n"
    "- verdict: 'passed' if covers_all_clauses is true AND invented_premises is empty. "
    "'failed' otherwise.\n\n"
    "APPROVED CONTROLLED TEXT:\n{controlled_text}\n\n"
    "DECOMPOSED IR SUMMARY:\n{ir_summary}"
)


class AuditVerdict(BaseModel):
    """Structured verdict from a PA-6 audit of a decomposition result.

    Fields:
      covers_all_clauses: True if every clause in the controlled text is present in the IR.
      invented_premises: List of IR premises or obligations not in the controlled text.
      verdict: "passed" only when covers_all_clauses is True and invented_premises is empty.
      audit_prompt_version: Version of the audit prompt used.
      model_id: Model that produced the verdict (None for recorded fixtures).
    """

    model_config = ConfigDict(extra="forbid")

    covers_all_clauses: StrictBool
    invented_premises: list[str] = Field(default_factory=list)
    verdict: Literal["passed", "failed"]
    audit_prompt_version: str = _AUDIT_PROMPT_VERSION
    model_id: str | None = None

    @model_validator(mode="after")
    def _normalize_verdict_from_fields(self) -> "AuditVerdict":
        # Derive verdict from structural fields so the stored value always matches the gate.
        # The model's verdict string is advisory — we never trust it over the field values.
        self.verdict = "passed" if (self.covers_all_clauses and not self.invented_premises) else "failed"
        return self


@runtime_checkable
class AuditClient(Protocol):
    """Synchronous interface for auditing an LLM decomposition result.

    The audit checks whether the decomposed IR:
      (1) covers every clause in the approved controlled text, and
      (2) does not add invented premises absent from the controlled text.

    Implementations:
    - RecordedAuditClient — replays a fixture verdict (offline/golden tests).
    - AnthropicAuditClient — second-model audit via live SDK call.
    """

    def audit_decomposition(
        self,
        controlled_text: str,
        ir_summary: str,
    ) -> AuditVerdict:
        """Return an AuditVerdict for the given controlled text and IR summary.

        Args:
            controlled_text: The approved DSL v3 controlled text (authoritative).
            ir_summary: A text summary of the decomposed IR for comparison.

        Returns:
            AuditVerdict with covers_all_clauses, invented_premises, and verdict.
        """
        ...


class RecordedAuditClient:
    """Replays a pre-recorded fixture verdict; never contacts a real model.

    Use for offline/golden tests and CI.

    Without hash constraints, the fixture verdict is returned verbatim regardless
    of the controlled_text or ir_summary inputs (suitable for truly generic tests).

    When expected_controlled_text_hash or expected_ir_summary_hash is supplied,
    the corresponding input is hashed and compared against the expected value.  A
    mismatch returns a conservative failed verdict so a passing fixture cannot be
    replayed against a different decomposition and bless it.

    The ir_summary hash should be computed from the exact output of
    summarize_ir_for_audit(requirement) — that is the string apply_audit passes.
    """

    def __init__(
        self,
        fixture: AuditVerdict,
        *,
        expected_controlled_text_hash: str | None = None,
        expected_ir_summary_hash: str | None = None,
    ) -> None:
        self._fixture = fixture
        self._expected_controlled_text_hash = expected_controlled_text_hash
        self._expected_ir_summary_hash = expected_ir_summary_hash

    def audit_decomposition(
        self,
        controlled_text: str,
        ir_summary: str,
    ) -> AuditVerdict:
        if self._expected_controlled_text_hash is not None:
            actual = sha256_text(controlled_text)
            if actual != self._expected_controlled_text_hash:
                return AuditVerdict(
                    covers_all_clauses=False,
                    invented_premises=[
                        f"[audit-fixture-mismatch: controlled_text hash {actual!r} "
                        f"does not match expected {self._expected_controlled_text_hash!r}]"
                    ],
                    verdict="failed",
                )
        if self._expected_ir_summary_hash is not None:
            actual = sha256_text(ir_summary)
            if actual != self._expected_ir_summary_hash:
                return AuditVerdict(
                    covers_all_clauses=False,
                    invented_premises=[
                        f"[audit-fixture-mismatch: ir_summary hash {actual!r} "
                        f"does not match expected {self._expected_ir_summary_hash!r}]"
                    ],
                    verdict="failed",
                )
        return self._fixture


class RecordedAuditFixture(BaseModel):
    """Hash-bound on-disk fixture for replaying a recorded audit verdict.

    Wraps an AuditVerdict together with the content hashes of the exact inputs it
    was produced for.  The CLI ``--audit-client recorded:<path>`` consumes this
    shape (never a bare AuditVerdict) so a passing verdict cannot be replayed
    against a different controlled text — and, when bound, a different IR summary —
    and bless a decomposition it never audited.

    expected_controlled_text_hash is required: it binds the verdict to one approved
    requirement.  expected_ir_summary_hash is optional: when set it further binds
    the verdict to a single decomposition's IR summary, i.e. the sha256 of
    summarize_ir_for_audit(requirement).  It is left optional because a single
    audit fixture supplied to a multi-candidate ensemble must still apply across
    candidates that share the same approved controlled text.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: AuditVerdict
    expected_controlled_text_hash: str
    expected_ir_summary_hash: str | None = None

    def build_client(self) -> RecordedAuditClient:
        """Return a RecordedAuditClient bound to this fixture's input hashes."""
        return RecordedAuditClient(
            fixture=self.verdict,
            expected_controlled_text_hash=self.expected_controlled_text_hash,
            expected_ir_summary_hash=self.expected_ir_summary_hash,
        )


class AnthropicAuditClient:
    """Live second-model Anthropic SDK client for decomposition auditing.

    Mirrors AnthropicDecompositionClient: SDK import is lazy, credentials via
    load_api_key(), temperature=0 for best-effort reproducibility.

    The model receives the controlled text and IR summary and returns a JSON
    verdict.  If parsing fails, the verdict is a conservative failure so an
    unreadable response does not silently pass as an audit.
    """

    def __init__(self, model: str = _DEFAULT_AUDIT_MODEL) -> None:
        self._model = model

    def audit_decomposition(
        self,
        controlled_text: str,
        ir_summary: str,
    ) -> AuditVerdict:
        from .llm_client import load_api_key
        import json

        api_key = load_api_key()

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Live audit requires the 'anthropic' package. "
                "Install it via: pip install anthropic  (or uv add anthropic)"
            ) from exc

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _AUDIT_PROMPT_TEMPLATE.format(
            controlled_text=controlled_text.strip(),
            ir_summary=ir_summary.strip(),
        )
        message = client.messages.create(
            model=self._model,
            max_tokens=512,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        try:
            data = json.loads(raw)
            # Do NOT coerce covers_all_clauses with bool() before passing to Pydantic.
            # StrictBool rejects non-bool values (e.g. the string "false") and raises
            # ValidationError, caught below as a conservative failure.  list[str] already
            # rejects non-list invented_premises without a coercion wrapper.
            return AuditVerdict(
                covers_all_clauses=data["covers_all_clauses"],
                invented_premises=list(data.get("invented_premises", [])),
                verdict=str(data["verdict"]),
                model_id=self._model,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError):
            # Conservative failure: an unreadable or schema-invalid verdict does not pass.
            return AuditVerdict(
                covers_all_clauses=False,
                invented_premises=[
                    "[audit-parse-error: model response was not valid JSON or failed schema validation]"
                ],
                verdict="failed",
                model_id=self._model,
            )


def summarize_ir_for_audit(requirement: object) -> str:
    """Produce a plain-text summary of a RequirementIRV2 for the audit rubric input.

    Returns a compact readable description of the requirement's claim class,
    premise, and obligation.  The model receives this rather than raw JSON to
    avoid leaking schema internals into the rubric prompt.
    """
    try:
        semantic = getattr(requirement, "semantic_ir", None)
        req_id = getattr(requirement, "requirement_id", "unknown")
        title = getattr(requirement, "title", "")
        claim_class = getattr(semantic, "claim_class", "unknown") if semantic else "unknown"
        premise = getattr(semantic, "premise", None) if semantic else None
        obligation = getattr(semantic, "obligation", None) if semantic else None

        parts = [f"requirement_id: {req_id}", f"title: {title}", f"claim_class: {claim_class}"]
        if premise is not None:
            parts.append(f"premise: {premise}")
        if obligation is not None:
            parts.append(f"obligation: {obligation}")
        return "\n".join(parts)
    except Exception:
        return str(requirement)


def apply_audit(
    result: object,
    audit_client: AuditClient,
    controlled_text: str,
) -> object:
    """Apply an audit gate to a DecompositionResult and return an updated copy.

    Builds an IR summary from result.requirement, calls audit_client.audit_decomposition,
    and returns a new DecompositionResult with:
      - audit_verdict set to the returned AuditVerdict
      - is_audited set to True ONLY when verdict == "passed"

    The original result is never mutated.  This is the PA-6 gate function — the only
    code path that may set is_audited=True on an LLM-produced DecompositionResult.
    A failing verdict (invented premises, missing clauses) leaves is_audited=False
    so the ensemble treats the candidate as needs_review rather than trusted.

    Args:
        result: A DecompositionResult produced by a DecompositionClient.
        audit_client: The audit client (RecordedAuditClient for tests,
                      AnthropicAuditClient for live runs).
        controlled_text: The approved DSL v3 controlled text (authoritative).

    Returns:
        An updated DecompositionResult with audit_verdict and is_audited set.
    """
    requirement = getattr(result, "requirement", None)
    ir_summary = summarize_ir_for_audit(requirement) if requirement is not None else ""
    verdict = audit_client.audit_decomposition(
        controlled_text=controlled_text,
        ir_summary=ir_summary,
    )
    # Derive gate from structural fields directly — treat verdict string as advisory.
    # The model_validator already coerced inconsistent verdicts, but we gate on fields
    # rather than trusting the string to be consistent with what the validator saw.
    passed = verdict.covers_all_clauses and not verdict.invented_premises
    return result.model_copy(update={"audit_verdict": verdict, "is_audited": passed})
