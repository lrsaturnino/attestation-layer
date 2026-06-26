from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from .audit_client import AuditVerdict
from .jsonutil import sha256_text
from .models import Approval, RequirementIRV2, SourceSpan


# Model used for decomposition. temperature=0 is sent for best-effort
# reproducibility only; callers must still treat output as untrusted
# and never approved/audited.
_DEFAULT_DECOMPOSITION_MODEL = "claude-haiku-4-5-20251001"

# Bump this string whenever the semantic content of the prompt changes so
# that prompt_hash values in archived DecompositionResult objects remain
# interpretable against a specific prompt version.
_DECOMPOSITION_PROMPT_VERSION = "0.1"

_DECOMPOSITION_PROMPT_TEMPLATE = (
    "You are a precise formal-requirements analyst. "
    "You will receive a requirement written in DSL v3 controlled language. "
    "Your task: independently re-express it as a valid DSL v3 requirement, "
    "capturing every stated obligation and predicate without adding or removing semantics.\n\n"
    "Output ONLY the DSL v3 controlled text — no explanation, no commentary.\n\n"
    "REQUIREMENT ID: {requirement_id}\n"
    "TITLE: {title}\n\n"
    "CONTROLLED TEXT:\n{controlled_text}"
)


class DecompositionResult(BaseModel):
    """Rich result from a decomposition client, carrying provenance and trust metadata.

    Trust boundary: is_audited is False until a PA-6 audit explicitly sets it.
    An ensemble check treats any unaudited or unapproved candidate as needs_review,
    not as a semantic finding.  Only approved+audited results proceed to the
    FormalClaim-signature comparison that can trigger REFUSED_AMBIGUOUS.
    """

    model_config = ConfigDict(extra="forbid")

    requirement: RequirementIRV2
    candidate_id: str
    source_text_hash: str
    model_id: str | None = None
    prompt_hash: str | None = None
    source_spans: list[SourceSpan] = Field(default_factory=list)
    approval: Approval | None = None
    is_audited: bool = False
    audit_verdict: AuditVerdict | None = None
    provenance: dict[str, str] = Field(default_factory=dict)


@runtime_checkable
class DecompositionClient(Protocol):
    """Synchronous interface for decomposing controlled DSL v3 text into a DecompositionResult.

    Used by the PA-5 ensemble: two independent clients receive the same approved
    controlled text and each returns its interpretation as a DecompositionResult.
    The caller compares FormalClaim signatures; divergence triggers REFUSED_AMBIGUOUS
    only when all candidates are approved and audited.

    Implementations:
    - RecordedDecompositionClient — replays a fixture IR with caller-supplied trust
      metadata (offline / golden tests; explicit approval enables the ambiguity path).
    - AnthropicDecompositionClient — live SDK call; always unaudited/unapproved until PA-6.

    The returned IR is UNTRUSTED from a semantic standpoint: the ensemble check
    determines whether it agrees with other independent decompositions.
    """

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ) -> DecompositionResult:
        """Return a DecompositionResult for the given controlled DSL v3 text.

        Args:
            controlled_text: Approved DSL v3 controlled text.
            requirement_id: Requirement identifier to embed in the returned IR.
            title: Human-readable title to embed in the returned IR.

        Returns:
            A DecompositionResult carrying the IR and its trust / provenance metadata.
        """
        ...


class RecordedDecompositionClient:
    """Replays a pre-recorded fixture IR; never contacts a real model.

    Use for offline/golden tests and CI.  The fixture IR is returned verbatim
    regardless of the controlled_text — golden tests pin the decomposition result,
    not the input routing.

    Callers supply explicit trust metadata at construction time.  To exercise the
    refused-ambiguous path in tests, pass approval=Approval(status="approved", …),
    is_audited=True, and a passing audit_verdict — the ensemble trust check requires
    a present, structurally passing verdict as evidence, not just the is_audited flag.
    To exercise the needs-review / untrusted path, leave them at their defaults
    (None / False / None).

    Pass expected_source_text_hash (typically fixture_result.source_text_hash from the
    saved fixture) to bind the replay to the original input.  When set, replaying against
    a different controlled_text raises ValueError — this prevents a stale or wrong-input
    fixture from being silently accepted and appearing hash-bound to new text.
    """

    def __init__(
        self,
        fixture: RequirementIRV2,
        *,
        candidate_id: str = "recorded",
        approval: Approval | None = None,
        is_audited: bool = False,
        audit_verdict: AuditVerdict | None = None,
        model_id: str | None = None,
        prompt_hash: str | None = None,
        fixture_provenance: dict[str, str] | None = None,
        source_spans: list[SourceSpan] | None = None,
        expected_source_text_hash: str | None = None,
    ) -> None:
        self._fixture = fixture
        self._candidate_id = candidate_id
        self._approval = approval
        self._is_audited = is_audited
        self._audit_verdict = audit_verdict
        self._model_id = model_id
        self._prompt_hash = prompt_hash
        self._fixture_provenance: dict[str, str] = fixture_provenance or {}
        self._source_spans: list[SourceSpan] = source_spans or []
        self._expected_source_text_hash = expected_source_text_hash

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ) -> DecompositionResult:
        actual_hash = sha256_text(controlled_text)
        if (
            self._expected_source_text_hash is not None
            and actual_hash != self._expected_source_text_hash
        ):
            raise ValueError(
                f"RecordedDecompositionClient: controlled_text hash {actual_hash!r} "
                f"does not match fixture's expected hash {self._expected_source_text_hash!r}. "
                "Replaying a fixture against different input text would produce a result "
                "that appears hash-bound to new text but carries the old IR."
            )
        return DecompositionResult(
            requirement=self._fixture,
            candidate_id=self._candidate_id,
            source_text_hash=actual_hash,
            model_id=self._model_id,
            prompt_hash=self._prompt_hash,
            source_spans=self._source_spans,
            approval=self._approval,
            is_audited=self._is_audited,
            audit_verdict=self._audit_verdict,
            # Use "replay_marker" to avoid colliding with a "source" key that may
            # already exist in fixture_provenance (e.g. {"source": "test_fixture"}).
            provenance={"replay_marker": "recorded_fixture", **self._fixture_provenance},
        )


class AnthropicDecompositionClient:
    """Live Anthropic SDK client for independent LLM-based IR decomposition.

    Mirrors AnthropicLlmClient: SDK import is lazy (no import-time failure),
    credentials loaded via load_api_key() (never hardcoded), temperature=0 for
    best-effort reproducibility.

    The LLM independently re-expresses the controlled text as DSL v3; DslV3Parser
    then produces the IR deterministically from that output.  If the LLM interprets
    the requirement differently it produces different DSL v3 → different FormalClaim
    signature → ensemble disagreement detected.

    Results are always unaudited (is_audited=False, approval=None) until PA-6
    implements the second-model audit.  An ensemble using this client returns
    needs_review, not refused-ambiguous, until audit is available.
    """

    def __init__(
        self,
        model: str = _DEFAULT_DECOMPOSITION_MODEL,
        *,
        client_kind: str | None = None,
    ) -> None:
        # client_kind is the per-role transport provenance (Work Item 1): it is emitted
        # into the DecompositionResult provenance dict ONLY when set, so the default
        # path (client_kind=None, no model-config) stays byte-identical to the pre-config
        # CLI. The model-config factory passes the resolved client_kind on non-default
        # rungs; direct callers leave it None.
        self._model = model
        self._client_kind = client_kind

    def decompose_controlled_to_ir(
        self,
        controlled_text: str,
        requirement_id: str,
        title: str,
    ) -> DecompositionResult:
        from .llm_client import load_api_key

        api_key = load_api_key()

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Live LLM decomposition requires the 'anthropic' package. "
                "Install it via: pip install anthropic (or uv add anthropic)"
            ) from exc

        prompt = _DECOMPOSITION_PROMPT_TEMPLATE.format(
            controlled_text=controlled_text,
            requirement_id=requirement_id,
            title=title,
        )
        prompt_hash = sha256_text(prompt)
        source_text_hash = sha256_text(controlled_text)

        sdk_client = anthropic.Anthropic(api_key=api_key)
        message = sdk_client.messages.create(
            model=self._model,
            max_tokens=2048,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        proposed_text: str = message.content[0].text

        from .dsl_v3 import DslV3Parser

        requirement = DslV3Parser().parse_ir(
            proposed_text.strip(),
            requirement_id=requirement_id,
            title=title,
        )

        return DecompositionResult(
            requirement=requirement,
            candidate_id=f"anthropic-{self._model}",
            source_text_hash=source_text_hash,
            model_id=self._model,
            prompt_hash=prompt_hash,
            approval=None,
            is_audited=False,
            provenance={
                "source": "anthropic_decomposition",
                "model": self._model,
                "prompt_version": _DECOMPOSITION_PROMPT_VERSION,
                **({"client_kind": self._client_kind} if self._client_kind else {}),
            },
        )
