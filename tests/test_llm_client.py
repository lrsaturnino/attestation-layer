"""Tests for PA-4: LLM-backed free-NL → controlled drafting.

Covers:
  - LlmClient protocol structural check
  - RecordedLlmClient fixture replay
  - UnavailableLlmClient error surface
  - draft_controlled_rewrite_with_llm: provenance, approval gate
  - intake-draft --method llm CLI path (offline, via --fixture)
  - intake-draft --method manual still requires --suggested
  - Approval gate blocks parsing until explicit human approval
  - Rejecting the diff keeps the parser blocked
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.dsl_v3 import canonicalize_dsl_v3_text
from nlreq.intake import (
    approve_controlled_rewrite,
    build_dsl_grammar_summary,
    build_rewrite_prompt,
    controlled_text_for_parsing,
    create_free_form_intake,
    draft_controlled_rewrite_with_llm,
)
from nlreq.llm_client import LlmClient, RecordedLlmClient, UnavailableLlmClient


# A valid DSL v3 controlled text used as a recorded fixture in all offline tests.
_FIXTURE_CONTROLLED = (
    "requirement authorization_precondition:\n"
    "scope operation\n"
    "when actor is not authorized\n"
    "then operation must reject before state_change\n"
)

_PROSE = "Unauthorised actors must be blocked before any state change occurs."


# ---------------------------------------------------------------------------
# LlmClient interface
# ---------------------------------------------------------------------------


def test_recorded_llm_client_is_llm_client_protocol() -> None:
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    assert isinstance(client, LlmClient)


def test_unavailable_llm_client_is_llm_client_protocol() -> None:
    client = UnavailableLlmClient()
    assert isinstance(client, LlmClient)


def test_recorded_llm_client_returns_fixture_verbatim() -> None:
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    result = client.propose_controlled_rewrite(_PROSE, "grammar")
    assert result == _FIXTURE_CONTROLLED


def test_recorded_llm_client_ignores_prose_and_grammar() -> None:
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    r1 = client.propose_controlled_rewrite("prose A", "g1")
    r2 = client.propose_controlled_rewrite("prose B", "g2")
    assert r1 == r2 == _FIXTURE_CONTROLLED


def test_unavailable_llm_client_raises_not_implemented() -> None:
    client = UnavailableLlmClient()
    with pytest.raises(NotImplementedError, match="anthropic"):
        client.propose_controlled_rewrite(_PROSE, "grammar")


# ---------------------------------------------------------------------------
# Grammar summary and prompt helpers
# ---------------------------------------------------------------------------


def test_grammar_summary_is_deterministic() -> None:
    assert build_dsl_grammar_summary() == build_dsl_grammar_summary()


def test_grammar_summary_contains_claim_classes() -> None:
    summary = build_dsl_grammar_summary()
    assert "authorization_precondition" in summary
    assert "numeric_invariant" in summary
    assert "bounded_temporal" in summary


def test_rewrite_prompt_contains_prose() -> None:
    prompt = build_rewrite_prompt(_PROSE, build_dsl_grammar_summary())
    assert _PROSE in prompt


def test_rewrite_prompt_is_deterministic() -> None:
    gs = build_dsl_grammar_summary()
    assert build_rewrite_prompt(_PROSE, gs) == build_rewrite_prompt(_PROSE, gs)


# ---------------------------------------------------------------------------
# draft_controlled_rewrite_with_llm: provenance
# ---------------------------------------------------------------------------


def test_draft_produces_needs_approval_proposal() -> None:
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-1",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-1",
        timestamp="2026-06-01T00:01:00Z",
        model="test-model-v1",
    )
    assert proposal.status == "needs_approval"
    assert proposal.producer.method == "llm"
    assert proposal.producer.model == "test-model-v1"
    assert proposal.proposed_controlled_text == _FIXTURE_CONTROLLED
    assert proposal.intake_id == intake.intake_id
    assert proposal.original_text_hash == intake.original_text_hash


def test_draft_records_prompt_hash_in_provenance() -> None:
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-2",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-2",
        timestamp="2026-06-01T00:01:00Z",
    )
    # Prompt hash must be present — it binds the provenance to the exact prompt.
    assert proposal.producer.prompt_hash is not None
    assert proposal.producer.prompt_hash.startswith("sha256:")
    # The stored prompt must reproduce the same hash.
    from nlreq.jsonutil import sha256_text

    assert proposal.producer.prompt_hash == sha256_text(proposal.producer.prompt)


def test_draft_prompt_is_deterministic_across_calls() -> None:
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-3",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    p1 = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-3a",
        timestamp="2026-06-01T00:01:00Z",
    )
    p2 = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-3b",
        timestamp="2026-06-01T00:01:00Z",
    )
    assert p1.producer.prompt_hash == p2.producer.prompt_hash


# ---------------------------------------------------------------------------
# Approval gate: parser blocked until explicit human approval
# ---------------------------------------------------------------------------


def test_draft_approval_gate_blocks_parsing_before_approval() -> None:
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-4",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-4",
        timestamp="2026-06-01T00:01:00Z",
    )
    with pytest.raises(ValueError, match="explicitly approved"):
        controlled_text_for_parsing(proposal, None)


def test_draft_approval_gate_unblocks_after_human_approval() -> None:
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-5",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-5",
        timestamp="2026-06-01T00:01:00Z",
    )
    approval = approve_controlled_rewrite(
        proposal,
        approval_id="APPROVAL-PA4-5",
        approved_by="reviewer@example.invalid",
        approved_at="2026-06-01T00:02:00Z",
    )
    text = controlled_text_for_parsing(proposal, approval)
    assert text == _FIXTURE_CONTROLLED
    assert approval.approved_diff_hash == proposal.diff_hash


def test_draft_approval_gate_rejects_tampered_hash() -> None:
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-6",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-6",
        timestamp="2026-06-01T00:01:00Z",
    )
    approval = approve_controlled_rewrite(
        proposal,
        approval_id="APPROVAL-PA4-6",
        approved_by="reviewer@example.invalid",
        approved_at="2026-06-01T00:02:00Z",
    )
    tampered = approval.model_copy(
        update={"reviewed_original_text_hash": "sha256:not-the-original"}
    )
    with pytest.raises(ValueError, match="original intake text"):
        controlled_text_for_parsing(proposal, tampered)


def test_draft_approval_gate_blocks_on_explicit_reject_decision() -> None:
    """An explicit human reject (decision='rejected') must block the parser.

    This is the named acceptance criterion: 'rejecting the diff blocks the
    parser.'  A reject decision is distinct from a tampered hash — it is the
    human operator saying 'no' after reviewing the diff.
    """
    intake = create_free_form_intake(
        intake_id="INTAKE-PA4-7",
        original_text=_PROSE,
        submitted_at="2026-06-01T00:00:00Z",
    )
    client = RecordedLlmClient(_FIXTURE_CONTROLLED)
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=client,
        proposal_id="PROP-PA4-7",
        timestamp="2026-06-01T00:01:00Z",
    )
    from nlreq.intake import approve_controlled_rewrite as _approve

    rejection = _approve(
        proposal,
        approval_id="REJECTION-PA4-7",
        approved_by="reviewer@example.invalid",
        approved_at="2026-06-01T00:02:00Z",
        decision="rejected",
    )
    # The parser must still be blocked — a rejected approval is not valid to parse.
    with pytest.raises(ValueError):
        controlled_text_for_parsing(proposal, rejection)


# ---------------------------------------------------------------------------
# CLI: intake-draft --method llm --fixture
# ---------------------------------------------------------------------------


def test_cli_intake_draft_method_llm_with_fixture(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    fixture_path = tmp_path / "fixture.nlreq3"
    proposal_path = tmp_path / "proposal.json"
    original.write_text(_PROSE)
    fixture_path.write_text(_FIXTURE_CONTROLLED)

    rc = main(
        [
            "intake-draft",
            str(original),
            "--method",
            "llm",
            "--fixture",
            str(fixture_path),
            "--intake-id",
            "INTAKE-CLI-LLM-1",
            "--proposal-id",
            "PROP-CLI-LLM-1",
            "--timestamp",
            "2026-06-01T00:01:00Z",
            "--out",
            str(proposal_path),
        ]
    )
    assert rc == 0
    data = json.loads(proposal_path.read_text())
    assert data["producer"]["method"] == "llm"
    assert data["proposed_controlled_text"] == _FIXTURE_CONTROLLED
    assert data["status"] == "needs_approval"


def test_cli_intake_draft_method_llm_also_writes_intake_out(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    fixture_path = tmp_path / "fixture.nlreq3"
    proposal_path = tmp_path / "proposal.json"
    intake_path = tmp_path / "intake.json"
    original.write_text(_PROSE)
    fixture_path.write_text(_FIXTURE_CONTROLLED)

    rc = main(
        [
            "intake-draft",
            str(original),
            "--method",
            "llm",
            "--fixture",
            str(fixture_path),
            "--intake-id",
            "INTAKE-CLI-LLM-2",
            "--proposal-id",
            "PROP-CLI-LLM-2",
            "--timestamp",
            "2026-06-01T00:01:00Z",
            "--out",
            str(proposal_path),
            "--intake-out",
            str(intake_path),
        ]
    )
    assert rc == 0
    assert intake_path.exists()
    intake_data = json.loads(intake_path.read_text())
    assert intake_data["intake_id"] == "INTAKE-CLI-LLM-2"


def test_cli_intake_draft_method_llm_records_model_in_provenance(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    fixture_path = tmp_path / "fixture.nlreq3"
    proposal_path = tmp_path / "proposal.json"
    original.write_text(_PROSE)
    fixture_path.write_text(_FIXTURE_CONTROLLED)

    main(
        [
            "intake-draft",
            str(original),
            "--method",
            "llm",
            "--fixture",
            str(fixture_path),
            "--intake-id",
            "INTAKE-CLI-LLM-3",
            "--proposal-id",
            "PROP-CLI-LLM-3",
            "--timestamp",
            "2026-06-01T00:01:00Z",
            "--model",
            "claude-sonnet-4-6",
            "--out",
            str(proposal_path),
        ]
    )
    data = json.loads(proposal_path.read_text())
    assert data["producer"]["model"] == "claude-sonnet-4-6"
    assert data["producer"]["prompt_hash"] is not None


# ---------------------------------------------------------------------------
# CLI: intake-draft --method manual (backward compat)
# ---------------------------------------------------------------------------


def test_cli_intake_draft_method_manual_requires_suggested(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    proposal_path = tmp_path / "proposal.json"
    original.write_text(_PROSE)

    rc = main(
        [
            "intake-draft",
            str(original),
            "--method",
            "manual",
            "--intake-id",
            "INTAKE-CLI-MAN-1",
            "--proposal-id",
            "PROP-CLI-MAN-1",
            "--out",
            str(proposal_path),
        ]
    )
    assert rc != 0


def test_cli_intake_draft_method_manual_with_suggested_works(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    suggested = tmp_path / "suggested.nlreq3"
    proposal_path = tmp_path / "proposal.json"
    original.write_text(_PROSE)
    suggested.write_text(_FIXTURE_CONTROLLED)

    rc = main(
        [
            "intake-draft",
            str(original),
            "--method",
            "manual",
            "--suggested",
            str(suggested),
            "--intake-id",
            "INTAKE-CLI-MAN-2",
            "--proposal-id",
            "PROP-CLI-MAN-2",
            "--out",
            str(proposal_path),
        ]
    )
    assert rc == 0
    data = json.loads(proposal_path.read_text())
    assert data["producer"]["method"] == "manual"
    assert data["proposed_controlled_text"] == _FIXTURE_CONTROLLED


def test_cli_intake_draft_default_method_is_manual(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    suggested = tmp_path / "suggested.nlreq3"
    proposal_path = tmp_path / "proposal.json"
    original.write_text(_PROSE)
    suggested.write_text(_FIXTURE_CONTROLLED)

    rc = main(
        [
            "intake-draft",
            str(original),
            "--suggested",
            str(suggested),
            "--intake-id",
            "INTAKE-CLI-DEFAULT",
            "--proposal-id",
            "PROP-CLI-DEFAULT",
            "--out",
            str(proposal_path),
        ]
    )
    assert rc == 0
    data = json.loads(proposal_path.read_text())
    assert data["producer"]["method"] == "manual"


# ---------------------------------------------------------------------------
# Full offline round-trip: LLM draft → approval → parse
# ---------------------------------------------------------------------------


def test_offline_llm_draft_full_roundtrip(tmp_path: Path) -> None:
    """End-to-end: fixture replay → proposal → CLI approval → text extracted."""
    original = tmp_path / "original.txt"
    fixture_path = tmp_path / "fixture.nlreq3"
    proposal_path = tmp_path / "proposal.json"
    intake_path = tmp_path / "intake.json"
    approval_path = tmp_path / "approval.json"
    original.write_text(_PROSE)
    fixture_path.write_text(_FIXTURE_CONTROLLED)

    assert (
        main(
            [
                "intake-draft",
                str(original),
                "--method",
                "llm",
                "--fixture",
                str(fixture_path),
                "--intake-id",
                "INTAKE-RT-1",
                "--proposal-id",
                "PROP-RT-1",
                "--timestamp",
                "2026-06-01T00:01:00Z",
                "--out",
                str(proposal_path),
                "--intake-out",
                str(intake_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "intake-approve",
                str(proposal_path),
                "--approval-id",
                "APPROVAL-RT-1",
                "--approved-by",
                "reviewer@example.invalid",
                "--out",
                str(approval_path),
            ]
        )
        == 0
    )

    from nlreq.intake import ControlledRewriteApproval, ControlledRewriteProposal

    proposal = ControlledRewriteProposal.model_validate_json(proposal_path.read_text())
    approval = ControlledRewriteApproval.model_validate_json(approval_path.read_text())

    text = controlled_text_for_parsing(proposal, approval)
    assert text == _FIXTURE_CONTROLLED
    # Confirm the controlled text is parseable by DSL v3.
    from nlreq.dsl_v3 import DslV3Parser

    ir = DslV3Parser().parse_ir(text, requirement_id="REQ-RT-1", title="roundtrip")
    assert ir.semantic_ir.metadata["requirement_class"] == "authorization_precondition"


# ---------------------------------------------------------------------------
# AnthropicLlmClient — real client construction (no network calls)
# ---------------------------------------------------------------------------


def test_anthropic_llm_client_constructs_without_key_in_env(monkeypatch) -> None:
    """AnthropicLlmClient construction does not read the key — only propose_controlled_rewrite does."""
    from nlreq.llm_client import AnthropicLlmClient

    monkeypatch.delenv("NLREQ_ANTHROPIC_API_KEY", raising=False)
    # Construction must not raise — the key is read lazily on the first call.
    client = AnthropicLlmClient()
    assert client is not None


def test_anthropic_llm_client_raises_on_missing_key(monkeypatch) -> None:
    """propose_controlled_rewrite raises EnvironmentError when NLREQ_ANTHROPIC_API_KEY is absent."""
    import pytest
    from nlreq.llm_client import AnthropicLlmClient

    monkeypatch.delenv("NLREQ_ANTHROPIC_API_KEY", raising=False)
    client = AnthropicLlmClient()
    with pytest.raises(EnvironmentError, match="NLREQ_ANTHROPIC_API_KEY"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_anthropic_llm_client_raises_on_empty_key(monkeypatch) -> None:
    """propose_controlled_rewrite raises EnvironmentError when NLREQ_ANTHROPIC_API_KEY is empty."""
    import pytest
    from nlreq.llm_client import AnthropicLlmClient

    monkeypatch.setenv("NLREQ_ANTHROPIC_API_KEY", "  ")
    client = AnthropicLlmClient()
    with pytest.raises(EnvironmentError, match="NLREQ_ANTHROPIC_API_KEY"):
        client.propose_controlled_rewrite("prose", "grammar")


def test_anthropic_llm_client_is_llm_client_protocol() -> None:
    """AnthropicLlmClient satisfies the LlmClient Protocol (checked at runtime)."""
    from nlreq.llm_client import AnthropicLlmClient, LlmClient

    client = AnthropicLlmClient()
    assert isinstance(client, LlmClient)


def test_intake_draft_llm_no_fixture_constructs_real_client(monkeypatch, tmp_path: Path, capsys) -> None:
    """intake-draft --method llm without --fixture uses AnthropicLlmClient (missing key → non-zero, not silent stub).

    The real client raises EnvironmentError on missing credentials; the CLI catches it and
    returns 1 with a message to stderr. This proves the non-fixture path is wired to
    AnthropicLlmClient, not UnavailableLlmClient (which raises NotImplementedError, not EnvironmentError).
    """
    from nlreq.cli import main

    monkeypatch.delenv("NLREQ_ANTHROPIC_API_KEY", raising=False)
    original = tmp_path / "original.txt"
    original.write_text(_PROSE)

    exit_code = main(
        [
            "intake-draft",
            str(original),
            "--method",
            "llm",
            "--intake-id",
            "INTAKE-REAL-1",
            "--proposal-id",
            "PROP-REAL-1",
            "--out",
            str(tmp_path / "proposal.json"),
        ]
    )
    captured = capsys.readouterr()
    # The CLI must exit with a non-zero code (not succeed silently) and surface
    # the credential variable name so the operator knows what to fix.
    assert exit_code != 0, "Missing credential must produce a non-zero exit code"
    assert "NLREQ_ANTHROPIC_API_KEY" in captured.err, (
        f"Expected credential variable name in stderr, got: {captured.err!r}"
    )


def test_load_api_key_requires_env_var(monkeypatch) -> None:
    """load_api_key() raises EnvironmentError with the expected variable name when unset."""
    from nlreq.llm_client import load_api_key, NLREQ_API_KEY_ENV
    import pytest

    monkeypatch.delenv(NLREQ_API_KEY_ENV, raising=False)
    with pytest.raises(EnvironmentError, match=NLREQ_API_KEY_ENV):
        load_api_key()


def test_load_api_key_returns_key_from_env(monkeypatch) -> None:
    """load_api_key() returns the key when NLREQ_ANTHROPIC_API_KEY is set."""
    from nlreq.llm_client import load_api_key, NLREQ_API_KEY_ENV

    monkeypatch.setenv(NLREQ_API_KEY_ENV, "sk-test-key")
    assert load_api_key() == "sk-test-key"
