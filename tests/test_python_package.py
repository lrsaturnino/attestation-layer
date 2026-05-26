from pathlib import Path

import pytest

from nlreq.jsonutil import read_json, write_json
from nlreq.models import EvidenceLevel, FinalStatus
from nlreq.python_adapter import PythonPackageAdapter
from nlreq.python_package import build_python_package, validate_python_package


FIXTURE_PACKAGE = Path(__file__).parent / "fixtures" / "adapters" / "pythonpkg" / "samplepkg"
TEST_PATH = Path("tests/fixtures/adapters/pythonpkg")
REPO_ROOT = Path(__file__).parents[1]


def test_build_python_package_records_adapter_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-PY-001"
    adapter = _adapter()

    build_python_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-PY-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
        adapter=adapter,
    )

    expected = {
        "requirement.md",
        "source-diff.md",
        "requirement.ir.json",
        "bindings.json",
        "assumptions.json",
        "review.json",
        "verification-tasks.json",
        "adapter-results.json",
        "evidence.json",
        "status.json",
        "implementation-spec.md",
        "smt",
    }
    assert expected.issubset({path.name for path in out.iterdir()})

    ir, evidence, status = validate_python_package(out, adapter)
    assert ir.bindings["operation"].adapter == "python_package"
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "PY-SYMBOLS",
        "PYTEST",
    ]
    assert evidence.claims[-1].required_evidence == EvidenceLevel.TEST_VALIDATED
    assert evidence.claims[-1].achieved_evidence == EvidenceLevel.TEST_VALIDATED


def test_validate_python_package_rejects_stale_adapter_result(tmp_path: Path) -> None:
    out = tmp_path / "REQ-PY-STALE-001"
    adapter = _adapter()
    build_python_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-PY-STALE-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
        adapter=adapter,
    )
    results = read_json(out / "adapter-results.json")
    results[1]["details"]["task_input_hash"] = "sha256:stale"
    write_json(out / "adapter-results.json", results)

    with pytest.raises(ValueError, match="evidence.json does not match adapter-results.json"):
        validate_python_package(out, adapter)


def _adapter() -> PythonPackageAdapter:
    return PythonPackageAdapter(
        FIXTURE_PACKAGE,
        package_name="samplepkg",
        project_root=REPO_ROOT,
        test_paths=[TEST_PATH],
    )
