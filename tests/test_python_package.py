import shutil
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
        "generated-tests.json",
        "counterexamples.json",
        "normalized-traces.json",
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


def test_build_python_package_records_generated_property_evidence(tmp_path: Path) -> None:
    out = tmp_path / "REQ-PY-PROP-001"
    adapter = _adapter(property_checks=True)

    build_python_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-PY-PROP-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
        adapter=adapter,
    )

    _ir, evidence, status = validate_python_package(out, adapter)

    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE
    assert [claim.id for claim in evidence.claims] == [
        "C-static",
        "C-consistency",
        "C-smt",
        "PY-SYMBOLS",
        "PY-PROPERTY",
        "PYTEST",
    ]
    property_claim = next(claim for claim in evidence.claims if claim.id == "PY-PROPERTY")
    assert property_claim.required_evidence == EvidenceLevel.TEST_VALIDATED
    assert property_claim.achieved_evidence == EvidenceLevel.TEST_VALIDATED
    assert property_claim.backend_results[0].details["coverage"]["threshold_met"] is True
    generated_tests = read_json(out / "generated-tests.json")
    assert generated_tests[0]["task_id"] == "PY-PROPERTY"
    assert "from samplepkg.core import operation" in generated_tests[0]["content"]
    assert read_json(out / "counterexamples.json") == []
    assert read_json(out / "normalized-traces.json") == []


def test_build_python_package_records_property_counterexample_artifact(tmp_path: Path) -> None:
    package = tmp_path / "badpkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text(
        "def operation() -> bool:\n"
        "    return False\n\n"
        "def actor() -> str:\n"
        "    return 'fixture-actor'\n"
    )
    out = tmp_path / "REQ-PY-PROP-FAIL-001"
    adapter = _adapter(
        package_root=package,
        package_name="badpkg",
        property_checks=True,
        test_paths=[],
    )

    build_python_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-PY-PROP-FAIL-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
        adapter=adapter,
    )

    _ir, evidence, status = validate_python_package(out, adapter)

    assert status.status == FinalStatus.REFUSED_FAILED_CHECK
    property_claim = next(claim for claim in evidence.claims if claim.id == "PY-PROPERTY")
    assert property_claim.achieved_evidence is None
    counterexamples = read_json(out / "counterexamples.json")
    assert counterexamples[0]["expected"] is True
    assert counterexamples[0]["actual"] is False


def test_validate_python_package_rejects_stale_source_hash(tmp_path: Path) -> None:
    package = tmp_path / "copypkg"
    shutil.copytree(FIXTURE_PACKAGE, package)
    out = tmp_path / "REQ-PY-SOURCE-STALE-001"
    adapter = _adapter(package_root=package, package_name="copypkg", property_checks=True)
    build_python_package(
        controlled_text=(
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        output_dir=out,
        requirement_id="REQ-PY-SOURCE-STALE-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
        adapter=adapter,
    )
    (package / "core.py").write_text(
        "def operation() -> bool:\n"
        "    return True\n\n"
        "def actor() -> str:\n"
        "    return 'changed-actor'\n\n"
        "def state_change() -> str:\n"
        "    return 'changed'\n"
    )

    with pytest.raises(ValueError, match="Python source hashes"):
        validate_python_package(out, adapter)


def _adapter(
    *,
    package_root: Path = FIXTURE_PACKAGE,
    package_name: str = "samplepkg",
    property_checks: bool = False,
    test_paths: list[Path] | None = None,
) -> PythonPackageAdapter:
    return PythonPackageAdapter(
        package_root,
        package_name=package_name,
        project_root=REPO_ROOT,
        test_paths=[TEST_PATH] if test_paths is None else test_paths,
        property_checks=property_checks,
    )
