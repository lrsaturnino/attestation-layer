from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .adoption import (
    build_ci_report,
    build_package_index,
    build_soft_gate_report,
    ci_report_markdown,
    extract_requirement_ids,
    review_checklist_template,
)
from .gate import (
    build_hard_gate_report,
    hard_gate_report_markdown,
    load_gate_policy,
    load_gate_waivers,
)
from .jsonutil import canonical_json
from .models import EvidenceObject, RequirementIR, StatusDecision, SymbolRef
from .openapi_adapter import OpenApiAdapter
from .openapi_package import build_openapi_package, validate_openapi_package
from .package import build_package, validate_package
from .parser import RequirementParser
from .python_package import build_python_package, validate_python_package
from .status import decide_status
from .adapter import default_generic_adapter
from .conformance import AdapterConformanceFixture, assert_adapter_conforms
from .python_adapter import PythonPackageAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nlreq")
    subcommands = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subcommands.add_parser("parse", help="Parse controlled language to AST JSON.")
    parse_cmd.add_argument("file", type=Path)

    ir_cmd = subcommands.add_parser("ir", help="Parse controlled language to IR JSON.")
    ir_cmd.add_argument("file", type=Path)
    ir_cmd.add_argument("--requirement-id", required=True)
    ir_cmd.add_argument("--title", required=True)
    ir_cmd.add_argument("--claim-kind", required=True)

    package_cmd = subcommands.add_parser("package", help="Build a Phase 0 requirement package.")
    package_cmd.add_argument("file", type=Path)
    package_cmd.add_argument("--out", type=Path, required=True)
    package_cmd.add_argument("--requirement-id", required=True)
    package_cmd.add_argument("--title", required=True)
    package_cmd.add_argument("--claim-kind", required=True)

    validate_ir_cmd = subcommands.add_parser("validate-ir", help="Validate IR JSON.")
    validate_ir_cmd.add_argument("file", type=Path)

    validate_cmd = subcommands.add_parser("validate", help="Validate a package directory.")
    validate_cmd.add_argument("package_dir", type=Path)

    validate_all_cmd = subcommands.add_parser(
        "validate-all", help="Validate all package directories under a root."
    )
    validate_all_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))

    status_cmd = subcommands.add_parser("decide-status", help="Compute status from evidence JSON.")
    status_cmd.add_argument("file", type=Path)

    subcommands.add_parser("conformance", help="Run the generic adapter conformance suite.")

    python_conformance_cmd = subcommands.add_parser(
        "python-conformance", help="Run conformance against a Python package adapter."
    )
    python_conformance_cmd.add_argument("package_root", type=Path)
    python_conformance_cmd.add_argument("--package-name")
    python_conformance_cmd.add_argument("--resolved-ref", default="operation")
    python_conformance_cmd.add_argument("--resolved-type", default="action")
    python_conformance_cmd.add_argument("--unresolved-ref", default="definitely_missing_symbol")
    python_conformance_cmd.add_argument("--ambiguous-ref", default="duplicate_symbol")
    python_conformance_cmd.add_argument("--ambiguous-type", default="action")

    openapi_conformance_cmd = subcommands.add_parser(
        "openapi-conformance", help="Run conformance against an OpenAPI adapter."
    )
    openapi_conformance_cmd.add_argument("document", type=Path)
    openapi_conformance_cmd.add_argument("--openapi-name")
    openapi_conformance_cmd.add_argument("--resolved-ref", default="operation")
    openapi_conformance_cmd.add_argument("--resolved-type", default="action")
    openapi_conformance_cmd.add_argument("--unresolved-ref", default="definitely_missing_symbol")
    openapi_conformance_cmd.add_argument("--ambiguous-ref", default="duplicate_operation")
    openapi_conformance_cmd.add_argument("--ambiguous-type", default="action")

    python_package_cmd = subcommands.add_parser(
        "python-package", help="Build a Python-adapter requirement package."
    )
    python_package_cmd.add_argument("file", type=Path)
    python_package_cmd.add_argument("--out", type=Path, required=True)
    python_package_cmd.add_argument("--requirement-id", required=True)
    python_package_cmd.add_argument("--title", required=True)
    python_package_cmd.add_argument("--claim-kind", required=True)
    python_package_cmd.add_argument("--package-root", type=Path, required=True)
    python_package_cmd.add_argument("--package-name")
    python_package_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    python_package_cmd.add_argument("--test-path", action="append", type=Path, default=[])
    python_package_cmd.add_argument(
        "--property-checks",
        action="store_true",
        help="Generate deterministic Python property checks for supported claims.",
    )

    python_validate_cmd = subcommands.add_parser(
        "python-validate", help="Validate a Python-adapter requirement package."
    )
    python_validate_cmd.add_argument("package_dir", type=Path)
    python_validate_cmd.add_argument("--package-root", type=Path, required=True)
    python_validate_cmd.add_argument("--package-name")
    python_validate_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    python_validate_cmd.add_argument("--test-path", action="append", type=Path, default=[])
    python_validate_cmd.add_argument(
        "--property-checks",
        action="store_true",
        help="Recompute deterministic Python property checks for supported claims.",
    )

    openapi_package_cmd = subcommands.add_parser(
        "openapi-package", help="Build an OpenAPI-adapter requirement package."
    )
    openapi_package_cmd.add_argument("file", type=Path)
    openapi_package_cmd.add_argument("--out", type=Path, required=True)
    openapi_package_cmd.add_argument("--requirement-id", required=True)
    openapi_package_cmd.add_argument("--title", required=True)
    openapi_package_cmd.add_argument("--claim-kind", required=True)
    openapi_package_cmd.add_argument("--document", type=Path, required=True)
    openapi_package_cmd.add_argument("--openapi-name")

    openapi_validate_cmd = subcommands.add_parser(
        "openapi-validate", help="Validate an OpenAPI-adapter requirement package."
    )
    openapi_validate_cmd.add_argument("package_dir", type=Path)
    openapi_validate_cmd.add_argument("--document", type=Path, required=True)
    openapi_validate_cmd.add_argument("--openapi-name")

    index_cmd = subcommands.add_parser(
        "package-index", help="Build a report-only index of requirement packages."
    )
    index_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    index_cmd.add_argument("--out", type=Path)
    _add_adapter_validation_options(index_cmd)

    ci_report_cmd = subcommands.add_parser(
        "ci-report", help="Build a shadow-mode CI report for requirement packages."
    )
    ci_report_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    ci_report_cmd.add_argument("--out", type=Path)
    ci_report_cmd.add_argument("--markdown-out", type=Path)
    _add_adapter_validation_options(ci_report_cmd)

    soft_gate_cmd = subcommands.add_parser(
        "soft-gate", help="Run the Phase 4 soft gate against requirement references."
    )
    soft_gate_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    soft_gate_cmd.add_argument("--requirement-id", action="append", default=[])
    soft_gate_cmd.add_argument(
        "--references-file",
        action="append",
        type=Path,
        default=[],
        help="Read requirement references from a PR body, commit message, or report file.",
    )
    soft_gate_cmd.add_argument("--out", type=Path)
    soft_gate_cmd.add_argument("--markdown-out", type=Path)
    soft_gate_cmd.add_argument(
        "--fail-on-blocking",
        action="store_true",
        help="Return non-zero when soft-gate blockers are found.",
    )
    _add_adapter_validation_options(soft_gate_cmd)

    hard_gate_cmd = subcommands.add_parser(
        "hard-gate", help="Run the Phase 5 scoped hard gate against requirement references."
    )
    hard_gate_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    hard_gate_cmd.add_argument("--policy", type=Path, required=True)
    hard_gate_cmd.add_argument("--waiver", action="append", type=Path, default=[])
    hard_gate_cmd.add_argument("--requirement-id", action="append", default=[])
    hard_gate_cmd.add_argument(
        "--references-file",
        action="append",
        type=Path,
        default=[],
        help="Read requirement references from a PR body, commit message, or report file.",
    )
    hard_gate_cmd.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help="Changed implementation path used for policy scope matching.",
    )
    hard_gate_cmd.add_argument(
        "--changed-paths-file",
        action="append",
        type=Path,
        default=[],
        help="Read changed implementation paths from a newline-delimited file.",
    )
    hard_gate_cmd.add_argument("--out", type=Path)
    hard_gate_cmd.add_argument("--markdown-out", type=Path)
    _add_adapter_validation_options(hard_gate_cmd)

    review_template_cmd = subcommands.add_parser(
        "review-template", help="Render the human review checklist template."
    )
    review_template_cmd.add_argument("requirement_id", nargs="?")
    review_template_cmd.add_argument("--out", type=Path)

    args = parser.parse_args(argv)

    try:
        if args.command == "parse":
            print(canonical_json(RequirementParser().parse(args.file.read_text())))
            return 0
        if args.command == "ir":
            ir = RequirementParser().parse_ir(
                args.file.read_text(),
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
            )
            print(canonical_json(ir))
            return 0
        if args.command == "package":
            build_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "validate-ir":
            RequirementIR.model_validate_json(args.file.read_text())
            print("IR: valid")
            return 0
        if args.command == "validate":
            ir, evidence, status = validate_package(args.package_dir)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "validate-all":
            summaries = []
            package_dirs = _package_dirs(args.packages_dir)
            if not package_dirs:
                raise ValueError(f"no package directories found under {args.packages_dir}")
            for package_dir in package_dirs:
                ir, evidence, status = validate_package(package_dir)
                summaries.append((ir.requirement_id, status.status.value))
            print(f"Packages: {len(summaries)} valid")
            for requirement_id, status_value in summaries:
                print(f"  - {requirement_id}: {status_value}")
            return 0
        if args.command == "decide-status":
            evidence = EvidenceObject.model_validate_json(args.file.read_text())
            print(canonical_json(decide_status(evidence)))
            return 0
        if args.command == "conformance":
            report = assert_adapter_conforms(default_generic_adapter(), _generic_conformance_fixture())
            print(f"Adapter: {report.adapter_id}")
            print(f"Target: {report.target_kind}")
            print("Conformance: passed")
            for check in report.checks:
                print(f"  - {check}")
            return 0
        if args.command == "python-conformance":
            adapter = PythonPackageAdapter(
                args.package_root,
                package_name=args.package_name or args.package_root.name,
            )
            report = assert_adapter_conforms(
                adapter,
                _python_conformance_fixture(
                    resolved_ref=args.resolved_ref,
                    resolved_type=args.resolved_type,
                    unresolved_ref=args.unresolved_ref,
                    ambiguous_ref=args.ambiguous_ref,
                    ambiguous_type=args.ambiguous_type,
                ),
            )
            print(f"Adapter: {report.adapter_id}")
            print(f"Target: {report.target_kind}")
            print(f"Package: {adapter.package_name}")
            print("Conformance: passed")
            for check in report.checks:
                print(f"  - {check}")
            return 0
        if args.command == "openapi-conformance":
            adapter = OpenApiAdapter(
                args.document,
                document_name=args.openapi_name or args.document.stem,
            )
            report = assert_adapter_conforms(
                adapter,
                _openapi_conformance_fixture(
                    resolved_ref=args.resolved_ref,
                    resolved_type=args.resolved_type,
                    unresolved_ref=args.unresolved_ref,
                    ambiguous_ref=args.ambiguous_ref,
                    ambiguous_type=args.ambiguous_type,
                ),
            )
            print(f"Adapter: {report.adapter_id}")
            print(f"Target: {report.target_kind}")
            print(f"Document: {adapter.document_name}")
            print("Conformance: passed")
            for check in report.checks:
                print(f"  - {check}")
            return 0
        if args.command == "python-package":
            adapter = PythonPackageAdapter(
                args.package_root,
                package_name=args.package_name or args.package_root.name,
                project_root=args.project_root,
                test_paths=args.test_path,
                property_checks=args.property_checks,
            )
            build_python_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "python-validate":
            adapter = PythonPackageAdapter(
                args.package_root,
                package_name=args.package_name or args.package_root.name,
                project_root=args.project_root,
                test_paths=args.test_path,
                property_checks=args.property_checks,
            )
            ir, evidence, status = validate_python_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "openapi-package":
            adapter = OpenApiAdapter(
                args.document,
                document_name=args.openapi_name or args.document.stem,
            )
            build_openapi_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "openapi-validate":
            adapter = OpenApiAdapter(
                args.document,
                document_name=args.openapi_name or args.document.stem,
            )
            ir, evidence, status = validate_openapi_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "package-index":
            package_index = build_package_index(
                args.packages_dir,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
            )
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, package_index)
                print(f"Package index: {args.out}")
            else:
                print(canonical_json(package_index), end="")
            return 0
        if args.command == "ci-report":
            report = build_ci_report(
                args.packages_dir,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, report)
                print(f"CI report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(ci_report_markdown(report))
                print(f"CI report markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0
        if args.command == "soft-gate":
            requirement_ids = _requirement_ids_from_args(args)
            report = build_soft_gate_report(
                args.packages_dir,
                requirement_ids=requirement_ids,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, report)
                print(f"Soft gate report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(ci_report_markdown(report))
                print(f"Soft gate report markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            if args.fail_on_blocking and report["result"] == "blocked":
                return 1
            return 0
        if args.command == "hard-gate":
            requirement_ids = _requirement_ids_from_args(args)
            report = build_hard_gate_report(
                args.packages_dir,
                requirement_ids=requirement_ids,
                policy=load_gate_policy(args.policy),
                waivers=load_gate_waivers(args.waiver),
                changed_paths=_changed_paths_from_args(args),
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, report)
                print(f"Hard gate report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(hard_gate_report_markdown(report))
                print(f"Hard gate report markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 1 if report["result"] == "blocked" else 0
        if args.command == "review-template":
            template = review_checklist_template(args.requirement_id)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(template)
                print(f"Review checklist: {args.out}")
            else:
                print(template, end="")
            return 0
    except (OSError, ValidationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1


def _add_adapter_validation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--python-package-root", type=Path)
    parser.add_argument("--package-name")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--test-path", action="append", type=Path, default=[])
    parser.add_argument(
        "--property-checks",
        action="store_true",
        help="Enable deterministic Python property checks for package validation.",
    )
    parser.add_argument("--openapi-document", type=Path)
    parser.add_argument("--openapi-name")


def _optional_python_adapter(args: argparse.Namespace) -> PythonPackageAdapter | None:
    if args.python_package_root is None:
        return None
    return PythonPackageAdapter(
        args.python_package_root,
        package_name=args.package_name or args.python_package_root.name,
        project_root=args.project_root,
        test_paths=args.test_path,
        property_checks=args.property_checks,
    )


def _optional_openapi_adapter(args: argparse.Namespace) -> OpenApiAdapter | None:
    if args.openapi_document is None:
        return None
    return OpenApiAdapter(
        args.openapi_document,
        document_name=args.openapi_name or args.openapi_document.stem,
    )


def _requirement_ids_from_args(args: argparse.Namespace) -> list[str]:
    requirement_ids = list(args.requirement_id)
    for references_file in args.references_file:
        requirement_ids.extend(extract_requirement_ids(references_file.read_text()))
    seen: set[str] = set()
    unique: list[str] = []
    for requirement_id in requirement_ids:
        if requirement_id not in seen:
            unique.append(requirement_id)
            seen.add(requirement_id)
    return unique


def _changed_paths_from_args(args: argparse.Namespace) -> list[str]:
    changed_paths = list(args.changed_path)
    for changed_paths_file in args.changed_paths_file:
        changed_paths.extend(
            line.strip()
            for line in changed_paths_file.read_text().splitlines()
            if line.strip()
        )
    seen: set[str] = set()
    unique: list[str] = []
    for changed_path in changed_paths:
        if changed_path not in seen:
            unique.append(changed_path)
            seen.add(changed_path)
    return unique


def _line_for_evidence(evidence: EvidenceObject, claim_id: str, label: str) -> str:
    for claim in evidence.claims:
        if claim.id == claim_id:
            return f"{label}: {'checked' if claim.achieved_evidence else 'missing'}"
    return f"{label}: missing"


def _package_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if (path / "requirement.ir.json").is_file())


def _print_package_validation(ir: RequirementIR, evidence: EvidenceObject, status: StatusDecision) -> None:
    print(f"Requirement: {ir.requirement_id}")
    print("IR: valid")
    if evidence.ambiguous_symbols:
        print("Bindings: ambiguous")
    else:
        print("Bindings: valid" if not evidence.unbound_symbols else "Bindings: invalid")
    print(_line_for_evidence(evidence, "C-consistency", "Consistency"))
    print(_line_for_evidence(evidence, "C-smt", "SMT"))
    print(f"Status: {status.status.value}")
    if status.source_span:
        print(f'Fragment: "{status.source_span.text}"')
    if status.next_actions:
        print("Next:")
        for action in status.next_actions:
            print(f"  - {action}")


def _generic_conformance_fixture() -> AdapterConformanceFixture:
    ir = RequirementParser().parse_ir(
        (
            "For every operation request:\n"
            "if actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        requirement_id="REQ-CONFORMANCE-001",
        title="Generic adapter conformance fixture",
        claim_kind="authorization_precondition",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name="operation", expected_type="action"),
        unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
        ambiguous_ref=SymbolRef(name="ambiguous_operation", expected_type="action"),
        sample_ir=ir,
    )


def _python_conformance_fixture(
    *,
    resolved_ref: str = "operation",
    resolved_type: str = "action",
    unresolved_ref: str = "definitely_missing_symbol",
    ambiguous_ref: str = "duplicate_symbol",
    ambiguous_type: str = "action",
) -> AdapterConformanceFixture:
    ir = RequirementParser().parse_ir(
        (
            "For every operation request:\n"
            "if actor is approved\n"
            "then operation must succeed.\n"
        ),
        requirement_id="REQ-PY-CONFORMANCE-001",
        title="Python adapter conformance fixture",
        claim_kind="state_precondition",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name=resolved_ref, expected_type=resolved_type),
        unresolved_ref=SymbolRef(name=unresolved_ref),
        ambiguous_ref=SymbolRef(name=ambiguous_ref, expected_type=ambiguous_type),
        sample_ir=ir,
    )


def _openapi_conformance_fixture(
    *,
    resolved_ref: str = "operation",
    resolved_type: str = "action",
    unresolved_ref: str = "definitely_missing_symbol",
    ambiguous_ref: str = "duplicate_operation",
    ambiguous_type: str = "action",
) -> AdapterConformanceFixture:
    ir = RequirementParser().parse_ir(
        (
            "For every operation request:\n"
            "if actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        requirement_id="REQ-OPENAPI-CONFORMANCE-001",
        title="OpenAPI adapter conformance fixture",
        claim_kind="authorization_precondition",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name=resolved_ref, expected_type=resolved_type),
        unresolved_ref=SymbolRef(name=unresolved_ref),
        ambiguous_ref=SymbolRef(name=ambiguous_ref, expected_type=ambiguous_type),
        sample_ir=ir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
