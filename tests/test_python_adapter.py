from pathlib import Path

from nlreq.bindings import bind_ir_with_diagnostics
from nlreq.cli import main
from nlreq.conformance import AdapterConformanceFixture, assert_adapter_conforms
from nlreq.models import BackendResult, EvidenceLevel, SymbolBinding, SymbolRef
from nlreq.parser import RequirementParser
from nlreq.python_adapter import PythonPackageAdapter


FIXTURE_PACKAGE = Path(__file__).parent / "fixtures" / "adapters" / "pythonpkg" / "samplepkg"
REPO_ROOT = Path(__file__).parents[1]


def test_python_adapter_indexes_module_class_function_and_method_symbols() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")

    symbols = {symbol.name: symbol for symbol in adapter.symbols()}

    assert symbols["samplepkg.core"].symbol_type == "module"
    assert symbols["samplepkg.core.operation"].symbol_type == "function"
    assert symbols["samplepkg.core.Service"].symbol_type == "class"
    assert symbols["samplepkg.core.Service.execute"].symbol_type == "function"
    assert symbols["samplepkg.core.operation"].metadata["path"] == "core.py"


def test_python_adapter_can_load_package_from_import_name(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(FIXTURE_PACKAGE.parent))

    adapter = PythonPackageAdapter.from_import_name("samplepkg")

    result = adapter.resolve_symbols([SymbolRef(name="operation", expected_type="action")])[0]
    assert result.status == "resolved"
    assert result.symbols[0].name == "samplepkg.core.operation"


def test_python_adapter_resolves_exact_and_suffix_symbols() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")

    exact = adapter.resolve_symbols([SymbolRef(name="samplepkg.core.operation")])[0]
    suffix = adapter.resolve_symbols([SymbolRef(name="Service.execute", expected_type="function")])[0]

    assert exact.status == "resolved"
    assert exact.symbols[0].name == "samplepkg.core.operation"
    assert suffix.status == "resolved"
    assert suffix.symbols[0].name == "samplepkg.core.Service.execute"


def test_python_adapter_maps_requirement_action_to_python_function() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")

    result = adapter.resolve_symbols([SymbolRef(name="operation", expected_type="action")])[0]

    assert result.status == "resolved"
    assert result.symbols[0].name == "samplepkg.core.operation"
    assert result.symbols[0].symbol_type == "function"


def test_python_adapter_reports_ambiguous_suffix_symbols() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")

    result = adapter.resolve_symbols([SymbolRef(name="duplicate_symbol", expected_type="action")])[0]

    assert result.status == "ambiguous"
    assert [symbol.name for symbol in result.symbols] == [
        "samplepkg.duplicates_a.duplicate_symbol",
        "samplepkg.duplicates_b.duplicate_symbol",
    ]


def test_python_adapter_validates_binding_against_index() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")

    valid = adapter.validate_binding(
        SymbolBinding(
            adapter="python_package",
            symbol="samplepkg.core.operation",
            symbol_type="function",
            confidence="adapter_resolved",
        )
    )
    wrong_type = adapter.validate_binding(
        SymbolBinding(
            adapter="python_package",
            symbol="samplepkg.core.operation",
            symbol_type="class",
            confidence="adapter_resolved",
        )
    )

    assert valid.valid is True
    assert wrong_type.valid is False
    assert wrong_type.reason == "binding type mismatch: expected class, found function"


def test_python_adapter_reports_phase_1_evidence_capabilities() -> None:
    adapter = PythonPackageAdapter(
        FIXTURE_PACKAGE,
        package_name="samplepkg",
        project_root=REPO_ROOT,
        test_paths=[Path("tests/fixtures/adapters/pythonpkg")],
    )
    symbol = adapter.resolve_symbols([SymbolRef(name="operation", expected_type="action")])[0].symbols[0]

    capabilities = adapter.available_evidence([symbol])

    assert [cap.evidence_level for cap in capabilities] == [
        EvidenceLevel.STATICALLY_RESOLVED,
        EvidenceLevel.TYPE_CHECKED,
        EvidenceLevel.TEST_VALIDATED,
    ]


def test_python_adapter_generates_symbol_and_pytest_tasks_for_bound_ir() -> None:
    adapter = PythonPackageAdapter(
        FIXTURE_PACKAGE,
        package_name="samplepkg",
        project_root=REPO_ROOT,
        test_paths=[Path("tests/fixtures/adapters/pythonpkg")],
    )
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is approved\nthen operation must succeed.\n",
        requirement_id="REQ-PY-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    tasks = adapter.generate_tasks(diagnostics.bound_ir)

    assert diagnostics.missing_symbols == []
    assert diagnostics.ambiguous_symbols == []
    assert sorted(diagnostics.bound_ir.bindings) == ["actor", "operation"]
    assert [task.id for task in tasks] == ["PY-SYMBOLS", "PYTEST"]
    assert tasks[0].payload["bindings"] == [
        {
            "requirement_ref": "actor",
            "symbol": "samplepkg.core.actor",
            "symbol_type": "function",
        },
        {
            "requirement_ref": "operation",
            "symbol": "samplepkg.core.operation",
            "symbol_type": "function",
        },
    ]


def test_python_adapter_collects_backend_results() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")

    results = adapter.collect_evidence(
        [
            {
                "backend": "pytest",
                "status": "valid",
                "evidence_level": "TEST_VALIDATED",
                "details": {"passed": 1},
            }
        ]
    )

    assert results == [
        BackendResult(
            backend="pytest",
            status="valid",
            evidence_level=EvidenceLevel.TEST_VALIDATED,
            details={"passed": 1},
        )
    ]


def test_python_adapter_runs_generated_symbol_shape_task() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is approved\nthen operation must succeed.\n",
        requirement_id="REQ-PY-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    result = adapter.run_task(adapter.generate_tasks(diagnostics.bound_ir)[0])

    assert result.backend == "python_package"
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.TYPE_CHECKED
    assert result.details["validated_bindings"] == 2


def test_python_adapter_runs_generated_pytest_task() -> None:
    adapter = PythonPackageAdapter(
        FIXTURE_PACKAGE,
        package_name="samplepkg",
        project_root=REPO_ROOT,
        test_paths=[Path("tests/fixtures/adapters/pythonpkg")],
    )
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is approved\nthen operation must succeed.\n",
        requirement_id="REQ-PY-001",
        title="Python operation succeeds for approved actor",
        claim_kind="state_precondition",
    )
    diagnostics = bind_ir_with_diagnostics(ir, adapter)

    result = adapter.run_task(adapter.generate_tasks(diagnostics.bound_ir)[1])

    assert result.backend == "pytest"
    assert result.status == "valid"
    assert result.evidence_level == EvidenceLevel.TEST_VALIDATED
    assert result.details["returncode"] == 0


def test_python_adapter_passes_conformance_suite() -> None:
    adapter = PythonPackageAdapter(FIXTURE_PACKAGE, package_name="samplepkg")
    ir = RequirementParser().parse_ir(
        "For every operation request:\nif actor is approved\nthen operation must succeed.\n",
        requirement_id="REQ-PY-CONFORMANCE-001",
        title="Python adapter conformance",
        claim_kind="state_precondition",
    )

    report = assert_adapter_conforms(
        adapter,
        AdapterConformanceFixture(
            resolved_ref=SymbolRef(name="operation", expected_type="action"),
            unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
            ambiguous_ref=SymbolRef(name="duplicate_symbol", expected_type="action"),
            sample_ir=ir,
        ),
    )

    assert report.adapter_id == "python_package"
    assert report.target_kind == "python_package"


def test_python_conformance_cli(capsys) -> None:
    exit_code = main(
        [
            "python-conformance",
            str(FIXTURE_PACKAGE),
            "--package-name",
            "samplepkg",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Adapter: python_package" in output
    assert "Package: samplepkg" in output
    assert "Conformance: passed" in output
