"""PA-11 multilingual NL intake, corpus, metrics, and refusal.

Non-English prose flows through the same PA-4 drafting path (the IR is language-neutral).
Provenance records the source language; merchant/identifier strings stay verbatim; a
low-confidence cross-language fragment refuses with a clarification rather than guessing.
The EN/PT spike reports per-language false-acceptance/false-refusal and demonstrates
EN<->PT FormalClaim signature equivalence.
"""

from __future__ import annotations

from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_claim import build_formal_claim, formal_claim_signature
from nlreq.intake import (
    ControlledRewriteProposal,
    FreeFormIntakeArtifact,
    build_dsl_grammar_summary,
    build_rewrite_prompt,
    create_controlled_rewrite_proposal,
    create_free_form_intake,
    cross_language_clarification,
    draft_controlled_rewrite_with_llm,
)
from nlreq.llm_client import CROSS_LANGUAGE_CLARIFY_SENTINEL, RecordedLlmClient
from nlreq.refusal import build_refusal_report_from_semantic_translation
from nlreq.semantic_translation import refuse_low_confidence_cross_language
from nlreq.translation_benchmark import (
    RequirementTranslationCorpus,
    build_translation_benchmark_report,
    run_translation_corpus,
)


MULTILINGUAL_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "translation-corpus"
    / "multilingual.corpus.json"
)

_MERCHANT_CONTROLLED = (
    "requirement state_postcondition:\n"
    "scope payment\n"
    "when payer is approved\n"
    'then state merchant_name must be "Café Lögïstica Ltda"\n'
)


# --- provenance: source language is recorded, English prompt is unchanged ------------------


def test_english_prompt_is_byte_identical_so_prompt_hash_is_stable() -> None:
    grammar = build_dsl_grammar_summary()
    # The "en" default must not perturb the prompt (or its pinned hash).
    assert build_rewrite_prompt("prose", grammar) == build_rewrite_prompt(
        "prose", grammar, language="en"
    )
    assert build_rewrite_prompt("prose", grammar, language="pt") != build_rewrite_prompt(
        "prose", grammar, language="en"
    )


def test_draft_records_source_language_in_provenance() -> None:
    intake = create_free_form_intake(
        intake_id="i-pt",
        original_text="O saque não autorizado deve ser rejeitado.",
        submitted_at="2026-01-01T00:00:00Z",
        language="pt",
    )
    proposal = draft_controlled_rewrite_with_llm(
        intake=intake,
        client=RecordedLlmClient("requirement state_precondition:\nscope op\nwhen a is approved\nthen op must succeed\n"),
        proposal_id="p",
        timestamp="2026-01-01T00:00:00Z",
        model="recorded",
    )
    # Source language defaults from the intake and is recorded on the proposal itself.
    assert proposal.producer.metadata["source_language"] == "pt"


def test_recorded_client_accepts_language_and_replays_fixture() -> None:
    client = RecordedLlmClient("fixture-text")
    assert client.propose_controlled_rewrite("prose", "grammar", language="pt") == "fixture-text"
    assert client.propose_controlled_rewrite("prose", "grammar") == "fixture-text"


# --- verbatim merchant/identifier strings (non-LLM path) ----------------------------------


def test_merchant_string_stays_verbatim_through_the_non_llm_intake_path() -> None:
    merchant = "Café Lögïstica Ltda"
    intake = create_free_form_intake(
        intake_id="i",
        original_text=f"O pagamento ao {merchant} deve ser registrado.",
        submitted_at="2026-01-01T00:00:00Z",
        language="pt",
    )
    proposal = create_controlled_rewrite_proposal(
        intake=intake,
        proposal_id="p",
        proposed_controlled_text=_MERCHANT_CONTROLLED,
        timestamp="2026-01-01T00:00:00Z",
        method="manual",
    )
    # The verbatim, non-ASCII merchant string is preserved on both the intake and the
    # proposal; the controlled DSL keeps it inside the quoted literal, untranslated.
    assert merchant in intake.original_text
    assert merchant in proposal.proposed_controlled_text


def test_cli_intake_draft_pt_records_source_language_and_keeps_merchant_verbatim(tmp_path) -> None:
    # The CLI intake path (not only the manual proposal helper) must thread --language pt
    # through PA-4: the intake records source_language=pt, the LLM draft uses the non-English
    # prompt addendum, and the verbatim non-ASCII merchant string survives into the proposal.
    merchant = "Café Lögïstica Ltda"
    prose = f"O pagamento ao {merchant} deve ser registrado quando o pagador estiver aprovado."
    original = tmp_path / "prose.pt.txt"
    original.write_text(prose)
    fixture = tmp_path / "fixture.nlreq3"
    fixture.write_text(_MERCHANT_CONTROLLED)
    intake_out = tmp_path / "intake.json"
    proposal_out = tmp_path / "proposal.json"

    exit_code = main(
        [
            "intake-draft",
            str(original),
            "--method",
            "llm",
            "--fixture",
            str(fixture),
            "--language",
            "pt",
            "--intake-id",
            "INTAKE-PT-1",
            "--proposal-id",
            "PROP-PT-1",
            "--intake-out",
            str(intake_out),
            "--out",
            str(proposal_out),
        ]
    )
    assert exit_code == 0

    intake = FreeFormIntakeArtifact.model_validate_json(intake_out.read_text())
    proposal = ControlledRewriteProposal.model_validate_json(proposal_out.read_text())
    # Provenance records the submitted language, not the English default.
    assert intake.language == "pt"
    assert proposal.producer.metadata["source_language"] == "pt"
    assert proposal.producer.method == "llm"
    # The drafting prompt took the non-English path (the addendum names the language code).
    assert "code 'pt'" in (proposal.producer.prompt or "")
    # The verbatim merchant string stayed verbatim from PT prose into the controlled output.
    assert merchant in intake.original_text
    assert merchant in proposal.proposed_controlled_text


def test_merchant_string_survives_into_the_formal_claim() -> None:
    import json

    ir = DslV3Parser().parse_ir(_MERCHANT_CONTROLLED, requirement_id="R-M", title="t")
    report = build_formal_claim(ir)
    assert report.result == "lowered"
    blob = json.dumps(report.formal_claim.model_dump(mode="json"), ensure_ascii=False)
    assert "Café Lögïstica Ltda" in blob


# --- low-confidence cross-language refusal -------------------------------------------------


def test_cross_language_clarification_detects_sentinel() -> None:
    assert cross_language_clarification("requirement state_precondition:\n...") is None
    fragment = cross_language_clarification(f"{CROSS_LANGUAGE_CLARIFY_SENTINEL} carência contratual")
    assert fragment == "carência contratual"


def test_low_confidence_cross_language_refusal_is_actionable() -> None:
    report = refuse_low_confidence_cross_language(
        requirement_id="R-PT",
        language="pt",
        fragment="carência contratual de resgate antecipado",
        prose="O saque respeita a carência contratual de resgate antecipado.",
    )
    assert report.result == "refused"
    assert report.refusal_code == "NLR-CROSS-LANGUAGE-UNCERTAIN"

    refusal = build_refusal_report_from_semantic_translation(report)
    finding = refusal.findings[0]
    assert finding.code == "NLR-CROSS-LANGUAGE-UNCERTAIN"
    # The untranslatable fragment is localized verbatim (non-ASCII preserved) with actions.
    assert finding.source_spans[0].text == "carência contratual de resgate antecipado"
    assert finding.next_actions


# --- multilingual corpus: per-language metrics + EN<->PT equivalence -----------------------


def _load_multilingual() -> RequirementTranslationCorpus:
    return RequirementTranslationCorpus.model_validate_json(MULTILINGUAL_CORPUS.read_text())


def test_multilingual_corpus_has_paired_en_and_pt_requirements() -> None:
    corpus = _load_multilingual()
    en = {c.case_id[:-3] for c in corpus.cases if c.language == "en"}
    pt = {c.case_id[:-3] for c in corpus.cases if c.language == "pt" and not c.case_id.startswith("ml-lc")}
    assert len(en) >= 20
    assert en == pt, "every English requirement must have a Portuguese twin"


def test_portuguese_rates_are_within_the_english_budget() -> None:
    # The NL-agnostic claim is scoped to languages whose recorded rates match English. On
    # this spike Portuguese matches English: zero false-acceptance and zero false-refusal.
    corpus = _load_multilingual()
    report = build_translation_benchmark_report(corpus, run_translation_corpus(corpus))
    assert report.result == "passed"
    by_lang = {m.language: m for m in report.languages}
    assert set(by_lang) == {"en", "pt"}
    english = by_lang["en"]
    portuguese = by_lang["pt"]
    assert portuguese.false_acceptance_count <= english.false_acceptance_count == 0
    assert portuguese.false_refusal_count <= english.false_refusal_count == 0


def test_en_pt_pairs_produce_equivalent_formal_claim_signatures() -> None:
    # The controlled DSL is language-neutral, so an EN requirement and its PT twin lower to
    # FormalClaims with identical alpha/commutative-normalised signatures.
    corpus = _load_multilingual()
    by_id = {c.case_id: c for c in corpus.cases}
    bases = sorted(
        cid[:-3] for cid in by_id if cid.endswith("-en") and cid.startswith("ml-")
    )
    assert bases, "expected paired ml-NN cases"
    for base in bases:
        en = by_id[f"{base}-en"]
        pt = by_id[f"{base}-pt"]
        assert _signature(en.recorded_output()) == _signature(pt.recorded_output())


def test_multilingual_low_confidence_cases_refuse_with_clarification() -> None:
    corpus = _load_multilingual()
    results = {r.case_id: r for r in run_translation_corpus(corpus).results}
    low_confidence = [r for cid, r in results.items() if cid.startswith("ml-lc")]
    assert low_confidence, "spike must include low-confidence Portuguese cases"
    for result in low_confidence:
        assert result.outcome == "refused"
        assert result.refusal_code == "NLR-CROSS-LANGUAGE-UNCERTAIN"


def test_cli_benchmark_translation_run_release_bar_on_multilingual_is_green(tmp_path) -> None:
    out = tmp_path / "ml-release-bar.json"
    exit_code = main(
        [
            "benchmark-translation",
            "--corpus",
            str(MULTILINGUAL_CORPUS),
            "--run",
            "--release-bar",
            "--per-domain-false-acceptance-budget",
            "0",
            "--out",
            str(out),
        ]
    )
    assert exit_code == 0


def test_multilingual_corpus_round_trips_through_the_generator() -> None:
    import json
    import sys

    sys.path.insert(0, str(MULTILINGUAL_CORPUS.parent))
    try:
        import build_corpus  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    expected = json.loads(
        json.dumps(build_corpus.build_multilingual_corpus().model_dump(mode="json"), sort_keys=True)
    )
    actual = json.loads(MULTILINGUAL_CORPUS.read_text())
    assert actual == expected, "multilingual.corpus.json is stale; rerun build_corpus.py"


def _signature(controlled: str) -> str:
    ir = DslV3Parser().parse_ir(controlled, requirement_id="REQ-SIG", title="t")
    return formal_claim_signature(
        build_formal_claim(ir).formal_claim, alpha_identifiers=False, commutative=True
    )
