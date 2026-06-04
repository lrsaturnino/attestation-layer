# Retained `S ∧ R` benchmark corpus (Pillar B · PB-5)

This corpus retains real, replayable system-consistency (`S ∧ R`) runs: a reviewed
system spec `S` composed with a requirement `R` and checked by a real symbolic model
checker. It is the SP2-B evidence for Pillar B — *a requirement that contradicts a real
`S` invariant yields a retained, replayable counterexample that names the invariant* —
plus a retained instance of every other outcome class so the honesty surface (timeout,
unsupported, missing-tool never silently pass) is exercised, not just described.

## Layout

```
<corpus-id>/
  manifest.json              # the scenario: spec, requirement(s), bounds, command
  spec/<Spec>.tla            # the reviewed system spec S (its own Init/Next + invariant)
  counterexample/            # R contradicts an S invariant → real model-checker counterexample
    <Module>.tla / .cfg      #   the composed S ∧ R module the checker ran
    trace.json               #   the counterexample trace (golden; #meta stripped → byte-stable)
    run.json                 #   sanitized run record: version, command, bounds, hashes
    stdout.txt               #   checker stdout tail (evidence snapshot; not byte-diffed)
  valid/                     # the compatible sibling → real model-checker 'valid'
  timeout/                   # a per-requirement budget is exhausted → 'timeout' (non-approving)
  missing-tool/              # the checker binary is absent → 'tool_error' (never a silent 'valid')
  unsupported/               # a relevant S declares no invariant → composition refuses
```

## The composition is a narrowing, not a product (PB-1)

`S` brings its own transition system (`SInit`/`SNext` over `authPhase`). The composed
module uses **`S`'s own `Init`/`Next` as the only state machine** and conjoins `R`'s
obligation as a state invariant `R_Requirement == Premise => ~Pred_<action>(subject)`.
`R` contributes no transitions and no harness variable. A counterexample is therefore a
real `S` behaviour walking `S`'s transition relation into the forbidden outcome
(`authPhase: init → denied → finalized`), not an artifact of a requirement harness
stepping its own state. See `counterexample/trace.json`.

## Replaying

`tests/test_benchmark_s_and_r_replay.py` replays this corpus:

- **counterexample / valid** re-run the *retained command* on the *committed* composed
  module through a real `apalache-mc` and diff the normalized trace against the golden.
  These skip with a recorded reason when `apalache-mc` is not installed (they never
  silently pass). Install the pinned checker with `scripts/install_formal_backends.sh`.
- **timeout / missing-tool / unsupported** are tool-free and reproduce deterministically
  on any machine from the committed spec + manifest.

## Regenerating

```
uv run python scripts/generate_s_and_r_benchmarks.py
```

Requires `apalache-mc` on `PATH` to (re)produce the `valid` / `counterexample` artifacts.
Every committed artifact is sanitized of machine-specific absolute paths; the replay test
fails the build if any reappear.
