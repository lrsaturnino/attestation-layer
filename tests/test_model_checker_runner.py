import json
import sys
from pathlib import Path

from nlreq.cli import main
from nlreq.model_checker_runner import (
    ModelCheckerBudget,
    ModelCheckerCommand,
    run_model_checker,
)


def test_model_checker_runner_records_valid_run_metadata(tmp_path: Path) -> None:
    request = ModelCheckerCommand(
        run_id="run-valid",
        checker_id="custom",
        command=[
            sys.executable,
            "-c",
            "print('Model checking completed. No error has been found.')",
        ],
        cwd=tmp_path.as_posix(),
        budget=ModelCheckerBudget(
            timeout_seconds=5,
            max_depth=10,
            max_states=100,
            memory_budget_mb=128,
            solver_options={"workers": 2},
        ),
        tool_version="custom-checker 1.0",
    )

    result = run_model_checker(request)

    assert result.outcome == "valid"
    assert result.exit_code == 0
    assert result.reproducibility.cwd == tmp_path.as_posix()
    assert result.reproducibility.command == request.command
    assert result.reproducibility.tool_version == "custom-checker 1.0"
    assert result.reproducibility.budget.max_depth == 10
    assert result.stdout.sha256.startswith("sha256:")
    assert result.counterexamples == []


def test_model_checker_runner_normalizes_counterexample() -> None:
    request = ModelCheckerCommand(
        run_id="run-counterexample",
        checker_id="custom",
        command=[sys.executable, "-c", "print('Invariant is violated.')"],
    )

    result = run_model_checker(request)

    assert result.outcome == "counterexample"
    assert result.counterexamples[0].marker == "invariant is violated"
    assert "Invariant is violated" in result.counterexamples[0].excerpt


def test_model_checker_runner_refuses_unsupported_fragments() -> None:
    request = ModelCheckerCommand(
        run_id="run-unsupported",
        checker_id="custom",
        command=[sys.executable, "-c", "print('Unsupported operator: LeadsTo')"],
    )

    result = run_model_checker(request)

    assert result.outcome == "unsupported"
    assert result.unsupported_markers == ["unsupported", "unsupported operator"]


def test_model_checker_runner_timeouts_never_approve() -> None:
    request = ModelCheckerCommand(
        run_id="run-timeout",
        checker_id="custom",
        command=[sys.executable, "-c", "import time; time.sleep(2)"],
        budget=ModelCheckerBudget(timeout_seconds=1),
    )

    result = run_model_checker(request)

    assert result.outcome == "timeout"
    assert result.timed_out is True
    assert result.exit_code is None


def test_version_probe_of_a_different_binary_is_not_attributed(tmp_path: Path) -> None:
    """A version belongs to the executable being run, never to a different probed binary.

    Regression for missing-tool provenance: the run executes an absent binary while the
    version probe points at a *different*, runnable one (here the Python interpreter, which
    would happily print its version). Because the probe targets a different executable than the
    run, the runner must not lend that version to this run — tool_version stays null even though
    the probe itself would succeed.
    """
    request = ModelCheckerCommand(
        run_id="run-missing-tool",
        checker_id="apalache",
        command=["nlreq-absent-checker-binary", "check"],
        cwd=tmp_path.as_posix(),
        tool_version_command=[sys.executable, "--version"],
    )

    result = run_model_checker(request)

    assert result.outcome == "tool_error"
    assert result.reproducibility.executable_resolved is None
    assert result.reproducibility.tool_version is None


def test_version_probe_of_the_same_binary_is_recorded(tmp_path: Path) -> None:
    """When the version probe shares the run's executable (same basename), its version is
    recorded — the guard suppresses only cross-binary attribution, not legitimate probes."""
    request = ModelCheckerCommand(
        run_id="run-same-binary",
        checker_id="custom",
        command=[sys.executable, "-c", "print('verification successful')"],
        cwd=tmp_path.as_posix(),
        tool_version_command=[sys.executable, "--version"],
    )

    result = run_model_checker(request)

    assert result.outcome == "valid"
    assert result.reproducibility.tool_version is not None
    assert "Python" in result.reproducibility.tool_version


def test_model_checker_runner_cli_outputs_schema_backed_json(capsys) -> None:
    exit_code = main(
        [
            "model-checker-run",
            "--run-id",
            "run-cli",
            "--checker-id",
            "custom",
            "--timeout-seconds",
            "5",
            "--max-depth",
            "4",
            "--solver-option",
            "workers=2",
            "--tool-version",
            "custom-checker 1.0",
            "--",
            sys.executable,
            "-c",
            "print('verification successful')",
        ]
    )

    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["schema_version"] == "0.1"
    assert output["outcome"] == "valid"
    assert output["reproducibility"]["budget"]["max_depth"] == 4
    assert output["reproducibility"]["budget"]["solver_options"]["workers"] == 2
