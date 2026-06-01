from pathlib import Path

from nlreq.cli import main
from nlreq.dsl_v2 import DslV2Parser
from nlreq.jsonutil import read_json
from nlreq.models import BackendResult, RequirementIRV2
from nlreq.verification_budget import (
    AbstractionAssumption,
    build_verification_budget_report,
    classify_budgeted_outcome,
)


FIXTURES = Path(__file__).parent / "fixtures" / "requirements"


def test_verification_budget_records_bounds_and_reviewed_assumptions() -> None:
    report = build_verification_budget_report(
        _ir(),
        requirement_class="system_compatibility",
        assumptions=[
            AbstractionAssumption(
                assumption_id="A1",
                scope="wallet",
                statement="wallet set is finite",
                reviewed=True,
            )
        ],
    )

    assert report.result == "ready"
    assert report.budget.timeout_seconds == 180
    assert report.budget.max_depth == 25
    assert report.budget.abstraction_level == "compositional"
    assert report.assumptions_hash is not None


def test_verification_budget_blocks_unreviewed_assumptions() -> None:
    report = build_verification_budget_report(
        _ir(),
        requirement_class="safety",
        assumptions=[
            AbstractionAssumption(
                assumption_id="A1",
                scope="auth",
                statement="only two actors exist",
            )
        ],
    )

    assert report.result == "needs_review"
    assert report.blockers == ["assumption A1 requires review"]


def test_budgeted_outcome_distinguishes_timeout_unknown_and_valid() -> None:
    budget = build_verification_budget_report(_ir(), requirement_class="safety")

    valid = classify_budgeted_outcome(
        requirement_id="REQ-BUDGET-001",
        budget_report=budget,
        backend_result=BackendResult(backend="tla-runner", status="valid"),
    )
    timeout = classify_budgeted_outcome(
        requirement_id="REQ-BUDGET-001",
        budget_report=budget,
        backend_result=BackendResult(backend="tla-runner", status="timeout"),
    )
    unknown = classify_budgeted_outcome(
        requirement_id="REQ-BUDGET-001",
        budget_report=budget,
        backend_result=BackendResult(backend="tla-runner", status="invalid"),
    )

    assert valid.outcome == "valid"
    assert valid.approving is True
    assert timeout.outcome == "timeout"
    assert timeout.approving is False
    assert unknown.outcome == "unknown"


def test_verification_budget_cli_writes_report(tmp_path: Path, capsys) -> None:
    ir_path = tmp_path / "requirement.ir.json"
    out = tmp_path / "budget.json"
    ir_path.write_text(_ir().model_dump_json())

    exit_code = main(
        [
            "verification-budget",
            "--requirement-ir",
            str(ir_path),
            "--requirement-class",
            "safety",
            "--assumption",
            "A1:auth:finite actors:reviewed",
            "--out",
            str(out),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Verification budget report:" in output
    assert read_json(out)["result"] == "ready"


def _ir() -> RequirementIRV2:
    return DslV2Parser().parse_ir(
        (FIXTURES / "dsl_v2_redemption.nlreq2").read_text(),
        requirement_id="REQ-BUDGET-001",
        title="Verification budget",
    )
