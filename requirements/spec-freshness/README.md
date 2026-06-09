# Spec-freshness demo (PC-12): a covered module with a validated, releasable baseline

This directory is the self-contained config the CI `spec-freshness-verify` step gates on. It covers
one real Solidity module with one reviewed spec and the recorded evidence that the spec reproduces
the module's REAL Foundry traces:

- `foundry/` — the covered module: a hermetic Foundry project (`src/Vault.sol`, `src/Reverting.sol`)
  whose tests drive the trace. Editing either covered source without re-validating blocks CI.
- `specs/Vault.tla` — the reviewed spec S (hand-written per the PB-5 pattern).
- `contract.json` — S's declared trace-observable projection (a `SpecTraceContract`, PC-11).
- `traces.json` — the recorded `NormalizedTraceArtifact` from a real `forge test` run, carrying
  source-bound real-tool provenance (`producer` + `raw_output`).
- `revalidation.json` — the `SpecRevalidationRecord` of the last `spec-revalidate` run: which
  source/spec hashes were validated, against which traces, with what classification.
- `manifest.json` / `registry.json` / `lockfile.json` — the code↔spec manifest, the spec registry,
  and the freshness lockfile that hash-binds all of the above.

## What the gate enforces

`nlreq spec-freshness-verify` blocks when a covered source or spec hash drifts from the lockfile
(the Cargo.lock-style invariant), AND when a hash-fresh entry lacks verifiable revalidation
evidence: the record must bind the locked hashes and the lock id, the traces must carry real-tool
provenance, and the contract-vs-traces replay is re-run and must classify `satisfies`. Rebuilding
the lockfile blindly (`spec-freshness-lock-v2`) does NOT clear a block — the rebuilt entry carries
no binding revalidation record and verifies as `unvalidated`.

## Releasing a block after editing the covered module (the honest flow)

1. Re-extract the module's CURRENT real traces (requires `forge` on PATH):

   ```bash
   uv run python - <<'EOF'
   from pathlib import Path
   from nlreq.jsonutil import write_json
   from nlreq.production_source_adapters import SoliditySourceAdapter
   from nlreq.source_adapter import SourceManifest

   manifest = SourceManifest.model_validate({
       "schema_version": "0.1", "adapter": "solidity-source", "language": "solidity",
       "runtime": "evm",
       "modules": [{"module_id": "vault", "path": "src/Vault.sol",
                    "symbols": ["Vault", "requestRedemption", "Redeemed", "total"]}],
   })
   adapter = SoliditySourceAdapter(project_root=Path("requirements/spec-freshness/foundry"))
   write_json(Path("requirements/spec-freshness/traces.json"), adapter.extract_traces(manifest))
   EOF
   ```

2. Re-validate and rebuild the baseline — this refuses (exit 1, nothing rewritten) unless every
   declared obligation of the reviewed spec is reproduced by those traces:

   ```bash
   uv run nlreq spec-revalidate \
     --manifest requirements/spec-freshness/manifest.json \
     --registry requirements/spec-freshness/registry.json \
     --lockfile requirements/spec-freshness/lockfile.json \
     --project-root . \
     --contract requirements/spec-freshness/contract.json \
     --traces requirements/spec-freshness/traces.json \
     --record-out requirements/spec-freshness/revalidation.json \
     --manifest-out requirements/spec-freshness/manifest.json \
     --registry-out requirements/spec-freshness/registry.json \
     --lockfile-out requirements/spec-freshness/lockfile.json
   ```

3. Commit the regenerated `traces.json`, `revalidation.json`, `manifest.json`, and `lockfile.json`
   together with the source edit.

If the edit changed the module's behavior so the spec no longer reproduces it, step 2 fails with
the populated delta — fix the spec (re-review) or the code; the block is the system working.
