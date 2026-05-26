from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .adapter import Adapter
from .jsonutil import sha256_json
from .models import (
    BackendResult,
    EvidenceCapability,
    EvidenceLevel,
    RequirementIR,
    Symbol,
    SymbolBinding,
    SymbolRef,
    SymbolResolution,
    ValidationResult,
    VerificationTask,
)


@dataclass(frozen=True)
class PythonSource:
    module: str
    relative_path: str
    tree: ast.Module


class PythonPackageAdapter(Adapter):
    adapter_id = "python_package"
    target_kind = "python_package"

    def __init__(
        self,
        package_root: Path,
        *,
        package_name: str | None = None,
        project_root: Path | None = None,
        test_paths: Iterable[Path] = (),
    ) -> None:
        self.package_root = Path(package_root)
        if not self.package_root.is_dir():
            raise ValueError(f"Python package root does not exist: {self.package_root}")
        self.package_name = package_name or self.package_root.name
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.test_paths = tuple(Path(path) for path in test_paths)
        self._symbols = _build_symbol_index(self.package_root, self.package_name)

    @classmethod
    def from_import_name(
        cls,
        import_name: str,
        *,
        project_root: Path | None = None,
        test_paths: Iterable[Path] = (),
    ) -> PythonPackageAdapter:
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            raise ValueError(f"Python import target not found: {import_name}")
        if not spec.submodule_search_locations:
            raise ValueError(f"Python import target is not a package: {import_name}")
        locations = sorted(Path(location) for location in spec.submodule_search_locations)
        if not locations:
            raise ValueError(f"Python package has no source locations: {import_name}")
        return cls(
            locations[0],
            package_name=import_name,
            project_root=project_root,
            test_paths=test_paths,
        )

    def resolve_symbols(self, refs: list[SymbolRef]) -> list[SymbolResolution]:
        return [self._resolve_symbol(ref) for ref in refs]

    def validate_binding(self, binding: SymbolBinding) -> ValidationResult:
        if binding.adapter != self.adapter_id:
            return ValidationResult(
                valid=False,
                reason=f"binding adapter mismatch: expected {self.adapter_id}, found {binding.adapter}",
            )
        symbol = self._symbols.get(binding.symbol)
        if symbol is None:
            return ValidationResult(valid=False, reason="binding symbol not found")
        if symbol.symbol_type != binding.symbol_type:
            return ValidationResult(
                valid=False,
                reason=f"binding type mismatch: expected {binding.symbol_type}, found {symbol.symbol_type}",
            )
        return ValidationResult(valid=True)

    def available_evidence(self, symbols: list[Symbol]) -> list[EvidenceCapability]:
        if not symbols:
            return []
        capabilities = [
            EvidenceCapability(
                evidence_level=EvidenceLevel.STATICALLY_RESOLVED,
                description="Python symbol resolved from source AST.",
            ),
            EvidenceCapability(
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                description="Python module, class, and function shape validated by AST parsing.",
            ),
        ]
        if self.test_paths:
            capabilities.append(
                EvidenceCapability(
                    evidence_level=EvidenceLevel.TEST_VALIDATED,
                    description="Adapter can request scoped pytest evidence for configured test paths.",
                )
            )
        return capabilities

    def generate_tasks(self, ir: RequirementIR) -> list[VerificationTask]:
        bindings = [
            {
                "requirement_ref": name,
                "symbol": binding.symbol,
                "symbol_type": binding.symbol_type,
            }
            for name, binding in sorted(ir.bindings.items())
            if binding.adapter == self.adapter_id
        ]
        symbol_payload = {
            "adapter": self.adapter_id,
            "package": self.package_name,
            "requirement_id": ir.requirement_id,
            "task": "symbol_shape",
            "bindings": bindings,
        }
        tasks = [
            VerificationTask(
                id="PY-SYMBOLS",
                backend="adapter",
                description=f"Validate Python symbol bindings for {ir.requirement_id}.",
                input_hash=sha256_json(symbol_payload),
                payload=symbol_payload,
            )
        ]
        if self.test_paths:
            pytest_payload = {
                "adapter": self.adapter_id,
                "package": self.package_name,
                "requirement_id": ir.requirement_id,
                "task": "pytest",
                "paths": [str(path) for path in self.test_paths],
            }
            tasks.append(
                VerificationTask(
                    id="PYTEST",
                    backend="adapter",
                    description=f"Run scoped pytest evidence for {ir.requirement_id}.",
                    input_hash=sha256_json(pytest_payload),
                    payload=pytest_payload,
                )
            )
        return tasks

    def collect_evidence(self, task_results: list[object]) -> list[BackendResult]:
        collected: list[BackendResult] = []
        for result in task_results:
            if isinstance(result, BackendResult):
                collected.append(result)
                continue
            if isinstance(result, dict):
                collected.append(BackendResult.model_validate(result))
                continue
            raise TypeError(f"unsupported Python adapter task result: {type(result).__name__}")
        return collected

    def run_task(self, task: VerificationTask) -> BackendResult:
        task_kind = task.payload.get("task")
        if task_kind == "symbol_shape":
            return self._run_symbol_shape_task(task)
        if task_kind == "pytest":
            return self._run_pytest_task(task)
        return BackendResult(
            backend=self.adapter_id,
            status="unsupported",
            details={"task_id": task.id, "task": task_kind},
        )

    def symbols(self) -> list[Symbol]:
        return [self._symbols[name] for name in sorted(self._symbols)]

    def _resolve_symbol(self, ref: SymbolRef) -> SymbolResolution:
        exact = self._symbols.get(ref.name)
        if exact and _matches_expected_type(exact, ref.expected_type):
            return SymbolResolution(ref=ref, status="resolved", symbols=[exact])

        matches = [
            symbol
            for symbol in self._symbols.values()
            if _matches_symbol_name(symbol.name, ref.name)
            and _matches_expected_type(symbol, ref.expected_type)
        ]
        matches = sorted(matches, key=lambda symbol: symbol.name)
        if not matches:
            if exact is not None:
                return SymbolResolution(
                    ref=ref,
                    status="unresolved",
                    reason=f"expected {ref.expected_type}, found {exact.symbol_type}",
                )
            return SymbolResolution(ref=ref, status="unresolved", reason="symbol not found")
        if len(matches) > 1:
            return SymbolResolution(
                ref=ref,
                status="ambiguous",
                symbols=matches,
                reason="multiple Python symbols matched",
            )
        return SymbolResolution(ref=ref, status="resolved", symbols=matches)

    def _run_symbol_shape_task(self, task: VerificationTask) -> BackendResult:
        invalid: list[dict[str, str]] = []
        bindings = task.payload.get("bindings", [])
        if not isinstance(bindings, list):
            return BackendResult(
                backend=self.adapter_id,
                status="invalid",
                evidence_level=EvidenceLevel.TYPE_CHECKED,
                details={"task_id": task.id, "reason": "bindings payload must be a list"},
            )
        for raw in bindings:
            if not isinstance(raw, dict):
                invalid.append({"symbol": "<invalid>", "reason": "binding payload must be an object"})
                continue
            symbol_name = str(raw.get("symbol", ""))
            expected_type = str(raw.get("symbol_type", ""))
            symbol = self._symbols.get(symbol_name)
            if symbol is None:
                invalid.append({"symbol": symbol_name, "reason": "symbol not found"})
                continue
            if symbol.symbol_type != expected_type:
                invalid.append(
                    {
                        "symbol": symbol_name,
                        "reason": f"expected {expected_type}, found {symbol.symbol_type}",
                    }
                )
        return BackendResult(
            backend=self.adapter_id,
            status="invalid" if invalid else "valid",
            evidence_level=EvidenceLevel.TYPE_CHECKED,
            details={
                "task_id": task.id,
                "validated_bindings": len(bindings) - len(invalid),
                "invalid_bindings": invalid,
            },
        )

    def _run_pytest_task(self, task: VerificationTask) -> BackendResult:
        paths = task.payload.get("paths", [])
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            return BackendResult(
                backend="pytest",
                status="invalid",
                evidence_level=EvidenceLevel.TEST_VALIDATED,
                details={"task_id": task.id, "reason": "paths payload must be a list of strings"},
            )
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", *paths],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return BackendResult(
            backend="pytest",
            status="valid" if completed.returncode == 0 else "invalid",
            evidence_level=EvidenceLevel.TEST_VALIDATED,
            details={
                "task_id": task.id,
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:],
            },
        )


def _build_symbol_index(package_root: Path, package_name: str) -> dict[str, Symbol]:
    symbols: dict[str, Symbol] = {}
    for source in _python_sources(package_root, package_name):
        _add_symbol(
            symbols,
            name=source.module,
            symbol_type="module",
            metadata={
                "kind": "module",
                "module": source.module,
                "path": source.relative_path,
            },
        )
        for node in source.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _add_function_symbol(symbols, source, node, kind="function")
            if isinstance(node, ast.ClassDef):
                class_name = f"{source.module}.{node.name}"
                _add_symbol(
                    symbols,
                    name=class_name,
                    symbol_type="class",
                    metadata={
                        "kind": "class",
                        "module": source.module,
                        "path": source.relative_path,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                    },
                )
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _add_function_symbol(
                            symbols,
                            source,
                            child,
                            kind="method",
                            owner=class_name,
                        )
    return dict(sorted(symbols.items()))


def _python_sources(package_root: Path, package_name: str) -> list[PythonSource]:
    sources: list[PythonSource] = []
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root)
        if any(part == "__pycache__" or part.startswith(".") for part in relative.parts):
            continue
        module = _module_name(package_name, relative)
        try:
            tree = ast.parse(path.read_text(), filename=str(relative))
        except SyntaxError as exc:
            raise ValueError(f"failed to parse Python source {relative}: {exc}") from exc
        sources.append(PythonSource(module=module, relative_path=str(relative), tree=tree))
    return sources


def _module_name(package_name: str, relative: Path) -> str:
    if relative.name == "__init__.py":
        parts = relative.parent.parts
    else:
        parts = relative.with_suffix("").parts
    if not parts:
        return package_name
    return ".".join((package_name, *parts))


def _add_function_symbol(
    symbols: dict[str, Symbol],
    source: PythonSource,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    kind: str,
    owner: str | None = None,
) -> None:
    name = f"{owner or source.module}.{node.name}"
    _add_symbol(
        symbols,
        name=name,
        symbol_type="function",
        metadata={
            "kind": kind,
            "module": source.module,
            "path": source.relative_path,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "async": isinstance(node, ast.AsyncFunctionDef),
            **({"owner": owner} if owner else {}),
        },
    )


def _add_symbol(
    symbols: dict[str, Symbol],
    *,
    name: str,
    symbol_type: str,
    metadata: dict[str, object],
) -> None:
    symbols[name] = Symbol(name=name, symbol_type=symbol_type, metadata=metadata)


def _matches_symbol_name(symbol_name: str, requested_name: str) -> bool:
    return symbol_name == requested_name or symbol_name.endswith(f".{requested_name}")


def _matches_expected_type(symbol: Symbol, expected_type: str | None) -> bool:
    if expected_type is None:
        return True
    if symbol.symbol_type == expected_type:
        return True
    if expected_type == "action" and symbol.symbol_type == "function":
        return True
    return False
