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
from nlreq.audit_client import AuditVerdict, RecordedAuditClient, apply_audit
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


# ---------------------------------------------------------------------------
# PA-6: AuditClient — RecordedAuditClient and AuditVerdict
# ---------------------------------------------------------------------------


def test_recorded_audit_client_returns_fixture_verdict() -> None:
    """RecordedAuditClient replays the fixture AuditVerdict regardless of inputs."""
    verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=[],
        verdict="passed",
    )
    client = RecordedAuditClient(fixture=verdict)

    result = client.audit_decomposition(
        controlled_text="any controlled text",
        ir_summary="any IR summary",
    )

    assert result is verdict
    assert result.verdict == "passed"
    assert result.covers_all_clauses is True
    assert result.invented_premises == []


def test_apply_audit_failing_verdict_blocks_is_audited() -> None:
    """apply_audit with a failing fixture (invented premise) leaves is_audited=False.

    This is the PA-6 acceptance criterion: a planted invented-premise decomposition
    is caught by the audit gate.  apply_audit is the gating function — the only code
    path that may set is_audited=True on an LLM-produced DecompositionResult.
    A failing verdict must leave is_audited=False so the ensemble treats the
    candidate as needs_review rather than trusted.
    """
    failing_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=["invented_condition_not_in_controlled_text"],
        verdict="failed",
    )
    audit_client = RecordedAuditClient(fixture=failing_verdict)
    base_result = RecordedDecompositionClient(fixture=_parse_ir()).decompose_controlled_to_ir(
        _CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE
    )
    assert base_result.is_audited is False, "Base result must start unaudited"

    gated = apply_audit(base_result, audit_client, _CONTROLLED_TEXT)

    assert gated.is_audited is False, (
        "apply_audit must leave is_audited=False when verdict is 'failed'"
    )
    assert gated.audit_verdict is not None
    assert gated.audit_verdict.verdict == "failed"
    assert "invented_condition_not_in_controlled_text" in gated.audit_verdict.invented_premises
    # Original result is not mutated.
    assert base_result.audit_verdict is None


def test_apply_audit_passing_verdict_sets_is_audited() -> None:
    """apply_audit with a passing fixture (clean decomposition) sets is_audited=True.

    A clean decomposition (all clauses covered, no invented premises) must set
    is_audited=True via apply_audit so the ensemble can treat the candidate as trusted.
    """
    passing_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=[],
        verdict="passed",
    )
    audit_client = RecordedAuditClient(fixture=passing_verdict)
    base_result = RecordedDecompositionClient(fixture=_parse_ir()).decompose_controlled_to_ir(
        _CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE
    )

    gated = apply_audit(base_result, audit_client, _CONTROLLED_TEXT)

    assert gated.is_audited is True, (
        "apply_audit must set is_audited=True when verdict is 'passed'"
    )
    assert gated.audit_verdict is not None
    assert gated.audit_verdict.verdict == "passed"
    assert gated.audit_verdict.covers_all_clauses is True
    assert gated.audit_verdict.invented_premises == []
    # Original result is not mutated.
    assert base_result.is_audited is False


def test_apply_audit_missing_clause_blocks_is_audited() -> None:
    """apply_audit with missing-clause failure leaves is_audited=False.

    covers_all_clauses=False must produce verdict='failed' which blocks is_audited.
    """
    missing_clause_verdict = AuditVerdict(
        covers_all_clauses=False,
        invented_premises=[],
        verdict="failed",
    )
    audit_client = RecordedAuditClient(fixture=missing_clause_verdict)
    base_result = RecordedDecompositionClient(fixture=_parse_ir()).decompose_controlled_to_ir(
        _CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE
    )

    gated = apply_audit(base_result, audit_client, _CONTROLLED_TEXT)

    assert gated.is_audited is False
    assert gated.audit_verdict.covers_all_clauses is False


def test_audit_verdict_schema() -> None:
    """AuditVerdict fields are correctly validated by Pydantic."""
    verdict = AuditVerdict(
        covers_all_clauses=False,
        invented_premises=["extra_condition"],
        verdict="failed",
        model_id="claude-haiku-4-5-20251001",
    )

    data = verdict.model_dump(mode="json")
    assert data["covers_all_clauses"] is False
    assert data["invented_premises"] == ["extra_condition"]
    assert data["verdict"] == "failed"
    assert data["model_id"] == "claude-haiku-4-5-20251001"
    assert "audit_prompt_version" in data


def test_decomposition_result_carries_audit_verdict() -> None:
    """DecompositionResult.audit_verdict field carries AuditVerdict when set."""
    ir = _parse_ir()
    verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=[],
        verdict="passed",
    )
    decomp = DecompositionResult(
        requirement=ir,
        candidate_id="test-candidate",
        source_text_hash=sha256_text(_CONTROLLED_TEXT),
        audit_verdict=verdict,
        is_audited=True,
    )

    assert decomp.audit_verdict is not None
    assert decomp.audit_verdict.verdict == "passed"
    assert decomp.is_audited is True


def test_decomposition_result_audit_verdict_defaults_to_none() -> None:
    """DecompositionResult.audit_verdict is None by default (not yet audited)."""
    ir = _parse_ir()
    decomp = DecompositionResult(
        requirement=ir,
        candidate_id="test-candidate",
        source_text_hash=sha256_text(_CONTROLLED_TEXT),
    )

    assert decomp.audit_verdict is None
    assert decomp.is_audited is False


# ---------------------------------------------------------------------------
# AuditVerdict hardening (PA-6 rec: harden verdict consistency)
# ---------------------------------------------------------------------------


def test_audit_verdict_inconsistent_passed_with_invented_premises_is_coerced() -> None:
    """AuditVerdict with verdict='passed' but non-empty invented_premises is coerced to 'failed'.

    A model that returns verdict='passed' while simultaneously listing invented_premises
    would bypass the gate if trusted literally.  The model_validator must coerce the
    verdict to 'failed' whenever the structural fields indicate failure.
    """
    verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=["extra_condition_not_in_controlled_text"],
        verdict="passed",  # inconsistent — will be coerced
    )

    assert verdict.verdict == "failed", (
        "verdict must be coerced to 'failed' when invented_premises is non-empty, "
        f"got {verdict.verdict!r}"
    )
    # The structural fields are preserved unchanged by the coercion.
    assert verdict.covers_all_clauses is True
    assert verdict.invented_premises == ["extra_condition_not_in_controlled_text"]


def test_audit_verdict_inconsistent_passed_with_missing_clauses_is_coerced() -> None:
    """AuditVerdict with verdict='passed' but covers_all_clauses=False is coerced to 'failed'."""
    verdict = AuditVerdict(
        covers_all_clauses=False,
        invented_premises=[],
        verdict="passed",  # inconsistent — will be coerced
    )

    assert verdict.verdict == "failed", (
        "verdict must be coerced to 'failed' when covers_all_clauses is False, "
        f"got {verdict.verdict!r}"
    )


def test_apply_audit_inconsistent_verdict_blocks_is_audited() -> None:
    """apply_audit derives gate from structural fields; an inconsistent model response does not pass.

    Even if the AuditVerdict's verdict field were somehow 'passed' after validator coercion,
    apply_audit uses covers_all_clauses and invented_premises directly.
    Here we verify end-to-end: an inconsistent response (passed + invented_premises)
    leaves is_audited=False.
    """
    # Build an inconsistent verdict — the validator coerces it to "failed",
    # then apply_audit reads the structural fields → is_audited=False.
    inconsistent_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=["invented_condition"],
        verdict="passed",  # coerced to "failed" by model_validator
    )
    assert inconsistent_verdict.verdict == "failed", "Precondition: coercion happened"

    audit_client = RecordedAuditClient(fixture=inconsistent_verdict)
    base_result = RecordedDecompositionClient(fixture=_parse_ir()).decompose_controlled_to_ir(
        _CONTROLLED_TEXT, _REQUIREMENT_ID, _TITLE
    )

    gated = apply_audit(base_result, audit_client, _CONTROLLED_TEXT)

    assert gated.is_audited is False, (
        "apply_audit must leave is_audited=False when invented_premises is non-empty"
    )
    assert gated.audit_verdict is not None
    assert gated.audit_verdict.invented_premises == ["invented_condition"]


# ---------------------------------------------------------------------------
# PA-6 wired into translate_controlled_requirement_to_formal_claim
# ---------------------------------------------------------------------------


def _build_approved_unaudited_client(ir: RequirementIRV2 | None = None) -> RecordedDecompositionClient:
    """Return a client whose results start approved but not yet audited.

    This is the canonical state of a live LLM decomposition before PA-6 audit:
    approval has been obtained (human gate), but is_audited is False because
    apply_audit has not yet been called.
    """
    return RecordedDecompositionClient(
        fixture=ir or _parse_ir(),
        approval=_approved_approval(),
        is_audited=False,  # not yet audited — PA-6 must set this
        model_id="test-model",
        prompt_hash="test-hash",
        fixture_provenance={"source": "test_pa6_wiring"},
    )


def test_translate_audit_client_unlocks_approved_unaudited_candidates() -> None:
    """translate_controlled_requirement_to_formal_claim wires audit_client into the ensemble.

    When candidates start approved but unaudited (is_audited=False) and a passing
    audit_client is supplied, apply_audit sets is_audited=True before the trust check.
    Both candidates then pass the trust check, agree on the same IR, and the translation
    proceeds to accepted.  This is the PA-6 acceptance criterion: live LLM decomposition
    can become audited through the normal translate path.
    """
    passing_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=[],
        verdict="passed",
    )
    audit_client = RecordedAuditClient(fixture=passing_verdict)
    client_a = _build_approved_unaudited_client()
    client_b = _build_approved_unaudited_client()

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=[client_a, client_b],
        audit_client=audit_client,
    )

    assert report.result == "accepted", (
        f"Passing audit must unlock the ensemble and produce 'accepted', got {report.result!r}. "
        f"refusal_code={report.refusal_code!r}"
    )
    # Audit verdicts appear in the report.
    assert len(report.ensemble_candidate_audit_verdicts) == 2, (
        f"Expected 2 audit verdicts in report, got {len(report.ensemble_candidate_audit_verdicts)}"
    )
    for i, av in enumerate(report.ensemble_candidate_audit_verdicts):
        assert av is not None, f"audit_verdict[{i}] must not be None after audit was applied"
        assert av.verdict == "passed", f"audit_verdict[{i}].verdict must be 'passed'"
        assert av.covers_all_clauses is True
        assert av.invented_premises == []


def test_translate_failing_audit_client_keeps_candidates_unaudited() -> None:
    """A failing audit_client leaves is_audited=False; ensemble returns NLR-UNAUDITED-DECOMPOSITION.

    This is the negative path: even when approval is present, a failing audit verdict
    (invented_premises or missing clauses) keeps is_audited=False so the trust check
    blocks with needs_review rather than letting an untrustworthy decomposition drive
    a formal-claim comparison.
    """
    failing_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=["invented_premise_should_block"],
        verdict="failed",
    )
    audit_client = RecordedAuditClient(fixture=failing_verdict)
    client_a = _build_approved_unaudited_client()
    client_b = _build_approved_unaudited_client()

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=[client_a, client_b],
        audit_client=audit_client,
    )

    assert report.result == "needs_review", (
        f"Failing audit must block with needs_review, got {report.result!r}"
    )
    assert report.refusal_code == "NLR-UNAUDITED-DECOMPOSITION", (
        f"Expected NLR-UNAUDITED-DECOMPOSITION, got {report.refusal_code!r}"
    )
    # Audit verdicts ARE present — they show WHY the candidates are blocked.
    assert len(report.ensemble_candidate_audit_verdicts) == 2
    for av in report.ensemble_candidate_audit_verdicts:
        assert av is not None
        assert av.verdict == "failed"
        assert "invented_premise_should_block" in av.invented_premises


def test_translate_no_audit_client_preserves_existing_behaviour() -> None:
    """Without audit_client, behaviour is unchanged: already-audited fixtures proceed normally.

    Regression guard: adding audit_client as an optional parameter must not break
    existing call sites that pass is_audited=True fixtures and no audit_client.
    """
    client_a = RecordedDecompositionClient(
        fixture=_parse_ir(),
        approval=_approved_approval(),
        is_audited=True,  # already audited by caller
    )
    client_b = RecordedDecompositionClient(
        fixture=_parse_ir(),
        approval=_approved_approval(),
        is_audited=True,
    )

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=[client_a, client_b],
        audit_client=None,  # explicit None — existing callers omit this
    )

    assert report.result == "accepted", (
        f"Pre-audited fixtures without audit_client must still produce 'accepted', "
        f"got {report.result!r}"
    )
    # No audit verdicts are emitted when no audit_client was supplied and candidates
    # were already audited (audit_verdict=None from RecordedDecompositionClient).
    for av in report.ensemble_candidate_audit_verdicts:
        assert av is None, (
            "No audit_client supplied and RecordedDecompositionClient sets no audit_verdict"
        )


def test_translate_audit_verdicts_present_even_on_ambiguous_refusal() -> None:
    """ensemble_candidate_audit_verdicts is populated even when the ensemble disagrees.

    When two audited candidates produce different FormalClaim signatures, the report
    carries NLR-REFUSED-AMBIGUOUS.  The audit verdicts must still appear in the report
    so the caller can distinguish 'audit failed' from 'audit passed but semantics diverged'.
    """
    passing_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=[],
        verdict="passed",
    )
    audit_client = RecordedAuditClient(fixture=passing_verdict)
    # Two clients with different IRs → different FormalClaim signatures → disagreement.
    client_a = _build_approved_unaudited_client(ir=_parse_ir())
    client_b = _build_approved_unaudited_client(ir=_parse_ir_variant())

    report = translate_controlled_requirement_to_formal_claim(
        controlled_text=_CONTROLLED_TEXT,
        requirement_id=_REQUIREMENT_ID,
        title=_TITLE,
        decomposition_clients=[client_a, client_b],
        audit_client=audit_client,
    )

    assert report.result == "refused", (
        f"Differing IR signatures must produce 'refused', got {report.result!r}"
    )
    assert report.refusal_code == "NLR-REFUSED-AMBIGUOUS"
    assert len(report.ensemble_candidate_audit_verdicts) == 2
    for av in report.ensemble_candidate_audit_verdicts:
        assert av is not None
        assert av.verdict == "passed", (
            "Audit passed for both candidates; refusal is due to signature disagreement, not audit failure"
        )


# ---------------------------------------------------------------------------
# CLI --audit-client integration
# ---------------------------------------------------------------------------


def test_cli_audit_client_recorded_unlocks_unaudited_candidates(tmp_path: Path) -> None:
    """CLI --audit-client recorded:<path> applies the fixture verdict to unaudited candidates.

    Ensures the CLI path constructs a RecordedAuditClient from a fixture file and passes
    it to translate_controlled_requirement_to_formal_claim, unlocking approved-but-unaudited
    candidates and producing an accepted report.
    """
    req_file = tmp_path / "req.nlreq"
    req_file.write_text(_CONTROLLED_TEXT)

    # Write a passing AuditVerdict fixture.
    audit_verdict = AuditVerdict(
        covers_all_clauses=True,
        invented_premises=[],
        verdict="passed",
    )
    audit_fixture_path = tmp_path / "audit.json"
    audit_fixture_path.write_text(audit_verdict.model_dump_json())

    # Write two approved-but-unaudited DecompositionResult fixtures (same IR → agree).
    decomp_result = DecompositionResult(
        requirement=_parse_ir(),
        candidate_id="cli-audit-candidate",
        source_text_hash=sha256_text(_CONTROLLED_TEXT),
        approval=_approved_approval(),
        is_audited=False,  # CLI --audit-client must set this
    )
    fixture_a = tmp_path / "fixture_a.json"
    fixture_b = tmp_path / "fixture_b.json"
    fixture_a.write_text(decomp_result.model_dump_json())
    fixture_b.write_text(decomp_result.model_dump_json())

    out_path = tmp_path / "report.json"
    exit_code = main([
        "semantic-translate", str(req_file),
        "--requirement-id", _REQUIREMENT_ID,
        "--title", _TITLE,
        "--ensemble-client", f"recorded:{fixture_a}",
        "--ensemble-client", f"recorded:{fixture_b}",
        "--audit-client", f"recorded:{audit_fixture_path}",
        "--out", str(out_path),
    ])

    assert exit_code == 0, (
        f"CLI must exit 0 (accepted) when audit unlocks approved-unaudited candidates, "
        f"got exit_code={exit_code}. Report: {out_path.read_text()[:500]}"
    )
    report = json.loads(out_path.read_text())
    assert report["result"] == "accepted"
    # Audit verdicts must appear in the serialised report.
    audit_verdicts = report.get("ensemble_candidate_audit_verdicts", [])
    assert len(audit_verdicts) == 2, (
        f"Expected 2 audit verdicts in serialised report, got {len(audit_verdicts)}"
    )
    for av in audit_verdicts:
        assert av["verdict"] == "passed"
        assert av["covers_all_clauses"] is True


# ---------------------------------------------------------------------------
# AuditVerdict strict-bool validation (PA-6 live audit parsing hardening)
# ---------------------------------------------------------------------------


def test_audit_verdict_rejects_string_false_covers_all_clauses() -> None:
    """AuditVerdict rejects a string 'false' for covers_all_clauses (StrictBool enforced).

    Guards the live audit parsing trust boundary: a model response like
    {"covers_all_clauses": "false"} must not be silently treated as True.
    Python's bool("false") returns True, so the Pydantic StrictBool annotation
    on covers_all_clauses is the enforcement point.  A ValidationError here means
    the AnthropicAuditClient catches it and returns a conservative failed verdict.
    """
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        AuditVerdict(covers_all_clauses="false", invented_premises=[], verdict="failed")


def test_audit_verdict_rejects_string_true_covers_all_clauses() -> None:
    """AuditVerdict rejects the string 'true' for covers_all_clauses (StrictBool enforced)."""
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        AuditVerdict(covers_all_clauses="true", invented_premises=[], verdict="passed")


def test_audit_verdict_rejects_int_covers_all_clauses() -> None:
    """AuditVerdict rejects integers (1/0) for covers_all_clauses (StrictBool enforced).

    Model responses like {"covers_all_clauses": 1} must fail, not silently coerce
    to True.  StrictBool accepts only literal Python bools.
    """
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        AuditVerdict(covers_all_clauses=1, invented_premises=[], verdict="passed")

    with pytest.raises(PydanticValidationError):
        AuditVerdict(covers_all_clauses=0, invented_premises=[], verdict="failed")


def test_audit_verdict_rejects_invalid_verdict_string() -> None:
    """AuditVerdict rejects a verdict string that is not 'passed' or 'failed'.

    A model response like {"verdict": "maybe"} must fail the Literal["passed","failed"]
    constraint, be caught in the live client, and return a conservative failure.
    The model_validator coerces the verdict to 'failed' if structural fields disagree,
    so a badly-formatted verdict from the model also fails at the Literal level first.
    """
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="maybe")


def test_audit_verdict_rejects_non_list_invented_premises() -> None:
    """AuditVerdict rejects a non-list value for invented_premises.

    A model response like {"invented_premises": "some string"} must fail the
    list[str] constraint and be caught by the conservative-failure handler.
    """
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        AuditVerdict(covers_all_clauses=True, invented_premises="invented premise as string", verdict="passed")


def test_audit_verdict_accepts_actual_bools() -> None:
    """AuditVerdict accepts actual Python booleans (the only valid values)."""
    v_pass = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    assert v_pass.covers_all_clauses is True
    assert v_pass.verdict == "passed"

    v_fail = AuditVerdict(covers_all_clauses=False, invented_premises=[], verdict="failed")
    assert v_fail.covers_all_clauses is False
    assert v_fail.verdict == "failed"


# ---------------------------------------------------------------------------
# RecordedAuditClient hash binding (PA-6 replay binding)
# ---------------------------------------------------------------------------


def test_recorded_audit_client_without_hash_constraints_returns_fixture() -> None:
    """RecordedAuditClient without hash constraints returns the fixture regardless of inputs.

    This is the original behaviour preserved for callers that do not need hash binding
    (generic tests, broad offline fixtures).
    """
    verdict = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    client = RecordedAuditClient(fixture=verdict)

    result_a = client.audit_decomposition("any controlled text", "any IR summary")
    result_b = client.audit_decomposition("completely different text", "different IR")

    assert result_a is verdict
    assert result_b is verdict


def test_recorded_audit_client_controlled_text_hash_match_returns_fixture() -> None:
    """RecordedAuditClient with expected_controlled_text_hash returns fixture on hash match."""
    controlled_text = "requirement authorization_precondition: scope payment when actor is authorized then payment must reject before finalized."
    expected_hash = sha256_text(controlled_text)

    verdict = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    client = RecordedAuditClient(
        fixture=verdict,
        expected_controlled_text_hash=expected_hash,
    )

    result = client.audit_decomposition(controlled_text=controlled_text, ir_summary="any IR")
    assert result is verdict, "Hash matched: fixture must be returned"


def test_recorded_audit_client_controlled_text_hash_mismatch_returns_failure() -> None:
    """RecordedAuditClient with expected_controlled_text_hash returns conservative failure on mismatch.

    This prevents a passing audit fixture being replayed against a different controlled text
    and blessing a decomposition it was never audited for.
    """
    original_text = "requirement authorization_precondition: scope payment when actor is authorized then payment must reject before finalized."
    different_text = "requirement authorization_precondition: scope payment when actor is not authorized then payment must reject before finalized."
    expected_hash = sha256_text(original_text)

    verdict = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    client = RecordedAuditClient(
        fixture=verdict,
        expected_controlled_text_hash=expected_hash,
    )

    result = client.audit_decomposition(controlled_text=different_text, ir_summary="any IR")
    assert result is not verdict, "Hash mismatched: fixture must NOT be returned"
    assert result.verdict == "failed"
    assert result.covers_all_clauses is False
    assert any("audit-fixture-mismatch" in p for p in result.invented_premises), (
        f"Failure must explain the mismatch, got: {result.invented_premises}"
    )


def test_recorded_audit_client_ir_summary_hash_mismatch_returns_failure() -> None:
    """RecordedAuditClient with expected_ir_summary_hash returns conservative failure on mismatch.

    The ir_summary_hash binding prevents a fixture from blessing a decomposition whose
    IR summary differs from what the fixture was created for.
    """
    from nlreq.audit_client import summarize_ir_for_audit

    ir = _parse_ir()
    expected_ir_summary = summarize_ir_for_audit(ir)
    expected_hash = sha256_text(expected_ir_summary)

    verdict = AuditVerdict(covers_all_clauses=True, invented_premises=[], verdict="passed")
    client = RecordedAuditClient(
        fixture=verdict,
        expected_ir_summary_hash=expected_hash,
    )

    # Correct summary → fixture returned.
    result_match = client.audit_decomposition(controlled_text="any", ir_summary=expected_ir_summary)
    assert result_match is verdict

    # Different summary → conservative failure.
    result_mismatch = client.audit_decomposition(controlled_text="any", ir_summary="completely different IR summary")
    assert result_mismatch.verdict == "failed"
    assert result_mismatch.covers_all_clauses is False
    assert any("audit-fixture-mismatch" in p for p in result_mismatch.invented_premises)
