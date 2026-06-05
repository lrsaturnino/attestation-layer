import json
import shutil
import sys
from pathlib import Path

import pytest

from nlreq.cli import main
from nlreq.model_checker_runner import (
    ModelCheckerBudget,
    ModelCheckerCommand,
    _same_tool,
    _tool_identity,
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


def test_same_tool_matches_a_direct_binary_by_basename() -> None:
    """A direct binary is its own tool: a `version` subcommand and a `check` run match, and an
    absolute path matches a bare name, while a differently-named binary does not."""
    assert _same_tool(["apalache-mc", "check", "--length=10", "M.tla"], ["apalache-mc", "version"])
    assert _same_tool(["/opt/bin/apalache-mc", "check", "M.tla"], ["apalache-mc", "version"])
    assert not _same_tool(["apalache-mc-not-installed", "check"], ["apalache-mc", "version"])


def test_same_tool_matches_a_jvm_run_to_its_main_class_probe() -> None:
    """Positive TLC case (the milestone test skips without the pinned jar, so this carries it):
    a `java -cp tla2tools.jar tlc2.TLC -config X.cfg M.tla` run and a `java -cp tla2tools.jar
    tlc2.TLC` probe invoke the same main class, so the probe's version is attributable."""
    run = ["java", "-cp", "tla2tools.jar", "tlc2.TLC", "-config", "X.cfg", "M.tla"]
    probe = ["java", "-cp", "tla2tools.jar", "tlc2.TLC"]
    assert _same_tool(run, probe)


def test_same_tool_rejects_a_jvm_version_probe_of_a_different_main_class() -> None:
    """The unsoundness the basename rule allowed: a bare `java -version` run reports the JVM, not
    TLC, so a `java -cp tla2tools.jar tlc2.TLC` probe (a different main class) must not lend it the
    TLC version even though both share the `java` launcher."""
    assert not _same_tool(["java", "-version"], ["java", "-cp", "tla2tools.jar", "tlc2.TLC"])
    # Different main classes under the same launcher are different tools.
    assert not _same_tool(
        ["java", "-cp", "other.jar", "com.other.Main"],
        ["java", "-cp", "tla2tools.jar", "tlc2.TLC"],
    )
    # The `-jar` launch form is identified by its jar, distinct from a bare JVM probe.
    assert not _same_tool(["java", "-jar", "tool.jar", "arg"], ["java", "-version"])
    assert _same_tool(["java", "-jar", "tool.jar", "arg"], ["java", "-jar", "tool.jar", "--version"])


def test_tool_identity_normalizes_launch_forms() -> None:
    """Tool identity ignores trailing program args and JVM flags, isolating the program named."""
    assert _tool_identity(["apalache-mc", "check", "M.tla"]) == ("apalache-mc",)
    assert _tool_identity(["java", "-version"]) == ("java",)
    assert _tool_identity(["java", "-Xmx512m", "-cp", "a.jar", "tlc2.TLC", "M.tla"]) == (
        "java",
        "class:tlc2.TLC",
    )
    assert _tool_identity(["java", "-jar", "/abs/tool.jar"]) == ("java", "jar:tool.jar")


@pytest.mark.skipif(shutil.which("java") is None, reason="java launcher not installed")
def test_jvm_version_probe_of_a_different_main_class_is_not_attributed(tmp_path: Path) -> None:
    """End-to-end via the runner: a `tlc2.TLC` run never inherits a bare `java -version` probe.

    The probe `java -version` *succeeds* (the JVM is installed) and prints the JVM banner, so if the
    same-tool guard wrongly matched, the run would record the JVM version. Because the run's main
    class (tlc2.TLC) differs from the probe's (the bare JVM), the guard keeps tool_version null —
    the null is the guard's doing, not a failed probe. The positive control below proves the probe
    mechanism does yield a version, so the negative case is not vacuous."""
    negative = run_model_checker(
        ModelCheckerCommand(
            run_id="run-tlc-jvm-probe",
            checker_id="tlc",
            command=["java", "-cp", "tla2tools.jar", "tlc2.TLC", "-config", "M.cfg", "M.tla"],
            cwd=tmp_path.as_posix(),
            tool_version_command=["java", "-version"],
        )
    )
    assert negative.reproducibility.tool_version is None

    # Positive control: a bare `java -version` run and a bare `java -version` probe are the same
    # tool (the JVM itself), so the version IS recorded — proving the probe produces output and the
    # negative null above is attributable to the guard.
    control = run_model_checker(
        ModelCheckerCommand(
            run_id="run-jvm-self",
            checker_id="jvm",
            command=["java", "-version"],
            cwd=tmp_path.as_posix(),
            tool_version_command=["java", "-version"],
        )
    )
    assert control.reproducibility.tool_version is not None


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
