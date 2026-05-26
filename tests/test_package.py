from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.jsonutil import read_json, write_json
from nlreq.models import FinalStatus
from nlreq.package import build_package, validate_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"
GOLDENS = Path(__file__).parents[1] / "requirements"

PACKAGE_CASES = [
    pytest.param(
        "authorization_precondition.nlreq",
        "REQ-AUTH-001",
        "Unauthorized operation is rejected before state changes",
        "authorization_precondition",
        id="authorization_precondition",
    ),
    pytest.param(
        "state_postcondition.nlreq",
        "REQ-STATE-001",
        "Approved operation sets accepted status",
        "state_postcondition",
        id="state_postcondition",
    ),
    pytest.param(
        "numeric_invariant.nlreq",
        "REQ-NUM-001",
        "Counter increments within limit",
        "numeric_invariant",
        id="numeric_invariant",
    ),
    pytest.param(
        "unbound_symbol.nlreq",
        "REQ-REFUSED-UNBOUND-001",
        "Unbound operator example",
        "authorization_precondition",
        id="refused_unbound_symbol",
    ),
]


def test_build_package_outputs_required_files(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"

    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )

    expected = {
        "requirement.md",
        "source-diff.md",
        "requirement.ir.json",
        "bindings.json",
        "assumptions.json",
        "review.json",
        "verification-tasks.json",
        "evidence.json",
        "status.json",
        "implementation-spec.md",
        "smt",
    }
    assert expected.issubset({path.name for path in out.iterdir()})

    ir, evidence, status = validate_package(out)
    assert ir.requirement_id == "REQ-AUTH-001"
    assert evidence.unbound_symbols == []
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE


@pytest.mark.parametrize(
    ("fixture_name", "requirement_id", "title", "claim_kind"),
    PACKAGE_CASES,
)
def test_package_is_byte_stable(
    tmp_path: Path,
    fixture_name: str,
    requirement_id: str,
    title: str,
    claim_kind: str,
) -> None:
    text = (FIXTURES / fixture_name).read_text()
    first = tmp_path / "first"
    second = tmp_path / "second"

    kwargs = {
        "controlled_text": text,
        "requirement_id": requirement_id,
        "title": title,
        "claim_kind": claim_kind,
    }
    build_package(output_dir=first, **kwargs)
    build_package(output_dir=second, **kwargs)

    assert _relative_files(first) == _relative_files(second)
    _assert_same_bytes(first, second)


@pytest.mark.parametrize(
    ("fixture_name", "requirement_id", "title", "claim_kind"),
    PACKAGE_CASES,
)
def test_committed_example_package_is_golden(
    tmp_path: Path,
    fixture_name: str,
    requirement_id: str,
    title: str,
    claim_kind: str,
) -> None:
    generated = tmp_path / requirement_id

    build_package(
        controlled_text=(FIXTURES / fixture_name).read_text(),
        output_dir=generated,
        requirement_id=requirement_id,
        title=title,
        claim_kind=claim_kind,
    )

    golden = GOLDENS / requirement_id
    assert _relative_files(generated) == _relative_files(golden)
    _assert_same_bytes(generated, golden)


def test_refused_package_points_to_unbound_fragment(tmp_path: Path) -> None:
    out = tmp_path / "REQ-REFUSED-UNBOUND-001"

    build_package(
        controlled_text=(FIXTURES / "unbound_symbol.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-REFUSED-UNBOUND-001",
        title="Unbound operator example",
        claim_kind="authorization_precondition",
    )

    _ir, evidence, status = validate_package(out)

    assert evidence.unbound_symbols == ["operator"]
    assert status.status == FinalStatus.REFUSED_UNBOUND_SYMBOLS
    assert status.source_span is not None
    assert status.source_span.text == "operator is not authorized"


def test_ambiguous_package_is_refused_as_ambiguous(tmp_path: Path) -> None:
    out = tmp_path / "REQ-REFUSED-AMBIGUOUS-001"

    build_package(
        controlled_text=(
            "For every operation request:\n"
            "if ambiguous_actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        output_dir=out,
        requirement_id="REQ-REFUSED-AMBIGUOUS-001",
        title="Ambiguous actor example",
        claim_kind="authorization_precondition",
    )

    _ir, evidence, status = validate_package(out)

    assert evidence.ambiguous is True
    assert evidence.ambiguous_symbols == ["ambiguous_actor"]
    assert evidence.unbound_symbols == []
    assert status.status == FinalStatus.REFUSED_AMBIGUOUS
    assert status.source_span is not None
    assert status.source_span.text == "ambiguous_actor is not authorized"


def test_validate_package_rejects_invalid_auxiliary_artifact(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    write_json(out / "review.json", {"review_id": "RVW-INVALID"})

    with pytest.raises(ValidationError):
        validate_package(out)


def test_validate_package_rejects_stale_review_hash(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    review = read_json(out / "review.json")
    review["reviewed_hashes"]["requirement_ir"] = "sha256:stale"
    write_json(out / "review.json", review)

    with pytest.raises(ValueError, match="review.json requirement_ir hash"):
        validate_package(out)


def test_validate_package_rejects_stale_status(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    status = read_json(out / "status.json")
    status["status"] = "ACCEPTED_FOR_IMPLEMENTATION_WITH_REVIEW"
    status["reason"] = "stale"
    write_json(out / "status.json", status)

    with pytest.raises(ValueError, match="status.json does not match"):
        validate_package(out)


def test_validate_package_rejects_stale_verification_tasks(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    tasks = read_json(out / "verification-tasks.json")
    tasks[0]["input_hash"] = "sha256:stale"
    write_json(out / "verification-tasks.json", tasks)

    with pytest.raises(ValueError, match="verification-tasks.json"):
        validate_package(out)


def test_validate_package_rejects_stale_smt_file(tmp_path: Path) -> None:
    out = tmp_path / "REQ-AUTH-001"
    build_package(
        controlled_text=(FIXTURES / "authorization_precondition.nlreq").read_text(),
        output_dir=out,
        requirement_id="REQ-AUTH-001",
        title="Unauthorized operation is rejected before state changes",
        claim_kind="authorization_precondition",
    )
    (out / "smt" / "C1.smt2").write_text("; stale\n")

    with pytest.raises(ValueError, match="smt/C1.smt2"):
        validate_package(out)


def _relative_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


def _assert_same_bytes(first: Path, second: Path) -> None:
    for rel in _relative_files(first):
        assert (first / rel).read_bytes() == (second / rel).read_bytes(), str(rel)
