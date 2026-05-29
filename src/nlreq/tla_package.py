from __future__ import annotations

from pathlib import Path

from .bindings import bind_ir_with_diagnostics
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
from .tla_adapter import TlaAdapter, TlaModelConfigArtifact, TlaResultsArtifact


def build_tla_package(
    *,
    controlled_text: str,
    output_dir: Path,
    requirement_id: str,
    title: str,
    claim_kind: str,
    adapter: TlaAdapter,
) -> None:
    parser = RequirementParser()
    ir = parser.parse_ir(
        controlled_text,
        requirement_id=requirement_id,
        title=title,
        claim_kind=claim_kind,
        approved_by="phase13@example.invalid",
        approved_at="2026-05-26T00:00:00Z",
    )
    binding = bind_ir_with_diagnostics(ir, adapter)
    bound_ir = binding.bound_ir
    tasks = adapter.generate_tasks(bound_ir)
    if not tasks:
        raise ValueError(f"no TLA model checks cover requirement {requirement_id}")
    ir_hash = sha256_json(bound_ir)
    task_results = adapter.collect_evidence([adapter.run_task(task) for task in tasks])
    model_config = adapter.config_artifact_for_requirement(requirement_id)
    tla_results = TlaResultsArtifact(results=task_results)
    evidence = _tla_evidence_for_ir(
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
    write_json(output_dir / "review.json", _review(bound_ir, reviewer="phase13@example.invalid"))
    write_json(output_dir / "tla-models.json", model_config)
    write_json(output_dir / "verification-tasks.json", tasks)
    write_json(output_dir / "adapter-results.json", task_results)
    write_json(output_dir / "tla-results.json", tla_results)
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
            evidence_lines=_tla_evidence_lines(tasks),
        )
    )
    (output_dir / "smt" / "C1.smt2").parent.mkdir(exist_ok=True)
    (output_dir / "smt" / "C1.smt2").write_text(smt2_for_ir(bound_ir))


def validate_tla_package(
    package_dir: Path, adapter: TlaAdapter
) -> tuple[RequirementIR, EvidenceObject, StatusDecision]:
    ir = RequirementIR.model_validate_json((package_dir / "requirement.ir.json").read_text())
    bindings = BindingsArtifact.model_validate_json((package_dir / "bindings.json").read_text())
    assumptions = AssumptionsArtifact.model_validate_json((package_dir / "assumptions.json").read_text())
    review = ReviewArtifact.model_validate_json((package_dir / "review.json").read_text())
    model_config = TlaModelConfigArtifact.model_validate_json(
        (package_dir / "tla-models.json").read_text()
    )
    tasks = VerificationTasksArtifact.model_validate_json(
        (package_dir / "verification-tasks.json").read_text()
    )
    adapter_results = BackendResultsArtifact.model_validate_json(
        (package_dir / "adapter-results.json").read_text()
    )
    tla_results = TlaResultsArtifact.model_validate_json((package_dir / "tla-results.json").read_text())
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
    _validate_tla_package_integrity(
        package_dir,
        adapter,
        ir,
        bindings,
        assumptions,
        review,
        model_config,
        tasks,
        adapter_results,
        tla_results,
        generated_tests,
        counterexamples,
        normalized_traces,
        evidence,
        status,
    )
    return ir, evidence, status


def run_tla_checks(
    packages_dir: Path,
    *,
    adapter: TlaAdapter,
    requirement_ids: list[str] | None = None,
) -> TlaResultsArtifact:
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
        raise ValueError(f"no TLA model checks ran for requested requirements: {missing}")
    return TlaResultsArtifact(results=results)


def tla_results_markdown(results: TlaResultsArtifact) -> str:
    lines = [
        "# NLReq TLA Model-Checking Report",
        "",
        f"Results: `{len(results.results)}`",
        "",
    ]
    if not results.results:
        lines.append("No model checks ran.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| Status | Model | Checker | Properties |",
            "|---|---|---|---|",
        ]
    )
    for result in results.results:
        details = result.details
        lines.append(
            "| {status} | {model_id} | {checker} | {properties} |".format(
                status=result.status,
                model_id=details.get("model_id") or "-",
                checker=details.get("checker") or "-",
                properties=", ".join(str(item) for item in details.get("properties", [])) or "-",
            )
        )
    return "\n".join(lines) + "\n"


def _validate_tla_package_integrity(
    package_dir: Path,
    adapter: TlaAdapter,
    ir: RequirementIR,
    bindings: BindingsArtifact,
    assumptions: AssumptionsArtifact,
    review: ReviewArtifact,
    model_config: TlaModelConfigArtifact,
    tasks: VerificationTasksArtifact,
    adapter_results: BackendResultsArtifact,
    tla_results: TlaResultsArtifact,
    generated_tests: GeneratedTestsArtifact,
    counterexamples: CounterexamplesArtifact,
    normalized_traces: NormalizedTraceArtifact,
    evidence: EvidenceObject,
    status: StatusDecision,
) -> None:
    ir_hash = sha256_json(ir)
    binding = bind_ir_with_diagnostics(ir.model_copy(update={"bindings": {}}), adapter)
    expected_config = adapter.config_artifact_for_requirement(ir.requirement_id)
    expected_tasks = adapter.generate_tasks(ir)
    expected_evidence = _tla_evidence_for_ir(
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
    _expect(binding.bound_ir.bindings == ir.bindings, "bindings.json does not match TLA adapter")
    _expect(assumptions.root == ir.assumptions, "assumptions.json does not match requirement.ir.json")
    _expect(model_config == expected_config, "tla-models.json does not match model config")
    _expect(
        tasks.root == expected_tasks,
        "verification-tasks.json does not match requirement.ir.json or TLA model/config hashes",
    )
    _expect(tla_results.results == adapter_results.root, "tla-results.json does not match adapter-results.json")
    _expect(generated_tests.root == [], "generated-tests.json is not supported for TLA packages")
    _expect(
        counterexamples.root == _counterexamples_for_results(adapter_results.root),
        "counterexamples.json does not match adapter-results.json",
    )
    _expect(normalized_traces.root == [], "normalized-traces.json is not supported for TLA packages")
    _expect(
        review.reviewed_hashes.get("requirement_ir") == ir_hash,
        "review.json requirement_ir hash does not match requirement.ir.json",
    )
    _expect(evidence.requirement_id == ir.requirement_id, "evidence.json requirement_id does not match IR")
    _expect(evidence.ir_hash == ir_hash, "evidence.json ir_hash does not match requirement.ir.json")
    _expect(
        evidence == expected_evidence,
        "evidence.json does not match TLA results, config, or model/config hashes",
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
            evidence_lines=_tla_evidence_lines(expected_tasks),
        ),
        "implementation-spec.md does not match requirement.ir.json and status.json",
    )
    _expect(
        (package_dir / "smt" / "C1.smt2").read_text() == smt2_for_ir(ir),
        "smt/C1.smt2 does not match requirement.ir.json",
    )


def _tla_evidence_for_ir(
    ir: RequirementIR,
    *,
    ir_hash: str,
    adapter: TlaAdapter,
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
            description="Symbols are resolved by the TLA adapter vocabulary.",
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
        claim = _claim_for_tla_task(task, result)
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


def _claim_for_tla_task(task: VerificationTask, result: BackendResult | None) -> EvidenceClaim:
    required = EvidenceLevel.BOUNDED_CHECKED
    backend_result = result or BackendResult(
        backend="tla",
        status="invalid",
        evidence_level=required,
        details={
            "task_id": task.id,
            "task_input_hash": task.input_hash,
            "reason": "missing TLA result",
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
        model_id = str(details.get("model_id") or details.get("task_id") or "tla")
        counterexamples.append(
            Counterexample(
                counterexample_id=f"{model_id}:model_check",
                backend="tla",
                claim_id=model_id,
                description="TLA model check did not complete without a violation.",
                inputs={
                    "module": details.get("module"),
                    "config": details.get("config"),
                    "properties": details.get("properties", []),
                    "bounds": details.get("bounds", {}),
                },
                expected={"bounded_model_check": "no_violation"},
                actual={
                    "exit_code": details.get("exit_code"),
                    "timed_out": details.get("timed_out"),
                    "violation_reason": details.get("violation_reason"),
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


def _tla_evidence_lines(tasks: list[VerificationTask]) -> list[str]:
    return [
        "IR type-checked.",
        "Symbols resolved through TLA adapter vocabulary.",
        "Self-consistency checked.",
        "Supported claim shape SMT-checked.",
        *[
            f"Reviewed TLA model check `{task.id}` produced BOUNDED_CHECKED evidence."
            for task in tasks
        ],
        "No PROVEN_INDUCTIVE evidence is claimed by bounded model checks.",
    ]
