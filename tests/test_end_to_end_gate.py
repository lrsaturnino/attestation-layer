import json
import sys
from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v3 import DslV3Parser
from nlreq.end_to_end_gate import build_proof_with_formal_claim_dispatch, run_end_to_end_requirement_gate
from nlreq.formal_backend import FormalBackendExecution
from nlreq.jsonutil import read_json
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.system_spec import SystemSpecRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


DSL = (
    "For every redemption:\n"
    "when wallet is authorized\n"
    "and requested_amount <= spendable_balance\n"
    "then finalize_redemption must emit redemption_finalized within 6 hours.\n"
)


def test_end_to_end_gate_accepts_closed_requirement(tmp_path: Path) -> None:
    manifest, registry = _project(tmp_path)

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-001",
        title="Requirement gate",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert report.decision == "accepted"
    assert report.downstream_action_allowed is True
    assert report.statuses["closure_gate"] == "passed"
    assert {artifact.name for artifact in report.artifacts} >= {
        "requirement_ir",
        "translation_agreement",
        "requirement_self_consistency",
        "source_impact",
        "spec_coverage",
        "trace_replay",
        "system_consistency",
        "delta_report",
        "proof_object",
        "closure_gate",
    }
    assert all(Path(artifact.path).is_file() for artifact in report.artifacts)


def test_build_proof_with_formal_claim_dispatch_uses_fragment_ids_for_classed_ir() -> None:
    """build_proof_with_formal_claim_dispatch must carry FormalClaim fragment IDs into the ProofObject.

    This tests the production entry point — not a manually-constructed dispatch plan — so the
    assertion that ProofObject.premises contain formal fragment IDs is not test-only wiring.
    With no backend results all premises are open; the test only verifies the IDs are present.
    """
    ir = DslV3Parser().parse_ir(
        FIXTURES.joinpath("authorization_precondition_v3.nlreq").read_text(),
        requirement_id="AUTH-FC-GATE",
        title="Authorization precondition (gate test)",
    )

    proof, formal_claim_report = build_proof_with_formal_claim_dispatch(
        requirement=ir,
        backend_results=[],
    )

    assert formal_claim_report.result == "lowered"
    assert formal_claim_report.formal_claim is not None
    premise_ids = {p.premise_id for p in proof.premises}
    for fragment in [*formal_claim_report.formal_claim.premises, *formal_claim_report.formal_claim.obligations]:
        assert fragment.fragment_id in premise_ids, (
            f"fragment {fragment.fragment_id} ({fragment.kind}) missing from ProofObject.premises"
        )
    # All premises open — no backend results were supplied
    assert all(p.status == "open" for p in proof.premises)


def test_end_to_end_gate_records_formal_claim_artifact(tmp_path: Path) -> None:
    """FormalClaim artifact must be recorded by the gate regardless of claim class support.

    DSL-v2 text without a supported requirement_class produces a 'refused' formal claim;
    the artifact is still recorded so downstream tooling can inspect why dispatch fell back
    to the default system-consistency plan.
    """
    manifest, registry = _project(tmp_path)

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-FC-001",
        title="Formal claim artifact test",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert "formal_claim_artifact" in {artifact.name for artifact in report.artifacts}
    assert "formal_claim" in report.statuses
    # DSL-v2 text has no requirement_class annotation — formal claim is refused,
    # gate falls back to default dispatch and remains accepted
    assert report.statuses["formal_claim"] == "refused"
    assert report.decision == "accepted"


def test_end_to_end_gate_refuses_trace_replay_violation(tmp_path: Path) -> None:
    manifest, registry = _project(tmp_path, trace_actions=["finalize_redemption"])

    report = run_end_to_end_requirement_gate(
        controlled_text=DSL,
        requirement_id="REQ-GATE-002",
        title="Requirement gate refusal",
        source_adapter=PythonSourceLanguageAdapter(project_root=tmp_path),
        source_manifest=manifest,
        symbols=["finalize_redemption"],
        registry=registry,
        project_root=tmp_path,
        artifact_dir=tmp_path / "gate-artifacts",
        execution=_execution(tmp_path),
    )

    assert report.decision == "refused"
    assert report.downstream_action_allowed is False
    assert any(blocker.stage == "trace_replay" for blocker in report.blockers)


def test_end_to_end_requirement_gate_cli_writes_report(tmp_path: Path, capsys) -> None:
    manifest, registry = _project(tmp_path)
    requirement_path = tmp_path / "requirement.nlreq2"
    manifest_path = tmp_path / "source-manifest.json"
    registry_path = tmp_path / "registry.json"
    out = tmp_path / "gate-report.json"
    requirement_path.write_text(DSL)
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))
    registry_path.write_text(json.dumps(registry.model_dump(mode="json"), indent=2))

    exit_code = main(
        [
            "requirement-gate",
            str(requirement_path),
            "--requirement-id",
            "REQ-GATE-003",
            "--title",
            "Requirement gate CLI",
            "--source-manifest",
            str(manifest_path),
            "--source-language",
            "python",
            "--symbol",
            "finalize_redemption",
            "--registry",
            str(registry_path),
            "--project-root",
            str(tmp_path),
            "--artifact-dir",
            str(tmp_path / "gate-artifacts"),
            "--out",
            str(out),
            "--checker-id",
            "custom",
            "--checker-command",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Requirement gate report:" in output
    assert read_json(out)["decision"] == "accepted"


def _project(
    tmp_path: Path,
    *,
    trace_actions: list[str] | None = None,
) -> tuple[SourceManifest, SystemSpecRegistry]:
    src = tmp_path / "src"
    specs = tmp_path / "specs"
    src.mkdir()
    specs.mkdir()
    (src / "redemption.py").write_text(
        "def finalize_redemption(wallet):\n"
        "    if wallet.authorized:\n"
        "        return 'redemption_finalized'\n"
        "    return 'rejected'\n"
    )
    (specs / "Redemption.tla").write_text("---- MODULE Redemption ----\n====\n")
    trace_path = tmp_path / "traces.json"
    trace_path.write_text(json.dumps(_trace_payload(trace_actions or [
        "finalize_redemption",
        "redemption_finalized",
    ])))
    manifest = SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "redemption",
                    "path": "src/redemption.py",
                    "symbols": ["finalize_redemption"],
                    "trace_sources": ["traces.json"],
                }
            ],
        }
    )
    registry = SystemSpecRegistry.model_validate(
        {
            "schema_version": "0.1",
            "specs": [
                {
                    "spec_id": "spec:redemption",
                    "module_ids": ["redemption"],
                    "formalism": "tla",
                    "path": "specs/Redemption.tla",
                    "version": "1",
                    "review_status": "reviewed",
                    "freshness": "fresh",
                }
            ],
        }
    )
    return manifest, registry


def _trace_payload(actions: list[str]) -> list[dict[str, object]]:
    return [
        {
            "trace_id": "TRACE-GATE-001",
            "adapter_id": "raw-python",
            "source_hash": "sha256:source",
            "events": [
                {
                    "event_id": f"evt-{index}",
                    "timestamp": f"2026-06-01T00:00:0{index}Z",
                    "action": action,
                    "post_state": (
                        {"collateral": 150, "reserve_floor": 100}
                        if action == "redemption_finalized"
                        else {}
                    ),
                }
                for index, action in enumerate(actions, start=1)
            ],
        }
    ]


def _execution(tmp_path: Path) -> FormalBackendExecution:
    return FormalBackendExecution(
        checker_id="custom",
        command=[sys.executable, "-c", "print('verification successful')"],
        artifact_dir=(tmp_path / "formal-self-check").as_posix(),
    )
