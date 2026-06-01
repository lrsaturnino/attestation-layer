from pathlib import Path

from nlreq.javascript_source_adapter import JavaScriptSourceLanguageAdapter
from nlreq.models import SymbolRef
from nlreq.python_source_adapter import PythonSourceLanguageAdapter
from nlreq.source_adapter import SourceManifest
from nlreq.source_conformance import (
    SourceAdapterConformanceFixture,
    assert_source_adapter_conforms,
)


def test_python_and_javascript_source_adapters_share_conformance_suite(
    tmp_path: Path,
) -> None:
    python_root = tmp_path / "python"
    javascript_root = tmp_path / "javascript"
    python_manifest = _python_project(python_root)
    javascript_manifest = _javascript_project(javascript_root)

    python_report = assert_source_adapter_conforms(
        PythonSourceLanguageAdapter(project_root=python_root),
        _fixture(python_manifest, ambiguous_ref="duplicate_symbol"),
    )
    javascript_report = assert_source_adapter_conforms(
        JavaScriptSourceLanguageAdapter(project_root=javascript_root),
        _fixture(javascript_manifest, ambiguous_ref="duplicateSymbol"),
    )

    assert python_report.checks == javascript_report.checks
    assert python_report.adapter_id == "python-source"
    assert javascript_report.adapter_id == "javascript-source"


def _fixture(
    manifest: SourceManifest, *, ambiguous_ref: str
) -> SourceAdapterConformanceFixture:
    return SourceAdapterConformanceFixture(
        manifest=manifest,
        resolved_ref=SymbolRef(name="operation"),
        unresolved_ref=SymbolRef(name="missingOperation"),
        ambiguous_ref=SymbolRef(name=ambiguous_ref),
    )


def _python_project(root: Path) -> SourceManifest:
    src = root / "src"
    src.mkdir(parents=True)
    (src / "auth.py").write_text(
        "from state import state_change\n\n"
        "def operation(actor):\n"
        "    return state_change(actor)\n\n"
        "def duplicate_symbol():\n"
        "    return 'auth'\n"
    )
    (src / "state.py").write_text(
        "def state_change(actor):\n"
        "    return actor\n\n"
        "def duplicate_symbol():\n"
        "    return 'state'\n"
    )
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "python-source",
            "language": "python",
            "runtime": "cpython",
            "modules": [
                {
                    "module_id": "auth",
                    "path": "src/auth.py",
                    "symbols": ["operation", "duplicate_symbol"],
                },
                {
                    "module_id": "state",
                    "path": "src/state.py",
                    "symbols": ["state_change", "duplicate_symbol"],
                },
            ],
        }
    )


def _javascript_project(root: Path) -> SourceManifest:
    src = root / "src"
    src.mkdir(parents=True)
    (src / "auth.js").write_text(
        "import { stateChange } from './state.js';\n\n"
        "export function operation(actor) {\n"
        "  return stateChange(actor);\n"
        "}\n\n"
        "export function duplicateSymbol() {\n"
        "  return 'auth';\n"
        "}\n"
    )
    (src / "state.js").write_text(
        "export function stateChange(actor) {\n"
        "  return actor;\n"
        "}\n\n"
        "export function duplicateSymbol() {\n"
        "  return 'state';\n"
        "}\n"
    )
    return SourceManifest.model_validate(
        {
            "schema_version": "0.1",
            "adapter": "javascript-source",
            "language": "javascript",
            "runtime": "node",
            "modules": [
                {
                    "module_id": "auth",
                    "path": "src/auth.js",
                    "symbols": ["operation", "duplicateSymbol"],
                },
                {
                    "module_id": "state",
                    "path": "src/state.js",
                    "symbols": ["stateChange", "duplicateSymbol"],
                },
            ],
        }
    )
