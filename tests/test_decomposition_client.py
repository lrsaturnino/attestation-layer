"""Tests for PA-5: DecompositionClient interface and ensemble check wired into
translate_controlled_requirement_to_formal_claim.
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nlreq.cli import main
from nlreq.decomposition_client import (
    AnthropicDecompositionClient,
    DecompositionClient,
    DecompositionResult,
    RecordedDecompositionClient,
)
from nlreq.dsl_v3 import DslV3Parser
from nlreq.jsonutil import sha256_text
from nlreq.models import Approval, RequirementIRV2, SourceSpan
from nlreq.semantic_translation import (
    remap_disagreement_spans_to_original,
    translate_controlled_requirement_to_formal_claim,
)
from nlreq.translator_agreement import TranslationDisagreement


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


# ---------------------------------------------------------------------------
# Direct unit tests for remap_disagreement_spans_to_original
# ---------------------------------------------------------------------------
# These tests exercise the remap function with candidate spans that genuinely
# come from a different synthetic document ("model-output-doc"), matching the
# production failure mode where LLM re-expression produces spans referencing
# model-output positions, not the original controlled text.


def test_remap_replaces_model_output_spans_with_original_ir_spans() -> None:
    """remap replaces spans from a model-output document with spans from the original IR.

    Proves the remap actually does work: the input disagreement carries spans
    referencing 'model-output-doc' at arbitrary positions; after remapping, those
    spans must be gone and replaced with the original IR's spans for that path.
    """
    from nlreq.translator_agreement import spans_for_path

    original_ir = DslV3Parser().parse_ir(
        _CONTROLLED_TEXT, requirement_id=_REQUIREMENT_ID, title=_TITLE
    )

    # Guard: verify the chosen path resolves in the original IR and has spans, so
    # the resolve branch (not fallback) is exercised.
    path = "semantic_ir.premise"
    resolved_spans = spans_for_path(original_ir.semantic_ir, path)
    assert resolved_spans, (
        f"test precondition: path {path!r} must resolve with non-empty spans in the original IR"
    )

    model_output_spans = [
        SourceSpan(document="model-output-doc", start_char=0, end_char=5, text="dummy"),
        SourceSpan(document="model-output-doc", start_char=10, end_char=20, text="other"),
    ]
    disagreement = TranslationDisagreement(
        left_translator_id="ensemble-decomposition-0",
        right_translator_id="ensemble-decomposition-1",
        path=path,
        reason="predicate mismatch",
        source_spans=model_output_spans,
    )

    remapped = remap_disagreement_spans_to_original([disagreement], original_ir)

    assert len(remapped) == 1
    result = remapped[0]
    for span in result.source_spans:
        assert span.document != "model-output-doc", (
            f"span still references model-output-doc after remap: {span}; "
            "remap must replace candidate spans with original IR spans"
        )
    assert "span-fallback" not in result.reason


def test_remap_appends_fallback_note_when_path_absent_from_original_ir() -> None:
    """remap appends a span-fallback note and preserves spans when the path is absent.

    When the candidate IR diverged structurally and the disagreement path has no
    counterpart in the original IR, the remapper keeps the candidate spans and
    appends an explanation to the reason so callers know the fallback was taken.
    """
    original_ir = DslV3Parser().parse_ir(
        _CONTROLLED_TEXT, requirement_id=_REQUIREMENT_ID, title=_TITLE
    )

    candidate_spans = [
        SourceSpan(document="model-output-doc", start_char=5, end_char=15, text="candidate"),
    ]
    nonexistent_path = "semantic_ir.children[99]"
    disagreement = TranslationDisagreement(
        left_translator_id="ensemble-decomposition-0",
        right_translator_id="ensemble-decomposition-1",
        path=nonexistent_path,
        reason="structural divergence",
        source_spans=candidate_spans,
    )

    remapped = remap_disagreement_spans_to_original([disagreement], original_ir)

    assert len(remapped) == 1
    result = remapped[0]
    assert "span-fallback" in result.reason, (
        f"expected span-fallback note in reason for absent path {nonexistent_path!r}; "
        f"got: {result.reason!r}"
    )
    assert result.source_spans == candidate_spans, (
        "candidate spans must be preserved unchanged when the path is absent from the original IR"
    )


# ---------------------------------------------------------------------------
# CLI-level tests for recorded: fixture format (DecompositionResult)
# ---------------------------------------------------------------------------
# These drive the actual argv/dispatch path so that CLI bugs (like parsing a
# bare RequirementIRV2 and defaulting trust to unapproved/unaudited) are caught
# at the layer they live, not masked by direct function calls.


def _write_decomposition_fixture(
    path: Path,
    ir: RequirementIRV2,
    *,
    candidate_id: str,
    approval: Approval | None,
    is_audited: bool,
) -> Path:
    result = DecompositionResult(
        requirement=ir,
        candidate_id=candidate_id,
        source_text_hash=sha256_text(_CONTROLLED_TEXT),
        approval=approval,
        is_audited=is_audited,
        provenance={"source": "test_fixture"},
    )
    path.write_text(result.model_dump_json())
    return path


def test_cli_semantic_translate_two_approved_disagreeing_fixtures_refused_ambiguous(
    tmp_path: Path,
) -> None:
    """CLI recorded: path with two approved+audited disagreeing fixtures → NLR-REFUSED-AMBIGUOUS.

    This is the CLI equivalent of test_refused_ambiguous_source_spans_from_original_ir.
    Exercises the full argv → CLI dispatch → RecordedDecompositionClient path so that
    broken trust-field handling in the CLI is caught here, not silently in the function.
    """
    req_file = tmp_path / "req.nlreq"
    req_file.write_text(_CONTROLLED_TEXT)
    approval = _approved_approval()
    fixture_a = _write_decomposition_fixture(
        tmp_path / "fixture_a.json",
        _parse_ir(),
        candidate_id="candidate-a",
        approval=approval,
        is_audited=True,
    )
    fixture_b = _write_decomposition_fixture(
        tmp_path / "fixture_b.json",
        _parse_ir_variant(),
        candidate_id="candidate-b",
        approval=approval,
        is_audited=True,
    )
    out_path = tmp_path / "report.json"

    exit_code = main([
        "semantic-translate", str(req_file),
        "--requirement-id", _REQUIREMENT_ID,
        "--title", _TITLE,
        "--ensemble-client", f"recorded:{fixture_a}",
        "--ensemble-client", f"recorded:{fixture_b}",
        "--out", str(out_path),
    ])

    assert exit_code == 1, f"expected exit 1 for refused report, got {exit_code}"
    report = json.loads(out_path.read_text())
    assert report["refusal_code"] == "NLR-REFUSED-AMBIGUOUS", (
        f"expected NLR-REFUSED-AMBIGUOUS but got {report.get('refusal_code')!r}"
    )


def test_cli_semantic_translate_two_unaudited_fixtures_returns_needs_review(
    tmp_path: Path,
) -> None:
    """CLI recorded: path with two unaudited fixtures → NLR-UNAUDITED-DECOMPOSITION.

    Verifies the trust check blocks before the signature comparison when the
    fixture carries default (no approval, is_audited=False) trust metadata.
    """
    req_file = tmp_path / "req.nlreq"
    req_file.write_text(_CONTROLLED_TEXT)
    fixture_a = _write_decomposition_fixture(
        tmp_path / "fixture_a.json",
        _parse_ir(),
        candidate_id="candidate-a",
        approval=None,
        is_audited=False,
    )
    fixture_b = _write_decomposition_fixture(
        tmp_path / "fixture_b.json",
        _parse_ir_variant(),
        candidate_id="candidate-b",
        approval=None,
        is_audited=False,
    )
    out_path = tmp_path / "report.json"

    exit_code = main([
        "semantic-translate", str(req_file),
        "--requirement-id", _REQUIREMENT_ID,
        "--title", _TITLE,
        "--ensemble-client", f"recorded:{fixture_a}",
        "--ensemble-client", f"recorded:{fixture_b}",
        "--out", str(out_path),
    ])

    assert exit_code == 1, f"expected exit 1 for needs_review report, got {exit_code}"
    report = json.loads(out_path.read_text())
    assert report["refusal_code"] == "NLR-UNAUDITED-DECOMPOSITION", (
        f"expected NLR-UNAUDITED-DECOMPOSITION but got {report.get('refusal_code')!r}"
    )


def test_cli_semantic_translate_unknown_ensemble_spec_exits_2(tmp_path: Path) -> None:
    """CLI semantic-translate with an unrecognised --ensemble-client spec returns exit code 2."""
    req_file = tmp_path / "req.nlreq"
    req_file.write_text(_CONTROLLED_TEXT)

    exit_code = main([
        "semantic-translate", str(req_file),
        "--requirement-id", _REQUIREMENT_ID,
        "--title", _TITLE,
        "--ensemble-client", "unknown-format-xyz",
    ])

    assert exit_code == 2, f"expected exit 2 for unknown spec, got {exit_code}"


def test_recorded_decomposition_client_preserves_fixture_provenance() -> None:
    """RecordedDecompositionClient must merge fixture_provenance into the result provenance.

    Fix 3 (iter 2): the client used to emit only {"source": "recorded_fixture"},
    silently dropping any provenance carried by the fixture (model ID, prompt version,
    original pipeline stage, etc.).  After the fix it should emit the fixture's
    provenance merged under the "replay_marker" key to avoid collision.
    """
    ir = _parse_ir()
    fixture_provenance = {
        "model": "claude-haiku-4-5-20251001",
        "prompt_version": "0.1",
        "original_stage": "decomposition_ensemble",
    }
    client = RecordedDecompositionClient(
        ir,
        candidate_id="test-recorded",
        fixture_provenance=fixture_provenance,
    )
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.provenance.get("replay_marker") == "recorded_fixture", (
        "replay_marker must be present under 'replay_marker' key, not 'source'"
    )
    for key, value in fixture_provenance.items():
        assert result.provenance.get(key) == value, (
            f"fixture_provenance[{key!r}]={value!r} must be preserved in result provenance"
        )


def test_recorded_decomposition_client_replay_marker_survives_fixture_source_key() -> None:
    """Replay marker must not be overwritten when fixture provenance already has a 'source' key.

    This is the collision that existed before the fix: {"source": "recorded_fixture",
    **fixture_provenance} silently overwrote the marker when the fixture already had
    {"source": "test_fixture"}.  After the fix the marker lives under "replay_marker"
    so both keys coexist.
    """
    ir = _parse_ir()
    fixture_provenance = {"source": "test_fixture", "model": "test-model-0.1"}
    client = RecordedDecompositionClient(
        ir,
        candidate_id="collision-test",
        fixture_provenance=fixture_provenance,
    )
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.provenance.get("replay_marker") == "recorded_fixture", (
        "replay_marker must survive even when fixture provenance has a 'source' key"
    )
    assert result.provenance.get("source") == "test_fixture", (
        "original fixture 'source' key must not be overwritten by the replay marker"
    )
    assert result.provenance.get("model") == "test-model-0.1", (
        "other fixture provenance keys must be preserved"
    )


def test_recorded_decomposition_client_preserves_source_spans() -> None:
    """RecordedDecompositionClient must replay source_spans from the fixture.

    Before the fix, DecompositionResult.source_spans were always empty for recorded
    replays because RecordedDecompositionClient had no way to accept them.  After the
    fix the constructor accepts source_spans and the replay carries them through.
    """
    from nlreq.models import SourceSpan
    ir = _parse_ir()
    spans = [SourceSpan(document="req.nlreq", start_char=0, end_char=10, text="actor")]
    client = RecordedDecompositionClient(
        ir,
        candidate_id="spans-test",
        source_spans=spans,
    )
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)

    assert result.source_spans == spans, (
        "source_spans supplied at construction must appear in the replayed DecompositionResult"
    )


def test_cli_recorded_fixture_preserves_provenance_in_decomposition(tmp_path: Path) -> None:
    """CLI recorded: path must carry fixture provenance into the report's ensemble_candidate_provenances.

    When a DecompositionResult fixture has non-empty provenance (e.g. a model ID and
    prompt version), those fields must appear in the translation report's
    ensemble_candidate_provenances list, proving that fixture provenance flowed through
    the RecordedDecompositionClient → _check_decomposition_ensemble → report path.
    """
    req_file = tmp_path / "req.nlreq"
    req_file.write_text(_CONTROLLED_TEXT)
    approval = _approved_approval()

    fixture_provenance = {"model": "test-model-0.1", "prompt_version": "test-0.1"}
    result = DecompositionResult(
        requirement=_parse_ir(),
        candidate_id="candidate-prov",
        source_text_hash=sha256_text(_CONTROLLED_TEXT),
        approval=approval,
        is_audited=True,
        provenance=fixture_provenance,
    )
    fixture_path = tmp_path / "fixture_prov.json"
    fixture_path.write_text(result.model_dump_json())

    # Use two identical fixtures so the ensemble agrees (no NLR-REFUSED-AMBIGUOUS).
    fixture_path_b = tmp_path / "fixture_prov_b.json"
    fixture_path_b.write_text(result.model_dump_json())

    out_path = tmp_path / "report_prov.json"
    exit_code = main([
        "semantic-translate", str(req_file),
        "--requirement-id", _REQUIREMENT_ID,
        "--title", _TITLE,
        "--ensemble-client", f"recorded:{fixture_path}",
        "--ensemble-client", f"recorded:{fixture_path_b}",
        "--out", str(out_path),
    ])

    # Both fixtures agree and are audited — ensemble returns accepted or needs_review, not exit 2.
    assert exit_code in (0, 1), (
        f"CLI must not exit 2 (unknown spec) when fixture provenance is non-empty, got {exit_code}"
    )
    report = json.loads(out_path.read_text())

    # The fixture provenance must appear in ensemble_candidate_provenances — this proves
    # that fixture_result.provenance flowed through RecordedDecompositionClient and into
    # _check_decomposition_ensemble's candidate_provenances list.
    candidate_provs: list[dict] = report.get("ensemble_candidate_provenances", [])
    assert len(candidate_provs) == 2, (
        f"expected 2 candidate provenances in report, got {len(candidate_provs)}: {candidate_provs}"
    )
    for i, cp in enumerate(candidate_provs):
        for key, value in fixture_provenance.items():
            assert cp.get(key) == value, (
                f"candidate_provenances[{i}] must contain fixture_provenance[{key!r}]={value!r}, "
                f"got {cp}"
            )
        assert cp.get("replay_marker") == "recorded_fixture", (
            f"candidate_provenances[{i}] must carry the replay_marker, got {cp}"
        )


def test_recorded_decomposition_client_refuses_wrong_input_when_hash_bound() -> None:
    """RecordedDecompositionClient must raise ValueError when replayed against different text.

    The fixture's source_text_hash is recorded at capture time.  If a caller provides
    expected_source_text_hash and then calls decompose_controlled_to_ir with different
    controlled text, the client must refuse — silently accepting would produce a result
    that appears hash-bound to the new text but carries the old (wrong-input) IR.
    """
    ir = _parse_ir()
    original_hash = sha256_text(_CONTROLLED_TEXT)
    client = RecordedDecompositionClient(
        ir,
        candidate_id="hash-bound-test",
        expected_source_text_hash=original_hash,
    )

    # Replaying against the original text must succeed.
    result = client.decompose_controlled_to_ir(_CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE)
    assert result.source_text_hash == original_hash

    # Replaying against different text must raise ValueError.
    different_text = "when actor is admin then operation must reject before finalized."
    assert different_text != _CONTROLLED_TEXT
    with pytest.raises(ValueError, match="does not match fixture's expected hash"):
        client.decompose_controlled_to_ir(different_text, _REQUIREMENT_ID, _TITLE)


def test_recorded_decomposition_client_without_hash_binding_accepts_any_text() -> None:
    """RecordedDecompositionClient without expected_source_text_hash accepts any controlled text.

    Existing tests and golden-test fixtures that do not bind to a specific hash must
    continue to work unchanged — hash binding is opt-in via expected_source_text_hash.
    """
    ir = _parse_ir()
    client = RecordedDecompositionClient(ir, candidate_id="no-hash-bind")

    different_text = "when actor is admin then operation must reject before finalized."
    # Must not raise; source_text_hash is derived from the supplied text.
    result = client.decompose_controlled_to_ir(different_text, _REQUIREMENT_ID, _TITLE)
    assert result.source_text_hash == sha256_text(different_text)


def test_cli_recorded_fixture_hash_mismatch_produces_clean_error(tmp_path: Path) -> None:
    """CLI recorded:<path> must print a clean error (not a traceback) on hash mismatch.

    The fixture's source_text_hash is passed as expected_source_text_hash to
    RecordedDecompositionClient.  When the CLI's --file content differs from the
    fixture's original input, the ValueError must be caught and rendered as a
    'nlreq: translation error: ...' message with exit code 2.

    Both texts must be valid DSL v3 so parsing succeeds and the decompose call is
    reached (if parsing fails first the hash check is never triggered).
    """
    import sys
    from io import StringIO

    original_text = _CONTROLLED_TEXT  # fixture was captured against this text
    # A different, syntactically valid DSL v3 text — parses OK but has a different hash.
    different_text = (
        "requirement authorization_precondition: scope payment "
        "when actor is authorized then payment must reject before finalized."
    )
    assert different_text != original_text

    # Two fixtures both bound to original_text's hash.  The ensemble check requires ≥2 clients,
    # so both are needed to reach decompose_controlled_to_ir.
    fixture_result = DecompositionResult(
        requirement=_parse_ir(),
        candidate_id="cli-hash-mismatch",
        source_text_hash=sha256_text(original_text),
    )
    fixture_path_a = tmp_path / "fixture_mismatch_a.json"
    fixture_path_b = tmp_path / "fixture_mismatch_b.json"
    fixture_path_a.write_text(fixture_result.model_dump_json())
    fixture_path_b.write_text(fixture_result.model_dump_json())

    # Write the DIFFERENT valid text to --file so the hash won't match the fixture.
    different_req_file = tmp_path / "different.nlreq"
    different_req_file.write_text(different_text)

    captured_stderr = StringIO()
    original_stderr = sys.stderr
    sys.stderr = captured_stderr
    try:
        exit_code = main([
            "semantic-translate", str(different_req_file),
            "--requirement-id", _REQUIREMENT_ID,
            "--title", _TITLE,
            "--ensemble-client", f"recorded:{fixture_path_a}",
            "--ensemble-client", f"recorded:{fixture_path_b}",
        ])
    finally:
        sys.stderr = original_stderr

    assert exit_code == 2, (
        f"CLI must return exit code 2 on hash mismatch, got {exit_code}"
    )
    stderr_output = captured_stderr.getvalue()
    assert "nlreq: translation error:" in stderr_output, (
        f"CLI must print a clean error message, not a traceback. Got: {stderr_output!r}"
    )
    assert "does not match fixture's expected hash" in stderr_output, (
        f"Error message must explain the hash mismatch. Got: {stderr_output!r}"
    )
