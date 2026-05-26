from pathlib import Path

from nlreq.cli import main
from nlreq.package import build_package


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_validate_all_reports_all_packages(capsys) -> None:
    exit_code = main(["validate-all", "requirements"])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Packages: 4 valid" in output
    assert "REQ-AUTH-001: ACCEPTED_WITH_EVIDENCE" in output
    assert "REQ-REFUSED-UNBOUND-001: REFUSED_UNBOUND_SYMBOLS" in output


def test_validate_all_rejects_empty_package_root(tmp_path: Path, capsys) -> None:
    exit_code = main(["validate-all", str(tmp_path)])

    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "no package directories found" in stderr


def test_validate_reports_ambiguous_bindings(tmp_path: Path, capsys) -> None:
    out = tmp_path / "REQ-AMBIGUOUS-001"
    build_package(
        controlled_text=(
            "For every operation request:\n"
            "if ambiguous_actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        output_dir=out,
        requirement_id="REQ-AMBIGUOUS-001",
        title="Ambiguous actor",
        claim_kind="authorization_precondition",
    )

    exit_code = main(["validate", str(out)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Bindings: ambiguous" in output
    assert "Status: REFUSED_AMBIGUOUS" in output
