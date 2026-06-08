# Translation corpus (PA-9)

A labeled corpus that measures the **LLM front-half** of requirement intake — PA-4
controlled-rewrite drafting plus PA-5 semantic translation — across two unrelated
domains, reporting **false-acceptance** and **false-refusal** separately.

## What this measures (and what it does not)

Each case is a `(prose, approved-controlled, gold-IR)` triple:

| Field | Meaning |
|---|---|
| `input_text` | the free-form prose a requirement author submitted |
| `gold_controlled_text` | the human-approved controlled rewrite; the **gold IR** (and the gold `FormalClaim` signature scored against) is the deterministic DSL v3 parse of this text — there is no separate gold-IR file to drift |
| `recorded_controlled_text` | the controlled text a recorded model run produced, replayed verbatim through `RecordedLlmClient` |

The harness (`translation_benchmark.run_translation_corpus`) runs each case
`prose → draft (RecordedLlmClient) → translate → FormalClaim` and scores it:

- **false-acceptance** — the pipeline accepted a claim it should not have: either the
  gold outcome was a refusal, or the accepted claim's signature diverges from the gold
  claim (wrong claim class, inverted premise polarity, invented premise). Equality uses
  the alpha-/commutative-normalised `formal_claim_signature`, so cosmetic id/title/order
  differences are **not** counted as divergence.
- **false-refusal** — the pipeline refused (or needs-review) a claim the gold says should
  have been accepted.

Both rates are always reported per domain; they are never collapsed into a single
"accuracy" (they trade off and must be read independently).

> **This is not an empirical LLM error rate.** Because `RecordedLlmClient` replays fixed,
> recorded outputs, the corpus measures the **pipeline gate's quality over those recorded
> outputs**, deterministically and offline. Measuring the live model's error rate is a
> separate, budgeted live-LLM suite that is out of scope here.

## The release bar

`corpus.json` is the committed release bar: every case's recorded output is the faithful
approved rewrite (or a genuinely un-lowerable refusal case), so a correct pipeline yields
**false-acceptance = 0** and **false-refusal = 0** in every domain. The CI gate
(`tests/test_translation_corpus.py`, run under `uv run pytest`) fails if either rate
regresses past its declared budget — overall or in any single domain.

The tests also plant a wrong-but-parseable output (→ false-acceptance) and a garbled
output (→ false-refusal) to prove the instrument actually discriminates, so the zeros on
the release corpus are a real signal rather than a constant.

## Multilingual slice (PA-11)

`multilingual.corpus.json` is the EN/PT spike: 20 requirements authored in **both**
English and Portuguese, each pair sharing one language-neutral controlled rewrite, plus a
few low-confidence Portuguese cases. The report breaks both rates down **per language**
(`languages`) as well as per domain.

- **EN↔PT signature equivalence** — because the controlled DSL normalises to snake_case
  symbols, an English requirement and its Portuguese twin lower to `FormalClaim`s with
  identical alpha-/commutative-normalised signatures. Merchant names and identifiers stay
  **verbatim** in the original language (preserved in the intake provenance and inside
  quoted DSL string literals).
- **Low-confidence refuses, never guesses** — a Portuguese fragment the drafter cannot
  confidently map to the grammar produces `NLR-CROSS-LANGUAGE-UNCERTAIN` with a
  clarification and the offending fragment localized, instead of a guessed rewrite.
- **NL-agnostic claim is scoped to the data** — "NL-agnostic" is asserted for a language
  only when its recorded false-acceptance/false-refusal match the English budget. On this
  spike Portuguese matches English (both zero), so the claim holds for Portuguese.

Source language is recorded as `source_language` in the proposal's producer provenance
(threaded from the intake's `language`).

## Reproducing

```bash
# Regenerate corpus.json + multilingual.corpus.json from source (round-trip tested):
uv run python benchmarks/translation-corpus/build_corpus.py

# Per-domain report + release-bar gate, computed offline from the corpus:
uv run nlreq benchmark-translation \
  --corpus benchmarks/translation-corpus/corpus.json \
  --run --release-bar --per-domain-false-acceptance-budget 0

# Per-language EN/PT spike:
uv run nlreq benchmark-translation \
  --corpus benchmarks/translation-corpus/multilingual.corpus.json \
  --run --release-bar --per-domain-false-acceptance-budget 0
```
