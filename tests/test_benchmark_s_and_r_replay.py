"""Replay the retained S ∧ R benchmark corpus (Pillar B, PB-5).

The corpus under ``benchmarks/s-and-r/`` retains one real, replayable system-consistency
run per outcome class. These tests re-run the retained artifacts and assert they still
produce the same outcome:

- ``counterexample`` / ``valid`` re-run the *retained command* on the *committed* composed
  module through a real ``apalache-mc`` and diff the normalized trace against the golden.
  They skip with a recorded reason when the binary is absent — never a silent pass.
- ``timeout`` / ``missing-tool`` / ``unsupported`` are tool-free and reproduce
  deterministically on any machine from the committed spec + manifest.

The committed corpus must carry no machine-specific absolute path; one test enforces that
as a build-failing guard.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from nlreq.dsl_v3 import DslV3Parser
from nlreq.formal_backend import FormalBackendBudget, FormalBackendExecution
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.jsonutil import sha256_text
from nlreq.model_checker_runner import ModelCheckerBudget, ModelCheckerCommand, run_model_checker
from nlreq.system_checker import APALACHE_S_AND_R_COMMAND, check_solver_backed_system_consistency
from nlreq.system_spec import SystemSpecRegistry
from nlreq.translator import lower_ir_v2_to_tla

APALACHE = shutil.which("apalache-mc")
CORPUS = Path(__file__).resolve().parents[1] / "benchmarks" / "s-and-r" / "redemption-authorization"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text())


def _run_record(outcome: str) -> dict:
    return json.loads((CORPUS / outcome / "run.json").read_text())


def _strip_itf_trace(itf: dict) -> dict:
    """Project an ITF trace onto its deterministic state sequence (drop timestamped #meta).

    Must match scripts/generate_s_and_r_benchmarks.py::strip_itf_trace so the replayed trace
    and the committed golden agree by construction.
    """
    return {
        "vars": itf["vars"],
        "params": itf.get("params", []),
        "states": [{k: v for k, v in state.items() if k != "#meta"} for state in itf["states"]],
    }


def _impact() -> ImpactAnalysisArtifact:
    return ImpactAnalysisArtifact.model_validate(MANIFEST["impact"])


def _registry(project_root: Path, *, invariants: list[str]) -> SystemSpecRegistry:
    """Reconstruct the reviewed-spec registry from the committed spec + manifest."""
    spec_text = (CORPUS / MANIFEST["spec_path"]).read_text()
    spec_name = Path(MANIFEST["spec_path"]).name
    specs = project_root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / spec_name).write_text(spec_text)
    entry: dict[str, object] = {
        "spec_id": MANIFEST["spec_id"],
        "module_ids": MANIFEST["module_ids"],
        "formalism": "tla",
        "path": f"specs/{spec_name}",
        "version": "1",
        "review_status": "reviewed",
        "freshness": "fresh",
        "invariants": invariants,
        "init_op": MANIFEST["init_op"],
        "next_op": MANIFEST["next_op"],
    }
    return SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": [entry]})


def _check(project_root: Path, *, requirement_id: str, dsl: str, command: list[str],
           checker_id: str, invariants: list[str], timeout_seconds: int):
    """Reconstruct and run the S ∧ R check from the committed scenario (the tool-free replay)."""
    ir = DslV3Parser().parse_ir(dsl, requirement_id=requirement_id, title=requirement_id)
    return check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_registry(project_root, invariants=invariants),
        impact=_impact(),
        project_root=project_root,
        budget=FormalBackendBudget(timeout_seconds=timeout_seconds, max_depth=MANIFEST["budget"]["max_depth"]),
        execution=FormalBackendExecution(
            checker_id=checker_id,
            command=command,
            artifact_dir=(project_root / "artifacts").as_posix(),
        ),
    )


def _replay_committed_module(outcome: str, tmp_path: Path):
    """Re-run the retained command on the committed composed module (the real-tool replay)."""
    record = _run_record(outcome)
    work = tmp_path / outcome
    work.mkdir(parents=True)
    for name in (record["module"], record["config"]):
        (work / name).write_text((CORPUS / outcome / name).read_text())
    bounds = record["bounds"]
    result = run_model_checker(
        ModelCheckerCommand(
            run_id=f"replay:{outcome}",
            checker_id=record["checker_id"],
            command=record["command"],
            cwd=work.as_posix(),
            budget=ModelCheckerBudget(
                timeout_seconds=bounds.get("timeout_seconds"),
                max_depth=bounds.get("max_depth"),
            ),
            tool_version_command=record.get("tool_version_command"),
        )
    )
    return result, work


# ---------------------------------------------------------------------------
# Corpus integrity — runs on every machine.
# ---------------------------------------------------------------------------

def test_corpus_has_no_absolute_paths() -> None:
    """Retained artifacts must carry no machine-specific absolute path (CLAUDE.md; replay)."""
    markers = ["/Users/", "/home/", "/private/", "/var/folders", ".venv", str(Path.home())]
    offenders: list[str] = []
    for path in sorted(CORPUS.glob("**/*")):
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        for marker in markers:
            if marker and marker in text:
                offenders.append(f"{path.relative_to(CORPUS)} contains {marker!r}")
    assert not offenders, offenders


def test_committed_run_statuses_match_manifest() -> None:
    """Each retained run record's status matches the manifest's expected outcome."""
    for outcome, spec in MANIFEST["outcomes"].items():
        record = _run_record(outcome)
        assert record["status"] == spec["expect_status"], (outcome, record["status"])


def test_missing_tool_record_does_not_misattribute_a_version() -> None:
    """The absent-binary run records no tool version — a version belongs to the executable that
    actually ran. The run executes an absent ``apalache-mc-not-installed`` while the configured
    probe targets a different binary, so the retained record must carry ``tool_version: null``
    rather than the installed Apalache's version for a checker that never executed."""
    record = _run_record("missing-tool")
    assert record["command"][0] == "apalache-mc-not-installed"
    assert record["tool_version"] is None


def test_manifest_command_equals_centralized_source_of_truth() -> None:
    """The retained corpus and the default gate must run the *same* Apalache command.

    ``APALACHE_S_AND_R_COMMAND`` (owned by system_checker) is what the default end-to-end gate
    runs; the committed manifest records what produced this corpus. If they drift, a passing
    replay would no longer testify to the command the gate actually executes — so pin them
    equal. The flags (--cinit/--init/--next/--inv) bind the composed module's operators; dropping
    any silently checks a different system.
    """
    assert MANIFEST["apalache_command"] == list(APALACHE_S_AND_R_COMMAND)


def test_counterexample_module_hash_matches_run_record() -> None:
    """The retained counterexample module is exactly the one the recorded run checked."""
    record = _run_record("counterexample")
    module_text = (CORPUS / "counterexample" / record["module"]).read_text()
    assert sha256_text(module_text) == record["module_sha256"]


def test_counterexample_module_names_the_violated_invariant() -> None:
    """The composed module conjoins the requirement obligation as a named invariant, and the
    golden trace walks S's own transitions into the forbidden outcome."""
    record = _run_record("counterexample")
    module_text = (CORPUS / "counterexample" / record["module"]).read_text()
    assert "R_Requirement == Pred_not_authorized(wallet) => ~Pred_finalize_redemption(wallet)" in module_text
    assert "Inv == AuthorizationDefaultsClosed /\\ R_Requirement" in module_text
    trace = json.loads((CORPUS / "counterexample" / "trace.json").read_text())
    phases = [state["authPhase"] for state in trace["states"]]
    assert phases[0] == "init"
    assert "finalized" in phases[1:], phases


# ---------------------------------------------------------------------------
# Real-tool replay — requires apalache-mc; skips (never silently passes) when absent.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_counterexample_replays_to_committed_trace(tmp_path: Path) -> None:
    """Re-running the retained command on the committed module reproduces a real counterexample
    that walks S's own transitions into the forbidden outcome — the SP2-B replay.

    The assertion is the forced violating spine: the replayed ``authPhase`` progression equals
    the committed golden's (init → denied → finalized) and reaches the forbidden outcome with the
    scope constants pinned through every state. For this deterministic model that path is unique,
    so the spine *is* the whole behavior. It deliberately does not require the ITF JSON to be
    byte-identical across operating systems — that would couple a green build to Apalache/Z3
    emission ordering (the `vars`/`params` metadata lists) rather than to the property under
    test, and this gate runs on a platform the golden was not generated on.
    """
    result, work = _replay_committed_module("counterexample", tmp_path)
    assert result.outcome == "counterexample", result.stdout.tail
    traces = sorted(work.glob("**/violation.itf.json"))
    assert traces, "expected a replayed ITF counterexample trace"
    replayed = _strip_itf_trace(json.loads(traces[0].read_text()))
    golden = json.loads((CORPUS / "counterexample" / "trace.json").read_text())
    replayed_phases = [state["authPhase"] for state in replayed["states"]]
    golden_phases = [state["authPhase"] for state in golden["states"]]
    assert replayed_phases == golden_phases, (replayed_phases, golden_phases)
    assert replayed_phases[0] == "init" and replayed_phases[-1] == "finalized"
    # The scope constants stay pinned (ConstInit bound them) through every replayed state, so the
    # violation is a real S behavior over its own variables, not an unconstrained search.
    for state in replayed["states"]:
        assert state["redemption"] == "redemption" and state["wallet"] == "wallet"


@pytest.mark.skipif(APALACHE is None, reason="apalache-mc binary not installed")
def test_valid_replays_to_valid(tmp_path: Path) -> None:
    """Re-running the retained command on the committed valid module reproduces 'valid'."""
    result, _ = _replay_committed_module("valid", tmp_path)
    assert result.outcome == "valid", result.stdout.tail


# ---------------------------------------------------------------------------
# Tool-free replay — reproduces deterministically on any machine.
# ---------------------------------------------------------------------------

def test_timeout_replays_as_non_approving(tmp_path: Path) -> None:
    """A per-requirement budget exhausted by a slow checker maps to 'timeout', never 'valid'."""
    scenario = MANIFEST["outcomes"]["counterexample"]
    result = _check(
        tmp_path,
        requirement_id=scenario["requirement_id"],
        dsl=scenario["requirement_dsl"],
        command=[sys.executable, "-c", "import time; time.sleep(5)"],
        checker_id="custom",
        invariants=MANIFEST["invariants"],
        timeout_seconds=MANIFEST["timeout_budget_seconds"],
    )
    assert result.result.status == "timeout"
    assert result.result.evidence_level is None


def test_missing_tool_replays_as_tool_error(tmp_path: Path) -> None:
    """An absent checker binary degrades to a tool error (status 'invalid'), never 'valid'."""
    scenario = MANIFEST["outcomes"]["counterexample"]
    result = _check(
        tmp_path,
        requirement_id=scenario["requirement_id"],
        dsl=scenario["requirement_dsl"],
        command=["apalache-mc-not-installed", "check", "{module}"],
        checker_id="apalache",
        invariants=MANIFEST["invariants"],
        timeout_seconds=MANIFEST["budget"]["timeout_seconds"],
    )
    assert result.result.status == "invalid"
    assert result.result.details["runner_outcome"] == "tool_error"


def test_unsupported_replays_as_refusal(tmp_path: Path) -> None:
    """A relevant reviewed S that declares no invariant refuses rather than passing vacuously."""
    scenario = MANIFEST["outcomes"]["counterexample"]
    result = _check(
        tmp_path,
        requirement_id=scenario["requirement_id"],
        dsl=scenario["requirement_dsl"],
        command=MANIFEST["apalache_command"],
        checker_id="apalache",
        invariants=[],
        timeout_seconds=MANIFEST["budget"]["timeout_seconds"],
    )
    assert result.result.status == "unsupported"
    assert result.result.details["refusal_kind"] == "no_system_invariant"
