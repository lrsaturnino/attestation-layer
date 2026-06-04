"""Generate the retained S ∧ R benchmark corpus (Pillar B, PB-5).

This script composes a reviewed system spec ``S`` with a requirement ``R`` and runs
a real model checker to produce one retained, replayable artifact per outcome class:
``valid``, ``counterexample``, ``timeout``, ``unsupported``, and ``missing-tool``. The
artifacts are written under ``benchmarks/s-and-r/<corpus-id>/`` and committed so the
replay test (``tests/test_benchmark_s_and_r_replay.py``) can re-run them.

The ``valid`` and ``counterexample`` artifacts require a real Apalache binary
(``apalache-mc`` on PATH; pin/install via ``scripts/install_formal_backends.sh``). The
``timeout``, ``unsupported``, and ``missing-tool`` artifacts are tool-free and
deterministic, so the replay reproduces them on any machine.

Run from the repository root:

    uv run python scripts/generate_s_and_r_benchmarks.py

Every committed artifact is sanitized of absolute paths: the model checker is invoked
over the composed module by its basename (the runner's ``command`` is already
path-relative), and the run summary drops the resolved executable path and working
directory. The byte-stable golden for the counterexample is the model checker's ITF
trace with its (timestamped) ``#meta`` stripped — the sequence of system states that
walk ``S``'s own transition relation into the forbidden outcome.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

# The script lives in scripts/; the package source is under src/.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nlreq.dsl_v3 import DslV3Parser  # noqa: E402
from nlreq.formal_backend import FormalBackendBudget, FormalBackendExecution  # noqa: E402
from nlreq.impact import ImpactAnalysisArtifact  # noqa: E402
from nlreq.jsonutil import sha256_text  # noqa: E402
from nlreq.system_checker import check_solver_backed_system_consistency  # noqa: E402
from nlreq.system_spec import SystemSpecRegistry  # noqa: E402
from nlreq.translator import lower_ir_v2_to_tla  # noqa: E402

CORPUS_ID = "redemption-authorization"
CORPUS_DIR = REPO_ROOT / "benchmarks" / "s-and-r" / CORPUS_ID

SPEC_ID = "spec:redemption"
SPEC_FILENAME = "RedemptionAuthorization.tla"
MODULE_IDS = ["redemption"]
INIT_OP = "SInit"
NEXT_OP = "SNext"
INVARIANTS = ["AuthorizationDefaultsClosed"]

# The reviewed system spec S. It brings its OWN transition system (SInit/SNext over the
# authPhase variable): authorization starts open, can be denied, and a denied redemption
# can still finalize. The narrowing conjoins R's obligation as a state invariant over S's
# own variables, so a counterexample is a real S behaviour, not a requirement-harness
# artifact (see PB-1).
STATEFUL_SPEC = (
    "---- MODULE RedemptionAuthorization ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE authPhase\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase \\in {"denied", "finalized"}\n'
    "\\* @type: (Str) => Bool;\n"
    'Pred_finalize_redemption(a) == authPhase = "finalized"\n'
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == \\/ (authPhase = "init" /\\ authPhase\' = "denied")\n'
    '         \\/ (authPhase = "denied" /\\ authPhase\' = "finalized")\n'
    '         \\/ UNCHANGED authPhase\n'
    "====\n"
)

# A requirement R that contradicts S: it forbids finalizing a redemption while the wallet
# is unauthorized, but S can step init -> denied -> finalized while unauthorized.
COUNTEREXAMPLE_REQUIREMENT_ID = "REQ-SYS-AUTHZ-NEG"
COUNTEREXAMPLE_DSL = (
    "requirement authorization_precondition: scope redemption "
    "when wallet is not authorized then finalize_redemption must reject before rejected."
)
# Its compatible sibling: the premise (wallet authorized) is never satisfiable under S
# (Pred_authorized is pinned FALSE), so the obligation holds vacuously — a real 'valid'.
VALID_REQUIREMENT_ID = "REQ-SYS-AUTHZ"
VALID_DSL = (
    "requirement authorization_precondition: scope redemption "
    "when wallet is authorized then finalize_redemption must reject before rejected."
)

# The product-vs-narrowing DISCRIMINATOR. Same requirement R as the counterexample (the
# premise "wallet is not authorized" genuinely FIRES — S reaches "denied"), but this reviewed
# spec has NO transition that finalizes the redemption (Pred_finalize_redemption is pinned
# FALSE; SNext stops at "denied"). Under the narrowing this is a real, NON-vacuous 'valid':
# the obligation holds because S cannot reach the forbidden outcome even though the premise is
# satisfiable. A *product* composition would instead report a spurious counterexample here —
# its requirement harness reaches "accepted" on its own, independent of S. Pairing this 'valid'
# with the counterexample (same R, an S that CAN reach "finalized") proves the check depends on
# S's transition relation, not on a requirement harness — i.e. it is a narrowing, not a product.
UNREACHABLE_SPEC_FILENAME = "RedemptionAuthorizationUnreachable.tla"
UNREACHABLE_SPEC = (
    "---- MODULE RedemptionAuthorizationUnreachable ----\n"
    "EXTENDS Naturals, TLC\n\n"
    "\\* @type: Str;\n"
    "VARIABLE authPhase\n\n"
    "\\* @type: (Str) => Bool;\n"
    "Pred_authorized(a) == FALSE\n"
    "\\* @type: (Str) => Bool;\n"
    'Pred_not_authorized(a) == authPhase = "denied"\n'
    "\\* @type: (Str) => Bool;\n"
    "Pred_finalize_redemption(a) == FALSE\n"
    "\\* System invariant: authorization defaults closed.\n"
    'AuthorizationDefaultsClosed == Pred_authorized("wallet") = FALSE\n'
    'SInit == authPhase = "init"\n'
    'SNext == (authPhase = "init" /\\ authPhase\' = "denied") \\/ UNCHANGED authPhase\n'
    "====\n"
)

APALACHE_COMMAND = [
    "apalache-mc",
    "check",
    "--cinit=ConstInit",
    "--init=Init",
    "--next=Next",
    "--inv=Inv",
    "--length=6",
    "{module}",
]
BUDGET = {"timeout_seconds": 60, "max_depth": 6}
TIMEOUT_BUDGET_SECONDS = 1

IMPACT = ImpactAnalysisArtifact(
    adapter_id="python-source",
    language="python",
    input_symbols=["finalize_redemption"],
    affected_modules=MODULE_IDS,
)


def _registry(project_root: Path, *, invariants: list[str],
              spec_text: str = STATEFUL_SPEC, spec_filename: str = SPEC_FILENAME) -> SystemSpecRegistry:
    """Write the reviewed spec under project_root and return a registry pointing at it."""
    specs = project_root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / spec_filename).write_text(spec_text)
    entry: dict[str, object] = {
        "spec_id": SPEC_ID,
        "module_ids": MODULE_IDS,
        "formalism": "tla",
        "path": f"specs/{spec_filename}",
        "version": "1",
        "review_status": "reviewed",
        "freshness": "fresh",
        "invariants": invariants,
        "init_op": INIT_OP,
        "next_op": NEXT_OP,
    }
    return SystemSpecRegistry.model_validate({"schema_version": "0.1", "specs": [entry]})


def _ir(requirement_id: str, dsl: str):
    return DslV3Parser().parse_ir(dsl, requirement_id=requirement_id, title=requirement_id)


def _run(project_root: Path, requirement_id: str, dsl: str, command: list[str], *,
         checker_id: str, invariants: list[str], timeout_seconds: int,
         spec_text: str = STATEFUL_SPEC, spec_filename: str = SPEC_FILENAME):
    ir = _ir(requirement_id, dsl)
    return check_solver_backed_system_consistency(
        requirement=ir,
        lowered=lower_ir_v2_to_tla(ir),
        registry=_registry(project_root, invariants=invariants,
                           spec_text=spec_text, spec_filename=spec_filename),
        impact=IMPACT,
        project_root=project_root,
        budget=FormalBackendBudget(timeout_seconds=timeout_seconds, max_depth=BUDGET["max_depth"]),
        execution=FormalBackendExecution(
            checker_id=checker_id,
            command=command,
            artifact_dir=(project_root / "artifacts").as_posix(),
        ),
    )


def strip_itf_trace(itf: dict) -> dict:
    """Drop the (timestamped) ITF metadata, keeping the deterministic state sequence.

    The model checker stamps a wall-clock ``#meta.description`` into every ITF file, so the
    raw trace is not byte-stable. The state walk itself is deterministic for this spec, so
    the golden retains only ``vars``, ``params``, and the per-state assignments. The replay
    test applies this same projection, so generator and replay agree by construction.
    """
    return {
        "vars": itf["vars"],
        "params": itf.get("params", []),
        "states": [{k: v for k, v in state.items() if k != "#meta"} for state in itf["states"]],
    }


def _canonical_json(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _sanitize_command(command: list[str]) -> list[str]:
    """Drop machine-specific absolute paths from a recorded checker argv.

    The stub checkers used for the tool-free outcome classes invoke the current Python
    interpreter (``sys.executable``, an absolute path); record it abstractly so the
    committed artifact carries no machine-specific path.
    """
    home = str(Path.home())
    sanitized: list[str] = []
    for arg in command:
        if arg == sys.executable:
            sanitized.append("python3")
        else:
            sanitized.append(arg.replace(home, "<HOME>"))
    return sanitized


def _sanitize_text(text: str, project_root: Path) -> str:
    """Replace machine-specific absolute paths with stable placeholders."""
    replacements = {
        str(project_root.resolve()): "<RUN_DIR>",
        str(Path(tempfile.gettempdir()).resolve()): "<TMP>",
        str(Path.home()): "<HOME>",
    }
    for needle, placeholder in replacements.items():
        text = text.replace(needle, placeholder)
    return text


def _run_summary(result, *, module_name: str | None, config_name: str | None,
                 module_sha: str | None, trace_ref: str | None) -> dict:
    """A sanitized, path-free run record: version, command, bounds, outcome, hashes.

    Drops the runner's ``reproducibility.cwd`` and ``executable_resolved`` (both absolute,
    machine-specific) but keeps ``tool_version`` and ``tool_version_command`` so the run
    records the exact tool it was produced by (PB-3).
    """
    details = result.result.details
    repro = details.get("reproducibility", {}) or {}
    summary: dict[str, object] = {
        "requirement_id": result.requirement_id,
        "checker_id": details.get("checker_id"),
        "status": result.result.status,
        "runner_outcome": details.get("runner_outcome"),
        "evidence_level": (
            result.result.evidence_level.value if result.result.evidence_level is not None else None
        ),
        "command": _sanitize_command(list(repro.get("command", details.get("command", [])))),
        "tool_version": repro.get("tool_version"),
        "tool_version_command": repro.get("tool_version_command"),
        "bounds": details.get("bounds", {}),
    }
    if module_name is not None:
        summary["module"] = module_name
        summary["module_sha256"] = module_sha
    if config_name is not None:
        summary["config"] = config_name
    if "preserved_invariants" in details:
        summary["preserved_invariants"] = details["preserved_invariants"]
    if details.get("refusal_kind") is not None:
        summary["refusal_kind"] = details["refusal_kind"]
    if details.get("reason") is not None:
        summary["reason"] = details["reason"]
    if details.get("tool_error") is not None:
        summary["tool_error"] = details["tool_error"]
    if trace_ref is not None:
        summary["trace"] = trace_ref
    return summary


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"  wrote {path.relative_to(REPO_ROOT)}")


def _copy_composed_module(result, dest_dir: Path, project_root: Path) -> tuple[str, str, str]:
    """Copy the composed S ∧ R module + config into the corpus, returning (module, cfg, sha)."""
    details = result.result.details
    module_name = details["module"]
    config_name = details["config"]
    src_dir = project_root / "artifacts"
    module_text = (src_dir / module_name).read_text()
    config_text = (src_dir / config_name).read_text()
    _write(dest_dir / module_name, module_text)
    _write(dest_dir / config_name, config_text)
    return module_name, config_name, sha256_text(module_text)


def _extract_itf(project_root: Path) -> dict:
    artifacts = project_root / "artifacts"
    itfs = sorted(artifacts.glob("**/violation.itf.json"))
    if not itfs:
        raise RuntimeError("no ITF counterexample trace was produced")
    return json.loads(itfs[0].read_text())


def generate() -> None:
    if shutil.which("apalache-mc") is None:
        raise SystemExit(
            "apalache-mc is required to (re)generate the valid/counterexample artifacts. "
            "Install it with scripts/install_formal_backends.sh and ensure it is on PATH."
        )

    if CORPUS_DIR.exists():
        shutil.rmtree(CORPUS_DIR)
    CORPUS_DIR.mkdir(parents=True)

    # The reviewed system specs, committed as the source of the corpus: the primary S (its
    # Next reaches the forbidden outcome) and the discriminator S (its Next cannot).
    _write(CORPUS_DIR / "spec" / SPEC_FILENAME, STATEFUL_SPEC)
    _write(CORPUS_DIR / "spec" / UNREACHABLE_SPEC_FILENAME, UNREACHABLE_SPEC)

    with tempfile.TemporaryDirectory() as tmp:
        # ---- counterexample: real Apalache finds an S behaviour that violates R ----
        root = Path(tmp) / "counterexample"
        result = _run(root, COUNTEREXAMPLE_REQUIREMENT_ID, COUNTEREXAMPLE_DSL, APALACHE_COMMAND,
                      checker_id="apalache", invariants=INVARIANTS,
                      timeout_seconds=BUDGET["timeout_seconds"])
        assert result.result.status == "counterexample", result.result.details
        dest = CORPUS_DIR / "counterexample"
        module_name, config_name, module_sha = _copy_composed_module(result, dest, root)
        itf = _extract_itf(root)
        _write(dest / "trace.json", _canonical_json(strip_itf_trace(itf)))
        _write(dest / "stdout.txt",
               _sanitize_text(result.result.details["stdout"]["tail"], root))
        _write(dest / "run.json", _canonical_json(_run_summary(
            result, module_name=module_name, config_name=config_name,
            module_sha=module_sha, trace_ref="trace.json")))

        # ---- valid: the compatible sibling — S cannot satisfy the premise ----
        root = Path(tmp) / "valid"
        result = _run(root, VALID_REQUIREMENT_ID, VALID_DSL, APALACHE_COMMAND,
                      checker_id="apalache", invariants=INVARIANTS,
                      timeout_seconds=BUDGET["timeout_seconds"])
        assert result.result.status == "valid", result.result.details
        dest = CORPUS_DIR / "valid"
        module_name, config_name, module_sha = _copy_composed_module(result, dest, root)
        _write(dest / "stdout.txt",
               _sanitize_text(result.result.details["stdout"]["tail"], root))
        _write(dest / "run.json", _canonical_json(_run_summary(
            result, module_name=module_name, config_name=config_name,
            module_sha=module_sha, trace_ref=None)))

        # ---- valid-premise-fires: the product-vs-narrowing discriminator ----
        # Same requirement R as the counterexample (the premise FIRES — S reaches "denied"),
        # but this S has no transition that finalizes the redemption. The narrowing returns a
        # real, NON-vacuous 'valid'; a product composition would report a spurious
        # counterexample here. The differing outcome vs the counterexample (same R) is produced
        # solely by S's transition relation — the proof that the composition narrows S.
        root = Path(tmp) / "valid-premise-fires"
        result = _run(root, COUNTEREXAMPLE_REQUIREMENT_ID, COUNTEREXAMPLE_DSL, APALACHE_COMMAND,
                      checker_id="apalache", invariants=INVARIANTS,
                      timeout_seconds=BUDGET["timeout_seconds"],
                      spec_text=UNREACHABLE_SPEC, spec_filename=UNREACHABLE_SPEC_FILENAME)
        assert result.result.status == "valid", result.result.details
        assert not result.counterexamples, "a product composition would falsely flag this"
        dest = CORPUS_DIR / "valid-premise-fires"
        module_name, config_name, module_sha = _copy_composed_module(result, dest, root)
        _write(dest / "stdout.txt",
               _sanitize_text(result.result.details["stdout"]["tail"], root))
        _write(dest / "run.json", _canonical_json(_run_summary(
            result, module_name=module_name, config_name=config_name,
            module_sha=module_sha, trace_ref=None)))

        # ---- timeout: the per-requirement budget is exhausted (PB-10) ----
        # A controlled checker stub that exceeds the 1s budget composes the real S ∧ R
        # module but cannot finish in budget; the runner classifies it 'timeout', which is
        # non-approving. Tool-free and deterministic (no flaky wall-clock race on Apalache).
        root = Path(tmp) / "timeout"
        sleeper = [sys.executable, "-c", "import time; time.sleep(5)"]
        result = _run(root, COUNTEREXAMPLE_REQUIREMENT_ID, COUNTEREXAMPLE_DSL, sleeper,
                      checker_id="custom", invariants=INVARIANTS,
                      timeout_seconds=TIMEOUT_BUDGET_SECONDS)
        assert result.result.status == "timeout", result.result.details
        _write(CORPUS_DIR / "timeout" / "run.json", _canonical_json(_run_summary(
            result, module_name=None, config_name=None, module_sha=None, trace_ref=None)))

        # ---- missing-tool: the pinned checker binary is absent ----
        # The S ∧ R module composes, but the checker binary cannot be resolved; the run
        # degrades to a tool error (status 'invalid'), never a silent 'valid'.
        root = Path(tmp) / "missing-tool"
        absent = ["apalache-mc-not-installed", "check", "{module}"]
        result = _run(root, COUNTEREXAMPLE_REQUIREMENT_ID, COUNTEREXAMPLE_DSL, absent,
                      checker_id="apalache", invariants=INVARIANTS,
                      timeout_seconds=BUDGET["timeout_seconds"])
        assert result.result.status == "invalid", result.result.details
        _write(CORPUS_DIR / "missing-tool" / "run.json", _canonical_json(_run_summary(
            result, module_name=None, config_name=None, module_sha=None, trace_ref=None)))

        # ---- unsupported: a relevant reviewed S declares no invariant to preserve ----
        # S ∧ R over a spec that asserts nothing is vacuous; the composition refuses rather
        # than silently passing. Tool-free.
        root = Path(tmp) / "unsupported"
        result = _run(root, COUNTEREXAMPLE_REQUIREMENT_ID, COUNTEREXAMPLE_DSL, APALACHE_COMMAND,
                      checker_id="apalache", invariants=[],
                      timeout_seconds=BUDGET["timeout_seconds"])
        assert result.result.status == "unsupported", result.result.details
        _write(CORPUS_DIR / "unsupported" / "run.json", _canonical_json(_run_summary(
            result, module_name=None, config_name=None, module_sha=None, trace_ref=None)))

    # The manifest is the single source of truth for the scenario; the replay test
    # reconstructs the registry/requirement/impact from it to reproduce the tool-free
    # outcomes deterministically.
    manifest = {
        "corpus_id": CORPUS_ID,
        "spec_id": SPEC_ID,
        "spec_path": f"spec/{SPEC_FILENAME}",
        "module_ids": MODULE_IDS,
        "init_op": INIT_OP,
        "next_op": NEXT_OP,
        "invariants": INVARIANTS,
        "impact": IMPACT.model_dump(mode="json", exclude_none=True),
        "budget": BUDGET,
        "timeout_budget_seconds": TIMEOUT_BUDGET_SECONDS,
        "apalache_command": APALACHE_COMMAND,
        "outcomes": {
            "counterexample": {
                "requirement_id": COUNTEREXAMPLE_REQUIREMENT_ID,
                "requirement_dsl": COUNTEREXAMPLE_DSL,
                "expect_status": "counterexample",
            },
            "valid": {
                "requirement_id": VALID_REQUIREMENT_ID,
                "requirement_dsl": VALID_DSL,
                "expect_status": "valid",
            },
            "valid-premise-fires": {
                "requirement_id": COUNTEREXAMPLE_REQUIREMENT_ID,
                "requirement_dsl": COUNTEREXAMPLE_DSL,
                "spec_path": f"spec/{UNREACHABLE_SPEC_FILENAME}",
                "expect_status": "valid",
                "discriminator": (
                    "Same R as 'counterexample'; valid only because this S cannot reach the "
                    "forbidden outcome though the premise fires. Proves narrowing, not product."
                ),
            },
            "timeout": {"expect_status": "timeout"},
            "missing-tool": {"expect_status": "invalid"},
            "unsupported": {"expect_status": "unsupported"},
        },
    }
    _write(CORPUS_DIR / "manifest.json", _canonical_json(manifest))
    print("done.")


if __name__ == "__main__":
    generate()
