"""PC-12 release path — staleness clears ONLY through trace re-validation, never a hash rebuild.

The block half (editing a covered module marks S stale and S ∧ R refuses) is proven in
test_spec_freshness_blocks_s_and_r.py. This file proves the RELEASE half and its bypasses:

- the positive path: a stale covered module becomes fresh — and S ∧ R runs again — only after
  `revalidate_spec_freshness` re-runs the PC-11 spec↔trace replay over the module's current real
  traces and every reviewed spec classifies ``satisfies``;
- the negative paths: a blind v2 lockfile rebuild stays blocked (``unvalidated``), grafting the old
  validation artifacts onto rebuilt hashes stays blocked (the record binds the OLD source hashes),
  a violating or no-coverage replay refuses to rebaseline anything, unprovenanced traces cannot
  revalidate, and the verifier RE-RUNS the replay rather than trusting a recorded verdict.

The traces are the committed demo's recorded REAL Foundry artifact (requirements/spec-freshness/
traces.json — produced by a genuine `forge test` run, with source-bound producer provenance), so
these tests run offline without forge while every "satisfies" below is against real tool output.
"""

import hashlib
import json
import shutil
from pathlib import Path

from nlreq.dsl_v2 import DslV2Parser
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.jsonutil import sha256_json, write_json
from nlreq.models import NormalizedTraceArtifact
from nlreq.spec_drift import CodeSpecManifest, build_spec_drift_report, mark_stale_specs
from nlreq.spec_freshness import (
    SpecFreshnessLockEntryV2,
    SpecFreshnessLockfileV2,
    SpecRevalidationModuleResult,
    SpecRevalidationRecord,
    SpecRevalidationSpecResult,
    build_spec_freshness_lockfile_v2,
    revalidate_spec_freshness,
    verify_spec_freshness_validation,
)
from nlreq.system_checker import check_system_consistency_fixture
from nlreq.system_spec import SpecTraceContract, SpecTraceExpectation, SystemSpecRegistry
from nlreq.translator import lower_ir_v2_to_tla


DEMO = Path(__file__).resolve().parents[1] / "requirements" / "spec-freshness"

DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)

SPEC_TLA = (
    "---- MODULE Vault ----\n"
    "\\* Reviewed system spec S for the covered vault module.\n"
    "EXTENDS Naturals\n"
    "VARIABLE total\n\n"
    "TotalNonNegative == total >= 0\n\n"
    "====\n"
)

CLEAN_SOURCE = "contract Vault { uint256 public total; }\n"
EDITED_SOURCE = "contract Vault { uint256 public total; uint256 public fee; }\n"


def _ir():
    return DslV2Parser().parse_ir(DSL, requirement_id="REQ-RELEASE-001", title="release")


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact(
        adapter_id="solidity-source",
        language="solidity",
        input_symbols=["requestRedemption"],
        affected_modules=["vault"],
    )


def _real_traces() -> NormalizedTraceArtifact:
    """The committed demo's recorded REAL Foundry traces (producer-provenanced forge output)."""
    return NormalizedTraceArtifact.model_validate_json((DEMO / "traces.json").read_text())


def _satisfying_contract() -> SpecTraceContract:
    """The reviewed spec's declared projection, reproduced by the recorded real traces."""
    return SpecTraceContract.model_validate_json((DEMO / "contract.json").read_text())


def _paper_contract(value: str = "999") -> SpecTraceContract:
    """A paper-system projection: total() never reaches ``value`` in the real traces."""
    return SpecTraceContract(
        spec_id="spec:vault",
        module_ids=["vault"],
        expectations=[
            SpecTraceExpectation(
                expectation_id="paper-total",
                kind="state_value_reached",
                target="total",
                value=value,
            )
        ],
    )


def _uncovered_contract() -> SpecTraceContract:
    """A projection the real traces never witness (no Settled event is ever emitted)."""
    return SpecTraceContract(
        spec_id="spec:vault",
        module_ids=["vault"],
        expectations=[
            SpecTraceExpectation(
                expectation_id="uncovered-settled", kind="event_emitted", target="Settled"
            )
        ],
    )


def _setup(tmp_path: Path) -> tuple[CodeSpecManifest, SystemSpecRegistry, SpecFreshnessLockfileV2]:
    """A tmp project with one covered source, one reviewed spec, the recorded real traces, and a
    freshness baseline produced by a REAL revalidate run over the clean tree (so the lockfile's
    validation binding is the genuine release-flow output, not hand-assembled)."""
    (tmp_path / "vault.sol").write_text(CLEAN_SOURCE)
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "Vault.tla").write_text(SPEC_TLA)
    shutil.copy(DEMO / "traces.json", tmp_path / "traces.json")
    write_json(tmp_path / "contract.json", _satisfying_contract())
    manifest = CodeSpecManifest.model_validate(
        {
            "schema_version": "0.1",
            "entries": [
                {
                    "module_id": "vault",
                    "source_paths": ["vault.sol"],
                    "spec_ids": ["spec:vault"],
                    "recorded_source_hashes": {},
                }
            ],
        }
    )
    registry = SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:vault",
                    "module_ids": ["vault"],
                    "formalism": "tla",
                    "path": "specs/Vault.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                    "recorded_hash": None,
                    "invariants": ["TotalNonNegative"],
                }
            ],
        }
    )
    empty_lockfile = SpecFreshnessLockfileV2(lock_id="release-test", entries=[])
    baseline = revalidate_spec_freshness(
        manifest=manifest,
        registry=registry,
        lockfile=empty_lockfile,
        project_root=tmp_path,
        contracts=[_satisfying_contract()],
        contract_paths={"spec:vault": "contract.json"},
        traces=_real_traces(),
        traces_path="traces.json",
        record_path="revalidation.json",
        validated_at="2026-06-09T00:00:00Z",
    )
    assert baseline.result == "revalidated"
    write_json(tmp_path / "revalidation.json", baseline.record)
    assert baseline.updated_manifest is not None
    assert baseline.updated_lockfile is not None
    return baseline.updated_manifest, registry, baseline.updated_lockfile


def _revalidate(
    manifest: CodeSpecManifest,
    registry: SystemSpecRegistry,
    lockfile: SpecFreshnessLockfileV2,
    tmp_path: Path,
    contract: SpecTraceContract,
    traces: NormalizedTraceArtifact,
):
    write_json(tmp_path / "contract.json", contract)
    return revalidate_spec_freshness(
        manifest=manifest,
        registry=registry,
        lockfile=lockfile,
        project_root=tmp_path,
        contracts=[contract],
        contract_paths={contract.spec_id: "contract.json"},
        traces=traces,
        traces_path="traces.json",
        record_path="revalidation.json",
        validated_at="2026-06-09T01:00:00Z",
    )


def test_release_path_clears_staleness_and_unblocks_s_and_r(tmp_path: Path) -> None:
    """The DoD's release half end-to-end: edit covered source → S stale → S ∧ R refuses; re-validate
    against the real traces → satisfies → baseline rebuilt, freshness released → S ∧ R runs again."""
    manifest, registry, lockfile = _setup(tmp_path)

    (tmp_path / "vault.sol").write_text(EDITED_SOURCE)
    drift = build_spec_drift_report(manifest, project_root=tmp_path)
    assert drift.result == "blocked"
    stale_registry = mark_stale_specs(registry, drift)
    assert stale_registry.specs[0].freshness == "stale"
    blocked = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir(), legacy_skeleton=True),
        registry=stale_registry,
        impact=_impact(),
        project_root=tmp_path,
    )
    assert blocked.result.status == "unsupported"

    release = _revalidate(
        manifest, stale_registry, lockfile, tmp_path, _satisfying_contract(), _real_traces()
    )
    assert release.result == "revalidated"
    assert release.record.results[0].spec_results[0].classification == "satisfies"
    write_json(tmp_path / "revalidation.json", release.record)
    assert release.updated_manifest is not None
    assert release.updated_registry is not None
    assert release.updated_lockfile is not None

    # The released registry is fresh again and the rebaselined manifest reports no drift, so the
    # stale flag cannot immediately re-assert itself.
    assert release.updated_registry.specs[0].freshness == "fresh"
    drift_after = build_spec_drift_report(release.updated_manifest, project_root=tmp_path)
    assert drift_after.result == "passed"
    refreshed = mark_stale_specs(release.updated_registry, drift_after)
    valid = check_system_consistency_fixture(
        requirement=_ir(),
        lowered=lower_ir_v2_to_tla(_ir(), legacy_skeleton=True),
        registry=refreshed,
        impact=_impact(),
        project_root=tmp_path,
    )
    assert valid.result.status == "valid"

    # And the validation-aware gate verifies the released baseline end-to-end (hash binding,
    # provenance, re-run replay).
    verification = verify_spec_freshness_validation(
        manifest=release.updated_manifest,
        registry=release.updated_registry,
        lockfile=release.updated_lockfile,
        project_root=tmp_path,
    )
    assert verification.result == "passed"
    assert verification.statuses[0].status == "fresh"
    assert "revalidation.json" in verification.statuses[0].validation_artifacts


def test_blind_lockfile_rebaseline_stays_blocked(tmp_path: Path) -> None:
    """Rebuilding the v2 lockfile over the edited tree — without any trace re-validation — does NOT
    clear the block: the rebuilt entry carries no binding revalidation record (`unvalidated`)."""
    manifest, registry, _lockfile = _setup(tmp_path)
    (tmp_path / "vault.sol").write_text(EDITED_SOURCE)

    blind = build_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        project_root=tmp_path,
        lock_id="release-test",
        validated_at="2026-06-09T02:00:00Z",
    )

    report = verify_spec_freshness_validation(
        manifest=manifest, registry=registry, lockfile=blind, project_root=tmp_path
    )
    assert report.result == "blocked"
    assert report.statuses[0].status == "unvalidated"
    assert "no validation artifacts" in (report.statuses[0].reason or "")


def test_grafting_old_validation_onto_rebuilt_hashes_stays_blocked(tmp_path: Path) -> None:
    """The stronger forgery: rebuild the lockfile over the edited tree AND graft the old (genuine)
    validation artifacts onto it. The record binds the OLD source hashes, so it cannot vouch for the
    edited source and the module verifies as `unvalidated`."""
    manifest, registry, lockfile = _setup(tmp_path)
    (tmp_path / "vault.sol").write_text(EDITED_SOURCE)

    blind = build_spec_freshness_lockfile_v2(
        manifest=manifest,
        registry=registry,
        project_root=tmp_path,
        lock_id="release-test",
        validated_at=lockfile.entries[0].validated_at,
    )
    grafted = blind.model_copy(
        update={
            "entries": [
                blind.entries[0].model_copy(
                    update={
                        "validation_artifact_hashes": dict(
                            lockfile.entries[0].validation_artifact_hashes
                        )
                    }
                )
            ]
        }
    )

    report = verify_spec_freshness_validation(
        manifest=manifest, registry=registry, lockfile=grafted, project_root=tmp_path
    )
    assert report.result == "blocked"
    assert report.statuses[0].status == "unvalidated"
    assert "does not bind the locked source hashes" in (report.statuses[0].reason or "")


def test_violating_replay_refuses_to_rebaseline(tmp_path: Path) -> None:
    """A spec the current traces actively contradict (total never reaches 999) is NOT released: the
    run is rejected with the populated classification and no baseline artifact is produced."""
    manifest, registry, lockfile = _setup(tmp_path)
    (tmp_path / "vault.sol").write_text(EDITED_SOURCE)

    rejected = _revalidate(
        manifest, registry, lockfile, tmp_path, _paper_contract(), _real_traces()
    )

    assert rejected.result == "rejected"
    spec_result = rejected.record.results[0].spec_results[0]
    assert spec_result.classification == "violates_with_delta"
    assert any("do not reproduce" in reason for reason in spec_result.reasons)
    assert rejected.updated_manifest is None
    assert rejected.updated_registry is None
    assert rejected.updated_lockfile is None


def test_no_coverage_replay_refuses_to_rebaseline(tmp_path: Path) -> None:
    """A spec obligation the current traces never witness (no Settled event) cannot release the
    module either — no-coverage is not evidence the spec reproduces the code."""
    manifest, registry, lockfile = _setup(tmp_path)

    rejected = _revalidate(
        manifest, registry, lockfile, tmp_path, _uncovered_contract(), _real_traces()
    )

    assert rejected.result == "rejected"
    assert rejected.record.results[0].spec_results[0].classification == "no_coverage"
    assert rejected.updated_lockfile is None


def test_unprovenanced_traces_cannot_revalidate(tmp_path: Path) -> None:
    """Traces without source-bound real-tool provenance (e.g. hand-written JSON) cannot clear
    staleness, even if they nominally reproduce the contract — the evidence floor is a real tool."""
    manifest, registry, lockfile = _setup(tmp_path)
    stripped = NormalizedTraceArtifact.model_validate(
        [
            trace.model_copy(update={"producer": None})
            for trace in _real_traces().root
        ]
    )
    write_json(tmp_path / "traces.json", stripped)

    rejected = _revalidate(manifest, registry, lockfile, tmp_path, _satisfying_contract(), stripped)

    assert rejected.result == "rejected"
    assert any(
        "real-tool provenance" in reason for reason in rejected.record.results[0].reasons
    )
    assert rejected.updated_lockfile is None


def test_draft_spec_cannot_be_revalidated(tmp_path: Path) -> None:
    """Only a REVIEWED spec can anchor a release: a draft spec covering the module rejects the run
    (revalidation is not a side door around the human review gate)."""
    manifest, registry, lockfile = _setup(tmp_path)
    draft_registry = registry.model_copy(
        update={"specs": [registry.specs[0].model_copy(update={"review_status": "draft"})]}
    )

    rejected = _revalidate(
        manifest, draft_registry, lockfile, tmp_path, _satisfying_contract(), _real_traces()
    )

    assert rejected.result == "rejected"
    assert any(
        "not reviewed" in reason
        for reason in rejected.record.results[0].spec_results[0].reasons
    )


def test_verifier_reruns_replay_instead_of_trusting_recorded_verdict(tmp_path: Path) -> None:
    """A hand-assembled, hash-consistent baseline whose record CLAIMS `satisfies` over a contract
    the traces actually contradict is still blocked: the verifier re-runs the replay itself."""
    manifest, registry, _lockfile = _setup(tmp_path)
    paper = _paper_contract()
    write_json(tmp_path / "contract.json", paper)
    def _file_hash(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    source_hash = _file_hash(tmp_path / "vault.sol")
    spec_hash = _file_hash(tmp_path / "specs" / "Vault.tla")
    traces_hash = _file_hash(tmp_path / "traces.json")
    contract_hash = _file_hash(tmp_path / "contract.json")
    record = SpecRevalidationRecord(
        lock_id="release-test",
        validated_at="2026-06-09T03:00:00Z",
        traces_path="traces.json",
        traces_hash=traces_hash,
        results=[
            SpecRevalidationModuleResult(
                module_id="vault",
                outcome="revalidated",
                source_hashes={"vault.sol": source_hash},
                spec_results=[
                    SpecRevalidationSpecResult(
                        spec_id="spec:vault",
                        classification="satisfies",
                        spec_hash=spec_hash,
                        contract_path="contract.json",
                        contract_hash=contract_hash,
                    )
                ],
            )
        ],
    )
    write_json(tmp_path / "revalidation.json", record)
    forged = SpecFreshnessLockfileV2(
        lock_id="release-test",
        entries=[
            SpecFreshnessLockEntryV2(
                module_id="vault",
                source_hashes={"vault.sol": source_hash},
                spec_hashes={"spec:vault": spec_hash},
                manifest_entry_hash=sha256_json(manifest.entries[0]),
                validated_at="2026-06-09T03:00:00Z",
                validation_artifact_hashes={
                    "revalidation.json": sha256_json(record),
                    "traces.json": traces_hash,
                    "contract.json": contract_hash,
                },
            )
        ],
    )

    report = verify_spec_freshness_validation(
        manifest=manifest, registry=registry, lockfile=forged, project_root=tmp_path
    )

    assert report.result == "blocked"
    assert report.statuses[0].status == "unvalidated"
    assert "do not reproduce" in (report.statuses[0].reason or "")


def test_revalidate_cli_release_and_refusal(tmp_path: Path) -> None:
    """The spec-revalidate CLI: a violating contract exits 1 and rewrites NOTHING; the satisfying
    contract exits 0 and rebuilds the baseline that spec-freshness-verify then accepts."""
    from nlreq.cli import main

    manifest, registry, lockfile = _setup(tmp_path)
    (tmp_path / "vault.sol").write_text(EDITED_SOURCE)
    write_json(tmp_path / "manifest.json", manifest)
    write_json(tmp_path / "registry.json", registry)
    write_json(tmp_path / "lockfile.json", lockfile)
    write_json(tmp_path / "paper-contract.json", _paper_contract())
    lockfile_before = (tmp_path / "lockfile.json").read_text()

    refused = main(
        [
            "spec-revalidate",
            "--manifest", str(tmp_path / "manifest.json"),
            "--registry", str(tmp_path / "registry.json"),
            "--lockfile", str(tmp_path / "lockfile.json"),
            "--project-root", str(tmp_path),
            "--contract", str(tmp_path / "paper-contract.json"),
            "--traces", str(tmp_path / "traces.json"),
            "--record-out", str(tmp_path / "revalidation.json"),
            "--lockfile-out", str(tmp_path / "lockfile.json"),
            "--manifest-out", str(tmp_path / "manifest.json"),
            "--out", str(tmp_path / "report.json"),
        ]
    )
    assert refused == 1
    assert (tmp_path / "lockfile.json").read_text() == lockfile_before
    assert json.loads((tmp_path / "report.json").read_text())["result"] == "rejected"

    released = main(
        [
            "spec-revalidate",
            "--manifest", str(tmp_path / "manifest.json"),
            "--registry", str(tmp_path / "registry.json"),
            "--lockfile", str(tmp_path / "lockfile.json"),
            "--project-root", str(tmp_path),
            "--contract", str(tmp_path / "contract.json"),
            "--traces", str(tmp_path / "traces.json"),
            "--record-out", str(tmp_path / "revalidation.json"),
            "--lockfile-out", str(tmp_path / "lockfile.json"),
            "--manifest-out", str(tmp_path / "manifest.json"),
            "--registry-out", str(tmp_path / "registry.json"),
        ]
    )
    assert released == 0

    verified = main(
        [
            "spec-freshness-verify",
            "--manifest", str(tmp_path / "manifest.json"),
            "--registry", str(tmp_path / "registry.json"),
            "--lockfile", str(tmp_path / "lockfile.json"),
            "--project-root", str(tmp_path),
            "--out", str(tmp_path / "verify.json"),
        ]
    )
    assert verified == 0
    assert json.loads((tmp_path / "verify.json").read_text())["result"] == "passed"


def test_recorded_demo_traces_carry_real_tool_provenance() -> None:
    """The committed demo evidence this whole file leans on is genuinely real-tool: every recorded
    trace passes the source-bound provenance gate (forge producer + raw_output hash binding)."""
    from nlreq.adapter_certification import trace_has_real_tool_provenance

    traces = _real_traces()
    assert traces.root
    assert all(trace_has_real_tool_provenance(trace) for trace in traces.root)
