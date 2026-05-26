from pathlib import Path

import pytest
from pydantic import ValidationError

from nlreq.jsonutil import write_json
from nlreq.models import FinalStatus
from nlreq.package import build_package, validate_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


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
    }
    assert expected.issubset({path.name for path in out.iterdir()})

    ir, evidence, status = validate_package(out)
    assert ir.requirement_id == "REQ-AUTH-001"
    assert evidence.unbound_symbols == []
    assert status.status == FinalStatus.ACCEPTED_WITH_EVIDENCE


def test_package_is_byte_stable(tmp_path: Path) -> None:
    text = (FIXTURES / "numeric_invariant.nlreq").read_text()
    first = tmp_path / "first"
    second = tmp_path / "second"

    kwargs = {
        "controlled_text": text,
        "requirement_id": "REQ-NUM-001",
        "title": "Counter increments within limit",
        "claim_kind": "numeric_invariant",
    }
    build_package(output_dir=first, **kwargs)
    build_package(output_dir=second, **kwargs)

    for first_file in sorted(path for path in first.rglob("*") if path.is_file()):
        rel = first_file.relative_to(first)
        assert first_file.read_bytes() == (second / rel).read_bytes()


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
