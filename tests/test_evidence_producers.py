from pathlib import Path

from nlreq.cli import main
from nlreq.evidence_producers import validate_real_evidence_producers
from nlreq.jsonutil import read_json
from nlreq.models import BackendResult, EvidenceLevel
from nlreq.proof_closure import (
    EvidenceProducer,
    EvidenceProducerMapping,
    default_evidence_producer_mapping,
)


def test_real_evidence_producer_validation_accepts_reproducible_bounded_result() -> None:
    report = validate_real_evidence_producers(
        [_bounded_result()],
        default_evidence_producer_mapping(),
    )

    assert report.result == "valid"
    assert report.statuses[0].status == "valid"


def test_real_evidence_producer_validation_blocks_forged_high_assurance() -> None:
    mapping = EvidenceProducerMapping(
        producers=[
            EvidenceProducer(
                producer_id="fake",
                producer_kind="formal_boundary",
                real_producer=False,
                allowed_evidence_levels=[EvidenceLevel.BOUNDED_CHECKED],
                tool="manual",
            )
        ]
    )
    result = BackendResult(
        backend="fake",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={"command": ["manual"], "input_hashes": {"model": "sha256:x"}},
    )

    report = validate_real_evidence_producers([result], mapping)

    assert report.result == "blocked"
    assert "high-assurance evidence requires a real producer" in report.statuses[0].reasons
    assert "tool version is missing" in report.statuses[0].reasons


def test_real_evidence_producer_validation_blocks_missing_reproducibility() -> None:
    result = BackendResult(
        backend="tla-runner",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={"tool_version": "tlc 1.0"},
    )

    report = validate_real_evidence_producers(
        [result],
        default_evidence_producer_mapping(),
    )

    assert report.result == "blocked"
    assert "command metadata is missing" in report.statuses[0].reasons
    assert "input/output or artifact hashes are missing" in report.statuses[0].reasons


def test_real_evidence_producer_validation_ignores_low_assurance_results() -> None:
    report = validate_real_evidence_producers(
        [
            BackendResult(
                backend="system_checker",
                status="valid",
                evidence_level=EvidenceLevel.CONSISTENCY_CHECKED,
            )
        ],
        default_evidence_producer_mapping(),
    )

    assert report.result == "valid"
    assert report.statuses[0].status == "not_applicable"


def test_evidence_producer_validation_cli_writes_report(tmp_path: Path, capsys) -> None:
    result_path = tmp_path / "backend-result.json"
    out = tmp_path / "producer-validation.json"
    result_path.write_text(_bounded_result().model_dump_json())

    exit_code = main(
        [
            "evidence-producers-validate",
            "--backend-result",
            str(result_path),
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Evidence producer validation report:" in output
    assert read_json(out)["result"] == "valid"


def _bounded_result() -> BackendResult:
    return BackendResult(
        backend="tla-runner",
        status="valid",
        evidence_level=EvidenceLevel.BOUNDED_CHECKED,
        details={
            "command": ["tlc2.TLC", "Model.tla"],
            "tool_version": "tlc 2.18",
            "bounds": {"max_depth": 10},
            "module_hash": "sha256:model",
            "config_hash": "sha256:config",
            "runner_result_hash": "sha256:runner",
        },
    )
