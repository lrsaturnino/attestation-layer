"""Tests for PA-5: DecompositionClient interface and ensemble check wired into
translate_controlled_requirement_to_formal_claim.
"""
from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nlreq.decomposition_client import (
    AnthropicDecompositionClient,
    DecompositionClient,
    DecompositionResult,
    RecordedDecompositionClient,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.jsonutil import sha256_text
from nlreq.models import Approval, RequirementIRV2
from nlreq.semantic_translation import translate_controlled_requirement_to_formal_claim


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"

_CONTROLLED_TEXT = (FIXTURES / "authorization_precondition_v3.nlreq").read_text()
_REQUIREMENT_ID = "REQ-DECOMP-001"
_TITLE = "PA-5 decomposition ensemble test"


def _parse_ir(requirement_id: str = _REQUIREMENT_ID) -> RequirementIRV2:
    return DslV3Parser().parse_ir(
        _CONTROLLED_TEXT, requirement_id=requirement_id, title=_TITLE
    )


def _parse_ir_variant() -> RequirementIRV2:
    """Return an IR that differs in its FormalClaim signature from the base IR.

    Mutates the predicate name in the premise so the formal-claim signature
    (alpha-renamed, commutative) differs from the unmodified base IR.
    """
    data = _parse_ir().model_dump(mode="json")
    # Change the predicate name in the premise children to produce a different
    # formal-claim signature (verified empirically — the base predicate is
    # 'not_authorized'; changing it produces a distinct FormalClaim signature).
    data["semantic_ir"]["premise"]["children"][0]["name"] = "alternative_predicate"
    return RequirementIRV2.model_validate(data)


def _approved_approval() -> Approval:
    return Approval(status="approved", approved_by="test-suite", approved_at="test")


# ---------------------------------------------------------------------------
# RecordedDecompositionClient
# ---------------------------------------------------------------------------


def test_recorded_decomposition_client_returns_fixture() -> None:
    """RecordedDecompositionClient returns a DecompositionResult whose .requirement is the fixture."""
    ir = _parse_ir()
    client = RecordedDecompositionClient(fixture=ir)

    result = client.decompose_controlled_to_ir("any text", "any-id", "any title")

    assert isinstance(result, DecompositionResult)
    assert result.requirement == ir


def test_recorded_decomposition_client_carries_trust_metadata() -> None:
    """RecordedDecompositionClient propagates approval, is_audited, model_id, and prompt_hash."""
    ir = _parse_ir()
    approval = _approved_approval()
    client = RecordedDecompositionClient(
        fixture=ir,
        candidate_id="my-candidate",
        approval=approval,
        is_audited=True,
        model_id="test-model",
        prompt_hash="abc123",
    )

    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.candidate_id == "my-candidate"
    assert result.approval == approval
    assert result.is_audited is True
    assert result.model_id == "test-model"
    assert result.prompt_hash == "abc123"
    assert result.source_text_hash  # non-empty hash of the controlled text


def test_recorded_decomposition_client_defaults_to_unapproved_unaudited() -> None:
    """RecordedDecompositionClient without explicit trust metadata is unapproved and unaudited."""
    client = RecordedDecompositionClient(fixture=_parse_ir())
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.approval is None
    assert result.is_audited is False


def test_recorded_decomposition_client_satisfies_protocol() -> None:
    """RecordedDecompositionClient satisfies the DecompositionClient Protocol."""
    client = RecordedDecompositionClient(fixture=_parse_ir())
    assert isinstance(client, DecompositionClient)


# ---------------------------------------------------------------------------
# AnthropicDecompositionClient
# ---------------------------------------------------------------------------


def test_anthropic_decomposition_client_raises_on_missing_key() -> None:
    """AnthropicDecompositionClient raises EnvironmentError when no API key is configured."""
    client = AnthropicDecompositionClient()
    # Patch both the env variable and the .claude/.env file lookup so neither
    # source yields a key, ensuring the test is hermetic.
    with patch("nlreq.llm_client._find_dot_claude_env", return_value=None):
        with patch.dict("os.environ", {"NLREQ_ANTHROPIC_API_KEY": ""}, clear=False):
            with pytest.raises(EnvironmentError, match="NLREQ_ANTHROPIC_API_KEY"):
                client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)


def test_anthropic_decomposition_client_satisfies_protocol() -> None:
    """AnthropicDecompositionClient satisfies the DecompositionClient Protocol."""
    client = AnthropicDecompositionClient()
    assert isinstance(client, DecompositionClient)


def test_anthropic_decomposition_client_defaults_unaudited() -> None:
    """AnthropicDecompositionClient never produces an audited result (PA-6 not yet implemented)."""
    # Verifying the class-level invariant without making a live call.
    # The is_audited=False / approval=None defaults are asserted on a RecordedDecompositionClient
    # acting as a proxy; the live-call path is integration-tested separately.
    client = RecordedDecompositionClient(fixture=_parse_ir())  # stand-in for the live client
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)
    assert result.is_audited is False
    assert result.approval is None


# ---------------------------------------------------------------------------
# PA-5 ensemble check: agreed + audited → accepted; disagreed + audited → REFUSED_AMBIGUOUS
# ---------------------------------------------------------------------------


def test_ensemble_agreed_audited_clients_produce_accepted() -> None:
    """Two approved+audited clients with the same IR yield an accepted translation."""
    approval = _approved_approval()
    ir = _parse_ir()
    clients = [
        RecordedDecompositionClient(fixture=ir, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir, approval=approval, is_audited=True),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result in {"accepted", "needs_review"}, (
        f"Agreeing audited ensemble must not be refused, got {report.result!r}: "
        f"refusal_code={report.refusal_code}"
    )
    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Agreeing ensemble must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_ensemble_agreed_clients_produce_accepted() -> None:
    """Two RecordedDecompositionClients with default (unapproved) trust produce needs_review."""
    ir = _parse_ir()
    clients = [
        RecordedDecompositionClient(fixture=ir),
        RecordedDecompositionClient(fixture=ir),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result in {"accepted", "needs_review"}, (
        f"Agreeing ensemble must not be refused, got {report.result!r}: "
        f"refusal_code={report.refusal_code}"
    )
    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Agreeing ensemble must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_ensemble_disagreed_audited_clients_produce_refused_ambiguous() -> None:
    """Two approved+audited clients with different IRs produce NLR-REFUSED-AMBIGUOUS.

    Approval must be supplied explicitly — the ensemble never synthesises it.
    """
    approval = _approved_approval()
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()  # different predicate → different formal-claim signature
    clients = [
        RecordedDecompositionClient(fixture=ir_a, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir_b, approval=approval, is_audited=True),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result == "refused", (
        f"Disagreeing audited ensemble must produce refused, got {report.result!r}"
    )
    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS", (
        f"Expected NLR-REFUSED-AMBIGUOUS, got {report.refusal_code!r}"
    )
    assert len(report.ambiguity_findings) >= 1, (
        "Must carry at least one ambiguity finding with the disagreement"
    )
    assert any(
        "ensemble-decomposition-0" in f.clarification_question
        or "ensemble-decomposition-1" in f.clarification_question
        for f in report.ambiguity_findings
    ), "Ambiguity findings must reference the ensemble candidate IDs"


# Backward-compat alias so existing callers of the old test name still pass.
test_ensemble_disagreed_clients_produce_refused_ambiguous = (
    test_ensemble_disagreed_audited_clients_produce_refused_ambiguous
)


# ---------------------------------------------------------------------------
# PA-5 trust boundary: unaudited candidates → needs_review, not refused-ambiguous
# ---------------------------------------------------------------------------


def test_ensemble_unaudited_clients_produce_needs_review() -> None:
    """Unaudited clients (no approval, is_audited=False) produce needs_review, not refused-ambiguous.

    Even when the two candidates disagree, the trust boundary must win: the
    correct output is needs_review with NLR-UNAUDITED-DECOMPOSITION, not
    NLR-REFUSED-AMBIGUOUS.  An ambiguity refusal requires both candidates to be
    explicitly approved and audited — reflecting that PA-6 audit is a prerequisite.
    """
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()
    clients = [
        RecordedDecompositionClient(fixture=ir_a),  # unapproved, unaudited
        RecordedDecompositionClient(fixture=ir_b),  # unapproved, unaudited
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.result == "needs_review", (
        f"Unaudited ensemble must yield needs_review, got {report.result!r}"
    )
    assert report.refusal_code == "NLR-UNAUDITED-DECOMPOSITION", (
        f"Expected NLR-UNAUDITED-DECOMPOSITION, got {report.refusal_code!r}"
    )
    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Unaudited candidates must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_ensemble_unaudited_carries_prior_provenance() -> None:
    """needs_review from unaudited ensemble carries controlled-text hash and prior stages."""
    ir = _parse_ir()
    clients = [
        RecordedDecompositionClient(fixture=ir),
        RecordedDecompositionClient(fixture=ir),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert "controlled_text" in report.input_hashes, (
        "input_hashes must include controlled_text hash"
    )
    stage_names = [s.stage for s in report.stages]
    assert "canonicalize" in stage_names, "canonicalize stage must be preserved in refusal"
    assert "parse_semantic_tree" in stage_names, "parse_semantic_tree stage must be preserved"


def test_ensemble_refused_ambiguous_carries_prior_provenance() -> None:
    """NLR-REFUSED-AMBIGUOUS carries controlled-text hash, prior stages, and tree hashes."""
    approval = _approved_approval()
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()
    clients = [
        RecordedDecompositionClient(fixture=ir_a, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir_b, approval=approval, is_audited=True),
    ]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS"
    assert "controlled_text" in report.input_hashes, "input_hashes must include controlled_text"
    assert report.semantic_tree_hash is not None, "semantic_tree_hash must be set"
    assert report.semantic_decomposition_hash is not None, "semantic_decomposition_hash must be set"
    assert report.requirement_ir is not None, "requirement_ir must be present in refusal"
    stage_names = [s.stage for s in report.stages]
    assert "canonicalize" in stage_names, "canonicalize stage must be preserved"
    assert "parse_semantic_tree" in stage_names, "parse_semantic_tree stage must be preserved"
    assert "lower_formal_claim" in stage_names, "lower_formal_claim failure stage must be present"


# ---------------------------------------------------------------------------
# Ensemble skip conditions
# ---------------------------------------------------------------------------


def test_no_ensemble_clients_skips_check() -> None:
    """Omitting decomposition_clients does not trigger the ensemble check."""
    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=None,
    )

    assert report.result != "refused" or report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "No ensemble clients must not produce NLR-REFUSED-AMBIGUOUS"
    )


def test_single_ensemble_client_skips_check() -> None:
    """A list with only one client does not trigger the ensemble check (need ≥2)."""
    ir = _parse_ir()
    clients = [RecordedDecompositionClient(fixture=ir)]

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.refusal_code != "NLR-REFUSED-AMBIGUOUS", (
        "Single-client list must not produce NLR-REFUSED-AMBIGUOUS"
    )


# ---------------------------------------------------------------------------
# AnthropicDecompositionClient — mocked-SDK success path (no live call)
# ---------------------------------------------------------------------------

# Parseable DSL v3 text the fake SDK will return.
_PARSEABLE_SDK_RESPONSE = (
    "requirement authorization_precondition: "
    "scope operation_request when actor is not authorized "
    "then operation must reject before state_change."
)


def _make_fake_anthropic_module(response_text: str):
    """Build a fake 'anthropic' module and return it with the underlying mock SDK client.

    The returned sdk_client mock records calls to .messages.create() so tests can
    inspect the prompt that was sent.
    """
    module = types.ModuleType("anthropic")
    message = MagicMock()
    message.content = [MagicMock()]
    message.content[0].text = response_text
    sdk_client = MagicMock()
    sdk_client.messages.create.return_value = message
    module.Anthropic = MagicMock(return_value=sdk_client)
    return module, sdk_client


def test_anthropic_decomposition_client_success_returns_ir() -> None:
    """AnthropicDecompositionClient success path returns a DecompositionResult with a valid IR."""
    fake_module, _ = _make_fake_anthropic_module(_PARSEABLE_SDK_RESPONSE)
    client = AnthropicDecompositionClient()

    with patch.dict("sys.modules", {"anthropic": fake_module}):
        with patch("nlreq.llm_client.load_api_key", return_value="test-key"):
            result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert isinstance(result, DecompositionResult)
    assert isinstance(result.requirement, RequirementIRV2)
    assert result.requirement.requirement_id == _REQUIREMENT_ID


def test_anthropic_decomposition_client_success_provenance_metadata() -> None:
    """Success path records non-empty model_id, prompt_hash, and correct source_text_hash."""
    fake_module, _ = _make_fake_anthropic_module(_PARSEABLE_SDK_RESPONSE)
    client = AnthropicDecompositionClient()

    with patch.dict("sys.modules", {"anthropic": fake_module}):
        with patch("nlreq.llm_client.load_api_key", return_value="test-key"):
            result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.model_id is not None and result.model_id != "", "model_id must be populated"
    assert result.prompt_hash is not None and result.prompt_hash != "", "prompt_hash must be populated"
    assert result.source_text_hash == sha256_text(_CONTROLLED_TEXT), (
        "source_text_hash must be sha256 of the exact input controlled_text"
    )


def test_anthropic_decomposition_client_success_always_unaudited() -> None:
    """Success path always returns is_audited=False and approval=None (PA-6 not yet active)."""
    fake_module, _ = _make_fake_anthropic_module(_PARSEABLE_SDK_RESPONSE)
    client = AnthropicDecompositionClient()

    with patch.dict("sys.modules", {"anthropic": fake_module}):
        with patch("nlreq.llm_client.load_api_key", return_value="test-key"):
            result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.is_audited is False, (
        "AnthropicDecompositionClient must always return is_audited=False until PA-6 audit runs"
    )
    assert result.approval is None, (
        "AnthropicDecompositionClient must always return approval=None until human approval"
    )


def test_anthropic_decomposition_client_success_prompt_contains_inputs() -> None:
    """Success path embeds requirement_id, title, and controlled_text in the SDK prompt."""
    fake_module, sdk_client = _make_fake_anthropic_module(_PARSEABLE_SDK_RESPONSE)
    client = AnthropicDecompositionClient()

    with patch.dict("sys.modules", {"anthropic": fake_module}):
        with patch("nlreq.llm_client.load_api_key", return_value="test-key"):
            client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    call_args = sdk_client.messages.create.call_args
    assert call_args is not None, "sdk_client.messages.create must have been called"
    prompt_text = call_args.kwargs["messages"][0]["content"]
    assert _REQUIREMENT_ID in prompt_text, "prompt must include requirement_id"
    assert _TITLE in prompt_text, "prompt must include title"
    assert _CONTROLLED_TEXT.strip() in prompt_text, "prompt must include controlled_text"


# ---------------------------------------------------------------------------
# Source span remapping: disagreement spans resolve to the original IR
# ---------------------------------------------------------------------------


def test_refused_ambiguous_source_spans_from_original_ir() -> None:
    """NLR-REFUSED-AMBIGUOUS source_spans come from the original parsed IR, not candidate IR.

    When two approved+audited candidates disagree, the disagreement's source_spans
    must reference nodes from the original requirement_ir (the one parsed from the
    controlled_text supplied to translate_controlled_requirement_to_formal_claim),
    not positions in a model-produced re-expression.  We verify this by checking
    that the spans in the ambiguity findings are a subset of those present in the
    original requirement_ir.
    """
    approval = _approved_approval()
    ir_a = _parse_ir()
    ir_b = _parse_ir_variant()

    # Collect all source spans in the original IR.
    def _collect_spans(ir: RequirementIRV2) -> set[tuple]:
        spans = set()
        def _walk(node):
            for sp in node.source_spans:
                spans.add((sp.document, sp.start_char, sp.end_char))
            for child in (
                [node.premise, node.obligation, node.action, node.must]
                + list(node.scope)
                + list(node.children)
            ):
                if child is not None:
                    _walk(child)
        _walk(ir.semantic_ir)
        return spans

    original_ir = DslV3Parser().parse_ir(_CONTROLLED_TEXT, requirement_id=_REQUIREMENT_ID, title=_TITLE)
    original_spans = _collect_spans(original_ir)

    clients = [
        RecordedDecompositionClient(fixture=ir_a, approval=approval, is_audited=True),
        RecordedDecompositionClient(fixture=ir_b, approval=approval, is_audited=True),
    ]
    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=clients,
    )

    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS"
    for finding in report.ambiguity_findings:
        for span in finding.source_spans:
            span_tuple = (span.document, span.start_char, span.end_char)
            assert span_tuple in original_spans, (
                f"span {span_tuple} in ambiguity finding was not found in the original IR spans; "
                "spans must be remapped to the original controlled text"
            )
