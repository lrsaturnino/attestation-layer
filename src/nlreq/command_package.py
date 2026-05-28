from __future__ import annotations

from pathlib import Path

from .bindings import bind_ir_with_diagnostics
from .command_adapter import CommandAdapter, CommandChecksArtifact, CommandResultsArtifact
from .jsonutil import sha256_json, write_json
from .models import (
    AssumptionsArtifact,
    BackendResult,
    BackendResultsArtifact,
    BindingsArtifact,
    Counterexample,
    CounterexamplesArtifact,
    EvidenceClaim,
    EvidenceLevel,
    EvidenceObject,
    GeneratedTestsArtifact,
    NormalizedTraceArtifact,
    RequirementIR,
    ReviewArtifact,
    SourceSpan,
    StatusDecision,
    VerificationTask,
    VerificationTasksArtifact,
)
from .package import _expect, _implementation_spec, _requirement_markdown, _review, _symbol_spans
from .parser import RequirementParser
from .smt import check_self_consistency, smt2_for_ir, smt_check_requirement
from .status import decide_status


def build_command_package(
    *,
    controlled_text: str,
    output_dir: Path,
    requirement_id: str,
    title: str,
    claim_kind: str,
    adapter: CommandAdapter,
) -> None:
    parser = RequirementParser()
    ir = parser.parse_ir(
        controlled_text,
        requirement_id=requirement_id,
        title=title,
        claim_kind=claim_kind,
        approved_by="phase10@example.invalid",
        approved_at="2026-05-26T00:00:00Z",
    )
    binding = bind_ir_with_diagnostics(ir, adapter)
    bound_ir = binding.bound_ir
    tasks = adapter.generate_tasks(bound_ir)
    if not tasks:
        raise ValueError(f"no command checks cover requirement {requirement_id}")
    ir_hash = sha256_json(bound_ir)
    task_results = adapter.collect_evidence([adapter.run_task(task) for task in tasks])
    command_checks = adapter.checks_artifact_for_requirement(requirement_id)
    command_results = CommandResultsArtifact(results=task_results)
    evidence = _command_evidence_for_ir(
        bound_ir,
        ir_hash=ir_hash,
        adapter=adapter,
        missing_symbols=binding.missing_symbols,
        ambiguous_symbols=binding.ambiguous_symbols,
        ambiguous_symbol_spans=_symbol_spans(bound_ir, binding.ambiguous_symbols),
        unbound_symbol_spans=_symbol_spans(bound_ir, binding.missing_symbols),
        tasks=tasks,
        task_results=task_results,
    )
    status = decide_status(evidence)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "requirement.md").write_text(_requirement_markdown(bound_ir))
    (output_dir / "source-diff.md").write_text(
        "No LLM rewrite was used. Controlled text was submitted directly.\n"
    )
    write_json(output_dir / "requirement.ir.json", bound_ir)
    write_json(output_dir / "bindings.json", bound_ir.bindings)
    write_json(output_dir / "assumptions.json", bound_ir.assumptions)
    write_json(output_dir / "review.json", _review(bound_ir, reviewer="phase10@example.invalid"))
    write_json(output_dir / "command-checks.json", command_checks)
    write_json(output_dir / "verification-tasks.json", tasks)
    write_json(output_dir / "adapter-results.json", task_results)
    write_json(output_dir / "command-results.json", command_results)
    write_json(output_dir / "generated-tests.json", [])
    write_json(output_dir / "counterexamples.json", _counterexamples_for_results(task_results))
    write_json(output_dir / "normalized-traces.json", [])
    write_json(output_dir / "evidence.json", evidence)
    write_json(output_dir / "status.json", status)
    (output_dir / "implementation-spec.md").write_text(
        _implementation_spec(
            bound_ir,
            status.status.value,
            adapter_id=adapter.adapter_id,
            evidence_lines=_command_evidence_lines(tasks),
        )
    )
    (output_dir / "smt" / "C1.smt2").parent.mkdir(exist_ok=True)
    (output_dir / "smt" / "C1.smt2").write_text(smt2_for_ir(bound_ir))


def validate_command_package(
    package_dir: Path, adapter: CommandAdapter
) -> tuple[RequirementIR, EvidenceObject, StatusDecision]:
    ir = RequirementIR.model_validate_json((package_dir / "requirement.ir.json").read_text())
    bindings = BindingsArtifact.model_validate_json((package_dir / "bindings.json").read_text())
    assumptions = AssumptionsArtifact.model_validate_json((package_dir / "assumptions.json").read_text())
    review = ReviewArtifact.model_validate_json((package_dir / "review.json").read_text())
    command_checks = CommandChecksArtifact.model_validate_json(
        (package_dir / "command-checks.json").read_text()
    )
    tasks = VerificationTasksArtifact.model_validate_json(
        (package_dir / "verification-tasks.json").read_text()
    )
    adapter_results = BackendResultsArtifact.model_validate_json(
        (package_dir / "adapter-results.json").read_text()
    )
    command_results = CommandResultsArtifact.model_validate_json(
        (package_dir / "command-results.json").read_text()
    )
    generated_tests = GeneratedTestsArtifact.model_validate_json(
        (package_dir / "generated-tests.json").read_text()
    )
    counterexamples = CounterexamplesArtifact.model_validate_json(
        (package_dir / "counterexamples.json").read_text()
    )
    normalized_traces = NormalizedTraceArtifact.model_validate_json(
        (package_dir / "normalized-traces.json").read_text()
    )
    evidence = EvidenceObject.model_validate_json((package_dir / "evidence.json").read_text())
    status = StatusDecision.model_validate_json((package_dir / "status.json").read_text())
    _validate_command_package_integrity(
        package_dir,
        adapter,
        ir,
        bindings,
        assumptions,
        review,
        command_checks,
        tasks,
        adapter_results,
        command_results,
        generated_tests,
        counterexamples,
        normalized_traces,
        evidence,
        status,
    )
    return ir, evidence, status


def run_command_evidence(
    packages_dir: Path,
    *,
    adapter: CommandAdapter,
    requirement_ids: list[str] | None = None,
) -> CommandResultsArtifact:
    wanted = set(requirement_ids or [])
    results: list[BackendResult] = []
    package_dirs = sorted(path for path in packages_dir.iterdir() if (path / "requirement.ir.json").is_file())
    for package_dir in package_dirs:
        ir = RequirementIR.model_validate_json((package_dir / "requirement.ir.json").read_text())
        if wanted and ir.requirement_id not in wanted:
            continue
        tasks = adapter.generate_tasks(ir)
        results.extend(adapter.collect_evidence([adapter.run_task(task) for task in tasks]))
    if wanted and not results:
        missing = ", ".join(sorted(wanted))
        raise ValueError(f"no command checks ran for requested requirements: {missing}")
    return CommandResultsArtifact(results=results)


def command_results_markdown(results: CommandResultsArtifact) -> str:
    lines = [
        "# NLReq Command Evidence Report",
        "",
        f"Results: `{len(results.results)}`",
        "",
    ]
    if not results.results:
        lines.append("No command checks ran.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| Status | Check | Exit | Timeout | Command |",
            "|---|---|---|---|---|",
        ]
    )
    for result in results.results:
        details = result.details
        command = " ".join(str(part) for part in details.get("command", []))
        lines.append(
            "| {status} | {check_id} | {exit_code} | {timed_out} | {command} |".format(
                status=result.status,
                check_id=details.get("check_id") or result.details.get("task_id") or "-",
                exit_code=details.get("exit_code"),
                timed_out=details.get("timed_out", False),
                command=_escape_markdown_table(command),
            )
        )
    return "\n".join(lines) + "\n"


def _validate_command_package_integrity(
    package_dir: Path,
    adapter: CommandAdapter,
    ir: RequirementIR,
    bindings: BindingsArtifact,
    assumptions: AssumptionsArtifact,
    review: ReviewArtifact,
    command_checks: CommandChecksArtifact,
    tasks: VerificationTasksArtifact,
    adapter_results: BackendResultsArtifact,
    command_results: CommandResultsArtifact,
    generated_tests: GeneratedTestsArtifact,
    counterexamples: CounterexamplesArtifact,
    normalized_traces: NormalizedTraceArtifact,
    evidence: EvidenceObject,
    status: StatusDecision,
) -> None:
    ir_hash = sha256_json(ir)
    binding = bind_ir_with_diagnostics(ir.model_copy(update={"bindings": {}}), adapter)
    expected_checks = adapter.checks_artifact_for_requirement(ir.requirement_id)
    expected_tasks = adapter.generate_tasks(ir)
    expected_evidence = _command_evidence_for_ir(
        ir,
        ir_hash=ir_hash,
        adapter=adapter,
        missing_symbols=binding.missing_symbols,
        ambiguous_symbols=binding.ambiguous_symbols,
        ambiguous_symbol_spans=_symbol_spans(ir, binding.ambiguous_symbols),
        unbound_symbol_spans=_symbol_spans(ir, binding.missing_symbols),
        tasks=expected_tasks,
        task_results=adapter_results.root,
    )
    expected_status = decide_status(evidence)

    _expect(bindings.root == ir.bindings, "bindings.json does not match requirement.ir.json")
    _expect(binding.bound_ir.bindings == ir.bindings, "bindings.json does not match command adapter")
    _expect(assumptions.root == ir.assumptions, "assumptions.json does not match requirement.ir.json")
    _expect(command_checks == expected_checks, "command-checks.json does not match command config")
    _expect(
        tasks.root == expected_tasks,
        "verification-tasks.json does not match requirement.ir.json or command source/test hashes",
    )
    _expect(
        command_results.results == adapter_results.root,
        "command-results.json does not match adapter-results.json",
    )
    _expect(generated_tests.root == [], "generated-tests.json is not supported for command packages")
    _expect(
        counterexamples.root == _counterexamples_for_results(adapter_results.root),
        "counterexamples.json does not match adapter-results.json",
    )
    _expect(normalized_traces.root == [], "normalized-traces.json is not supported for command packages")
    _expect(
        review.reviewed_hashes.get("requirement_ir") == ir_hash,
        "review.json requirement_ir hash does not match requirement.ir.json",
    )
    _expect(evidence.requirement_id == ir.requirement_id, "evidence.json requirement_id does not match IR")
    _expect(evidence.ir_hash == ir_hash, "evidence.json ir_hash does not match requirement.ir.json")
    _expect(
        evidence == expected_evidence,
        "evidence.json does not match command results, config, or source/test hashes",
    )
    _expect(status == expected_status, "status.json does not match pure status decision")
    _expect(
        (package_dir / "requirement.md").read_text() == _requirement_markdown(ir),
        "requirement.md does not match requirement.ir.json",
    )
    _expect(
        (package_dir / "source-diff.md").read_text()
        == "No LLM rewrite was used. Controlled text was submitted directly.\n",
        "source-diff.md does not match package source policy",
    )
    _expect(
        (package_dir / "implementation-spec.md").read_text()
        == _implementation_spec(
            ir,
            status.status.value,
            adapter_id=adapter.adapter_id,
            evidence_lines=_command_evidence_lines(expected_tasks),
        ),
        "implementation-spec.md does not match requirement.ir.json and status.json",
    )
    _expect(
        (package_dir / "smt" / "C1.smt2").read_text() == smt2_for_ir(ir),
        "smt/C1.smt2 does not match requirement.ir.json",
    )


def _command_evidence_for_ir(
    ir: RequirementIR,
    *,
    ir_hash: str,
    adapter: CommandAdapter,
    missing_symbols: list[str],
    ambiguous_symbols: list[str],
    ambiguous_symbol_spans: dict[str, SourceSpan],
    unbound_symbol_spans: dict[str, SourceSpan],
    tasks: list[VerificationTask],
    task_results: list[BackendResult],
) -> EvidenceObject:
    static = BackendResult(
        backend=adapter.adapter_id,
        status="invalid" if missing_symbols or ambiguous_symbols else "valid",
        evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
        details={
            "adapter": adapter.adapter_id,
            "ambiguous_symbols": ambiguous_symbols,
            "missing_symbols": missing_symbols,
            "resolved_symbols": sorted(ir.bindings),
        },
    )
    consistency = check_self_consistency(ir)
    smt = smt_check_requirement(ir)
    task_results_by_id = _task_results_by_id(task_results)

    failed: list[str] = []
    timeouts: list[str] = []
    if static.status != "valid":
        failed.append("C-static")
    if consistency.status != "valid":
        failed.append("C-consistency")
    if smt.status != "valid":
        failed.append("C-smt")

    claims = [
        EvidenceClaim(
            id="C-static",
            description="Symbols are resolved by the command adapter vocabulary.",
            required_evidence=EvidenceLevel.STATICALLY_RESOLVED,
            achieved_evidence=EvidenceLevel.STATICALLY_RESOLVED if static.status == "valid" else None,
            backend_results=[static],
        ),
        EvidenceClaim(
            id="C-consistency",
            description="Supported claims are internally consistent.",
            required_evidence=EvidenceLevel.CONSISTENCY_CHECKED,
            achieved_evidence=EvidenceLevel.CONSISTENCY_CHECKED
            if consistency.status == "valid"
            else None,
            backend_results=[consistency],
        ),
        EvidenceClaim(
            id="C-smt",
            description="Supported claim shape is SMT-checked under declared assumptions.",
            required_evidence=EvidenceLevel.SMT_CHECKED,
            achieved_evidence=EvidenceLevel.SMT_CHECKED if smt.status == "valid" else None,
            backend_results=[smt],
        ),
    ]
    for task in tasks:
        result = task_results_by_id.get(task.id)
        claim = _claim_for_command_task(task, result)
        claims.append(claim)
        if claim.achieved_evidence is None:
            if claim.backend_results[0].status == "timeout":
                timeouts.append(task.id)
            else:
                failed.append(task.id)

    return EvidenceObject(
        requirement_id=ir.requirement_id,
        ir_hash=ir_hash,
        claims=claims,
        ambiguous=bool(ambiguous_symbols),
        ambiguous_symbols=ambiguous_symbols,
        ambiguous_symbol_spans=ambiguous_symbol_spans,
        unbound_symbols=missing_symbols,
        unbound_symbol_spans=unbound_symbol_spans,
        failed_checks=failed,
        timeouts=timeouts,
        needs_spec_coverage=not tasks,
    )


def _claim_for_command_task(
    task: VerificationTask, result: BackendResult | None
) -> EvidenceClaim:
    required = EvidenceLevel.TEST_VALIDATED
    backend_result = result or BackendResult(
        backend="command",
        status="invalid",
        evidence_level=required,
        details={
            "task_id": task.id,
            "task_input_hash": task.input_hash,
            "reason": "missing command result",
        },
    )
    fresh = backend_result.details.get("task_input_hash") == task.input_hash
    valid = (
        backend_result.status == "valid"
        and backend_result.evidence_level == required
        and fresh
    )
    return EvidenceClaim(
        id=task.id,
        description=task.description,
        required_evidence=required,
        achieved_evidence=required if valid else None,
        backend_results=[backend_result],
    )


def _task_results_by_id(results: list[BackendResult]) -> dict[str, BackendResult]:
    by_id: dict[str, BackendResult] = {}
    for result in results:
        task_id = result.details.get("task_id")
        if isinstance(task_id, str):
            by_id[task_id] = result
    return by_id


def _counterexamples_for_results(results: list[BackendResult]) -> list[Counterexample]:
    counterexamples: list[Counterexample] = []
    for result in results:
        if result.status == "valid":
            continue
        details = result.details
        check_id = str(details.get("check_id") or details.get("task_id") or "command")
        counterexamples.append(
            Counterexample(
                counterexample_id=f"{check_id}:command",
                backend="command",
                claim_id=check_id,
                description="Command check did not produce the expected result.",
                inputs={
                    "command": details.get("command", []),
                    "cwd": details.get("cwd"),
                },
                expected={
                    "exit_code": details.get("expected_exit_code"),
                    "timed_out": False,
                },
                actual={
                    "exit_code": details.get("exit_code"),
                    "timed_out": details.get("timed_out"),
                    "reason": details.get("reason"),
                },
                metadata={
                    "stdout_hash": details.get("stdout_hash"),
                    "stderr_hash": details.get("stderr_hash"),
                    "stdout_tail": details.get("stdout_tail"),
                    "stderr_tail": details.get("stderr_tail"),
                },
            )
        )
    return counterexamples


def _command_evidence_lines(tasks: list[VerificationTask]) -> list[str]:
    return [
        "IR type-checked.",
        "Symbols resolved through command adapter vocabulary.",
        "Self-consistency checked.",
        "Supported claim shape SMT-checked.",
        *[
            f"Reviewed command check `{task.id}` produced TEST_VALIDATED evidence."
            for task in tasks
        ],
    ]


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
