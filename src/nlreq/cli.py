from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .agent_workflow import (
    agent_pr_comment_markdown,
    append_agent_audit_entry,
    build_agent_audit_entry,
    build_agent_implementation_task,
    build_agent_verifier_handoff,
    load_continuous_run,
    package_input_refs,
)
from .adoption import (
    build_ci_report,
    build_package_index,
    build_soft_gate_report,
    ci_report_markdown,
    extract_requirement_ids,
    review_checklist_template,
)
from .command_adapter import CommandAdapter, CommandChecksArtifact, load_command_checks
from .command_package import (
    build_command_package,
    command_results_markdown,
    run_command_evidence,
    validate_command_package,
)
from .continuous import (
    build_attestation_run,
    continuous_attestation_markdown,
    load_attestation_run,
)
from .gate import (
    build_hard_gate_report,
    hard_gate_report_markdown,
    load_gate_policy,
    load_gate_waivers,
)
from .graphql_adapter import GraphQlAdapter
from .graphql_package import build_graphql_package, validate_graphql_package
from .jsonutil import canonical_json, read_json
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
from .routing import (
    AdapterRegistryArtifact,
    RoutingPolicyArtifact,
    build_routing_report,
    load_adapter_registry,
    load_routing_policy,
    routing_report_markdown,
)
from .trace_validation import build_trace_validation_report, trace_validation_markdown
from .tla_adapter import TlaAdapter, load_tla_model_config
from .tla_package import (
    build_tla_package,
    run_tla_checks,
    tla_results_markdown,
    validate_tla_package,
)


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

    graphql_conformance_cmd = subcommands.add_parser(
        "graphql-conformance", help="Run conformance against a GraphQL schema adapter."
    )
    graphql_conformance_cmd.add_argument("schema", type=Path)
    graphql_conformance_cmd.add_argument("--graphql-name")
    graphql_conformance_cmd.add_argument("--resolved-ref", default="operation")
    graphql_conformance_cmd.add_argument("--resolved-type", default="action")
    graphql_conformance_cmd.add_argument("--unresolved-ref", default="definitely_missing_symbol")
    graphql_conformance_cmd.add_argument("--ambiguous-ref", default="duplicate_operation")
    graphql_conformance_cmd.add_argument("--ambiguous-type", default="action")

    graphql_package_cmd = subcommands.add_parser(
        "graphql-package", help="Build a GraphQL-adapter requirement package."
    )
    graphql_package_cmd.add_argument("file", type=Path)
    graphql_package_cmd.add_argument("--out", type=Path, required=True)
    graphql_package_cmd.add_argument("--requirement-id", required=True)
    graphql_package_cmd.add_argument("--title", required=True)
    graphql_package_cmd.add_argument("--claim-kind", required=True)
    graphql_package_cmd.add_argument("--schema", type=Path, required=True)
    graphql_package_cmd.add_argument("--graphql-name")

    graphql_validate_cmd = subcommands.add_parser(
        "graphql-validate", help="Validate a GraphQL-adapter requirement package."
    )
    graphql_validate_cmd.add_argument("package_dir", type=Path)
    graphql_validate_cmd.add_argument("--schema", type=Path, required=True)
    graphql_validate_cmd.add_argument("--graphql-name")

    command_package_cmd = subcommands.add_parser(
        "command-package", help="Build a command/test-runner-backed requirement package."
    )
    command_package_cmd.add_argument("file", type=Path)
    command_package_cmd.add_argument("--out", type=Path, required=True)
    command_package_cmd.add_argument("--requirement-id", required=True)
    command_package_cmd.add_argument("--title", required=True)
    command_package_cmd.add_argument("--claim-kind", required=True)
    command_package_cmd.add_argument("--checks", type=Path, required=True)
    command_package_cmd.add_argument("--project-root", type=Path, default=Path.cwd())

    command_validate_cmd = subcommands.add_parser(
        "command-validate", help="Validate a command/test-runner-backed package."
    )
    command_validate_cmd.add_argument("package_dir", type=Path)
    command_validate_cmd.add_argument("--checks", type=Path, required=True)
    command_validate_cmd.add_argument("--project-root", type=Path, default=Path.cwd())

    command_evidence_cmd = subcommands.add_parser(
        "command-evidence", help="Run configured command checks and write result artifacts."
    )
    command_evidence_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    command_evidence_cmd.add_argument("--checks", type=Path, required=True)
    command_evidence_cmd.add_argument("--requirement-id", action="append", default=[])
    command_evidence_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    command_evidence_cmd.add_argument("--out", type=Path)
    command_evidence_cmd.add_argument("--markdown-out", type=Path)

    subcommands.add_parser(
        "command-conformance", help="Run conformance against the command/test-runner adapter."
    )

    tla_package_cmd = subcommands.add_parser(
        "tla-package", help="Build a TLA/model-checking-backed requirement package."
    )
    tla_package_cmd.add_argument("file", type=Path)
    tla_package_cmd.add_argument("--out", type=Path, required=True)
    tla_package_cmd.add_argument("--requirement-id", required=True)
    tla_package_cmd.add_argument("--title", required=True)
    tla_package_cmd.add_argument("--claim-kind", required=True)
    tla_package_cmd.add_argument("--model-config", type=Path, required=True)
    tla_package_cmd.add_argument("--project-root", type=Path, default=Path.cwd())

    tla_validate_cmd = subcommands.add_parser(
        "tla-validate", help="Validate a TLA/model-checking-backed package."
    )
    tla_validate_cmd.add_argument("package_dir", type=Path)
    tla_validate_cmd.add_argument("--model-config", type=Path, required=True)
    tla_validate_cmd.add_argument("--project-root", type=Path, default=Path.cwd())

    tla_check_cmd = subcommands.add_parser(
        "tla-check", help="Run configured TLA model checks and write result artifacts."
    )
    tla_check_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    tla_check_cmd.add_argument("--model-config", type=Path, required=True)
    tla_check_cmd.add_argument("--requirement-id", action="append", default=[])
    tla_check_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    tla_check_cmd.add_argument("--out", type=Path)
    tla_check_cmd.add_argument("--markdown-out", type=Path)

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

    continuous_cmd = subcommands.add_parser(
        "continuous-attestation",
        help="Build a Phase 8 continuous attestation run report.",
    )
    continuous_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    continuous_cmd.add_argument(
        "--trigger",
        choices=["manual", "schedule", "webhook", "release"],
        default="manual",
    )
    continuous_cmd.add_argument("--run-id")
    continuous_cmd.add_argument("--timestamp")
    continuous_cmd.add_argument("--repo-ref")
    continuous_cmd.add_argument("--previous-run", type=Path)
    continuous_cmd.add_argument("--trace-artifact", action="append", type=Path, default=[])
    continuous_cmd.add_argument(
        "--trace-validation",
        action="store_true",
        help="Validate normalized trace artifacts against supported requirement claims.",
    )
    continuous_cmd.add_argument("--out", type=Path)
    continuous_cmd.add_argument("--markdown-out", type=Path)
    _add_adapter_validation_options(continuous_cmd)

    trace_validate_cmd = subcommands.add_parser(
        "trace-validate", help="Validate normalized runtime traces against requirement packages."
    )
    trace_validate_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    trace_validate_cmd.add_argument("--requirement-id", action="append", default=[])
    trace_validate_cmd.add_argument("--trace-artifact", action="append", type=Path, required=True)
    trace_validate_cmd.add_argument("--out", type=Path)
    trace_validate_cmd.add_argument("--markdown-out", type=Path)

    validate_registry_cmd = subcommands.add_parser(
        "validate-adapter-registry", help="Validate an adapter registry JSON artifact."
    )
    validate_registry_cmd.add_argument("file", type=Path)

    validate_routing_policy_cmd = subcommands.add_parser(
        "validate-routing-policy", help="Validate a routing policy JSON artifact."
    )
    validate_routing_policy_cmd.add_argument("file", type=Path)

    route_adapters_cmd = subcommands.add_parser(
        "route-adapters", help="Build a deterministic adapter routing report."
    )
    route_adapters_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    route_adapters_cmd.add_argument("--adapter-registry", type=Path, required=True)
    route_adapters_cmd.add_argument("--routing-policy", type=Path, required=True)
    route_adapters_cmd.add_argument("--changed-path", action="append", default=[])
    route_adapters_cmd.add_argument("--changed-paths-file", action="append", type=Path, default=[])
    route_adapters_cmd.add_argument("--requirement-id", action="append", default=[])
    route_adapters_cmd.add_argument("--out", type=Path)
    route_adapters_cmd.add_argument("--markdown-out", type=Path)

    agent_task_cmd = subcommands.add_parser(
        "agent-task",
        help="Build a Phase 9 implementation task payload for coder agents.",
    )
    agent_task_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    agent_task_cmd.add_argument("--requirement-id", action="append", default=[])
    agent_task_cmd.add_argument("--references-file", action="append", type=Path, default=[])
    agent_task_cmd.add_argument("--workflow-id")
    agent_task_cmd.add_argument("--step-id")
    agent_task_cmd.add_argument("--allowed-path", action="append", default=[])
    agent_task_cmd.add_argument("--reviewer-constraint", action="append", default=[])
    agent_task_cmd.add_argument("--out", type=Path)
    _add_adapter_validation_options(agent_task_cmd)

    agent_verify_cmd = subcommands.add_parser(
        "agent-verify",
        help="Build a Phase 9 verifier handoff and retry payloads.",
    )
    agent_verify_cmd.add_argument("packages_dir", nargs="?", type=Path, default=Path("requirements"))
    agent_verify_cmd.add_argument("--requirement-id", action="append", default=[])
    agent_verify_cmd.add_argument("--references-file", action="append", type=Path, default=[])
    agent_verify_cmd.add_argument("--workflow-id")
    agent_verify_cmd.add_argument("--step-id")
    agent_verify_cmd.add_argument("--policy", type=Path)
    agent_verify_cmd.add_argument("--waiver", action="append", type=Path, default=[])
    agent_verify_cmd.add_argument("--changed-path", action="append", default=[])
    agent_verify_cmd.add_argument("--changed-paths-file", action="append", type=Path, default=[])
    agent_verify_cmd.add_argument("--continuous-run", type=Path)
    agent_verify_cmd.add_argument("--out", type=Path)
    agent_verify_cmd.add_argument("--markdown-out", type=Path)
    _add_adapter_validation_options(agent_verify_cmd)

    agent_comment_cmd = subcommands.add_parser(
        "agent-pr-comment",
        help="Render a Phase 9 verifier handoff as PR Markdown.",
    )
    agent_comment_cmd.add_argument("handoff", type=Path)
    agent_comment_cmd.add_argument("--out", type=Path)

    agent_audit_cmd = subcommands.add_parser(
        "agent-audit",
        help="Append a Phase 9 agent audit log entry.",
    )
    agent_audit_cmd.add_argument("--log", type=Path, required=True)
    agent_audit_cmd.add_argument("--workflow-id", required=True)
    agent_audit_cmd.add_argument("--step-id", required=True)
    agent_audit_cmd.add_argument(
        "--agent-role",
        choices=["specifier", "coder", "verifier", "reviewer"],
        required=True,
    )
    agent_audit_cmd.add_argument("--tool", required=True)
    agent_audit_cmd.add_argument("--input-package", action="append", type=Path, default=[])
    agent_audit_cmd.add_argument("--output-artifact", action="append", type=Path, default=[])
    agent_audit_cmd.add_argument("--git-ref")
    agent_audit_cmd.add_argument("--decision-status")
    agent_audit_cmd.add_argument("--decision-summary")
    agent_audit_cmd.add_argument("--human-approval", action="append", default=[])

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
        if args.command == "graphql-conformance":
            adapter = GraphQlAdapter(
                args.schema,
                schema_name=args.graphql_name or args.schema.stem,
            )
            report = assert_adapter_conforms(
                adapter,
                _graphql_conformance_fixture(
                    resolved_ref=args.resolved_ref,
                    resolved_type=args.resolved_type,
                    unresolved_ref=args.unresolved_ref,
                    ambiguous_ref=args.ambiguous_ref,
                    ambiguous_type=args.ambiguous_type,
                ),
            )
            print(f"Adapter: {report.adapter_id}")
            print(f"Target: {report.target_kind}")
            print(f"Schema: {adapter.schema_name}")
            print("Conformance: passed")
            for check in report.checks:
                print(f"  - {check}")
            return 0
        if args.command == "graphql-package":
            adapter = GraphQlAdapter(
                args.schema,
                schema_name=args.graphql_name or args.schema.stem,
            )
            build_graphql_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "graphql-validate":
            adapter = GraphQlAdapter(
                args.schema,
                schema_name=args.graphql_name or args.schema.stem,
            )
            ir, evidence, status = validate_graphql_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "command-package":
            adapter = CommandAdapter(
                load_command_checks(args.checks),
                project_root=args.project_root,
            )
            build_command_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "command-validate":
            adapter = CommandAdapter(
                load_command_checks(args.checks),
                project_root=args.project_root,
            )
            ir, evidence, status = validate_command_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "command-evidence":
            adapter = CommandAdapter(
                load_command_checks(args.checks),
                project_root=args.project_root,
            )
            results = run_command_evidence(
                args.packages_dir,
                adapter=adapter,
                requirement_ids=args.requirement_id,
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, results)
                print(f"Command evidence: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(command_results_markdown(results))
                print(f"Command evidence markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(results), end="")
            return 0
        if args.command == "command-conformance":
            adapter = CommandAdapter(_command_conformance_checks())
            report = assert_adapter_conforms(adapter, _command_conformance_fixture())
            print(f"Adapter: {report.adapter_id}")
            print(f"Target: {report.target_kind}")
            print("Conformance: passed")
            for check in report.checks:
                print(f"  - {check}")
            return 0
        if args.command == "tla-package":
            adapter = TlaAdapter(
                load_tla_model_config(args.model_config),
                project_root=args.project_root,
            )
            build_tla_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "tla-validate":
            adapter = TlaAdapter(
                load_tla_model_config(args.model_config),
                project_root=args.project_root,
            )
            ir, evidence, status = validate_tla_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "tla-check":
            adapter = TlaAdapter(
                load_tla_model_config(args.model_config),
                project_root=args.project_root,
            )
            results = run_tla_checks(
                args.packages_dir,
                adapter=adapter,
                requirement_ids=args.requirement_id,
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, results)
                print(f"TLA model-checking results: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(tla_results_markdown(results))
                print(f"TLA model-checking markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(results), end="")
            return 0
        if args.command == "package-index":
            package_index = build_package_index(
                args.packages_dir,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
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
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
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
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
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
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
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
        if args.command == "continuous-attestation":
            report = build_attestation_run(
                args.packages_dir,
                trigger=args.trigger,
                run_id=args.run_id,
                timestamp=args.timestamp,
                repo_ref=args.repo_ref,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
                trace_artifact_paths=args.trace_artifact,
                trace_validation=args.trace_validation,
                previous_run=load_attestation_run(args.previous_run)
                if args.previous_run
                else None,
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, report)
                print(f"Continuous attestation report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(continuous_attestation_markdown(report))
                print(f"Continuous attestation markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0
        if args.command == "trace-validate":
            report = build_trace_validation_report(
                args.packages_dir,
                requirement_ids=args.requirement_id,
                trace_artifact_paths=args.trace_artifact,
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, report)
                print(f"Trace validation report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(trace_validation_markdown(report))
                print(f"Trace validation markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0
        if args.command == "validate-adapter-registry":
            AdapterRegistryArtifact.model_validate_json(args.file.read_text())
            print("Adapter registry: valid")
            return 0
        if args.command == "validate-routing-policy":
            RoutingPolicyArtifact.model_validate_json(args.file.read_text())
            print("Routing policy: valid")
            return 0
        if args.command == "route-adapters":
            report = build_routing_report(
                args.packages_dir,
                registry=load_adapter_registry(args.adapter_registry),
                policy=load_routing_policy(args.routing_policy),
                changed_paths=_changed_paths_from_args(args),
                requirement_ids=args.requirement_id,
                registry_path=args.adapter_registry,
                policy_path=args.routing_policy,
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, report)
                print(f"Adapter routing report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(routing_report_markdown(report))
                print(f"Adapter routing markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0
        if args.command == "agent-task":
            requirement_ids = _requirement_ids_from_args(args)
            task = build_agent_implementation_task(
                args.packages_dir,
                requirement_ids=requirement_ids,
                workflow_id=args.workflow_id,
                step_id=args.step_id,
                allowed_paths=args.allowed_path,
                reviewer_constraints=args.reviewer_constraint,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
            )
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, task)
                print(f"Agent implementation task: {args.out}")
            else:
                print(canonical_json(task), end="")
            return 0
        if args.command == "agent-verify":
            requirement_ids = _requirement_ids_from_args(args)
            handoff = build_agent_verifier_handoff(
                args.packages_dir,
                requirement_ids=requirement_ids,
                workflow_id=args.workflow_id,
                step_id=args.step_id,
                python_adapter=_optional_python_adapter(args),
                openapi_adapter=_optional_openapi_adapter(args),
                command_adapter=_optional_command_adapter(args),
                tla_adapter=_optional_tla_adapter(args),
                graphql_adapter=_optional_graphql_adapter(args),
                hard_gate_policy=load_gate_policy(args.policy) if args.policy else None,
                hard_gate_waivers=load_gate_waivers(args.waiver) if args.policy else [],
                changed_paths=_changed_paths_from_args(args),
                continuous_run=load_continuous_run(args.continuous_run),
            )
            wrote_output = False
            if args.out:
                from .jsonutil import write_json

                write_json(args.out, handoff)
                print(f"Agent verifier handoff: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(agent_pr_comment_markdown(handoff))
                print(f"Agent verifier markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(handoff), end="")
            return 0
        if args.command == "agent-pr-comment":
            handoff = read_json(args.handoff)
            markdown = agent_pr_comment_markdown(handoff)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(markdown)
                print(f"Agent PR comment: {args.out}")
            else:
                print(markdown, end="")
            return 0
        if args.command == "agent-audit":
            entry = build_agent_audit_entry(
                workflow_id=args.workflow_id,
                step_id=args.step_id,
                agent_role=args.agent_role,
                tool=args.tool,
                input_packages=package_input_refs(args.input_package),
                output_artifact_paths=args.output_artifact,
                git_ref=args.git_ref,
                decision={
                    key: value
                    for key, value in {
                        "status": args.decision_status,
                        "summary": args.decision_summary,
                    }.items()
                    if value is not None
                },
                human_approvals=[
                    {"approval": approval} for approval in args.human_approval
                ],
            )
            entries = append_agent_audit_entry(args.log, entry)
            print(f"Agent audit log: {args.log}")
            print(f"Entries: {len(entries)}")
            return 0
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
    parser.add_argument("--graphql-schema", type=Path)
    parser.add_argument("--graphql-name")
    parser.add_argument("--command-checks", type=Path)
    parser.add_argument("--tla-model-config", type=Path)


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


def _optional_graphql_adapter(args: argparse.Namespace) -> GraphQlAdapter | None:
    if args.graphql_schema is None:
        return None
    return GraphQlAdapter(
        args.graphql_schema,
        schema_name=args.graphql_name or args.graphql_schema.stem,
    )


def _optional_command_adapter(args: argparse.Namespace) -> CommandAdapter | None:
    if args.command_checks is None:
        return None
    return CommandAdapter(
        load_command_checks(args.command_checks),
        project_root=args.project_root,
    )


def _optional_tla_adapter(args: argparse.Namespace) -> TlaAdapter | None:
    if args.tla_model_config is None:
        return None
    return TlaAdapter(
        load_tla_model_config(args.tla_model_config),
        project_root=args.project_root,
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


def _graphql_conformance_fixture(
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
        requirement_id="REQ-GRAPHQL-CONFORMANCE-001",
        title="GraphQL adapter conformance fixture",
        claim_kind="authorization_precondition",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name=resolved_ref, expected_type=resolved_type),
        unresolved_ref=SymbolRef(name=unresolved_ref),
        ambiguous_ref=SymbolRef(name=ambiguous_ref, expected_type=ambiguous_type),
        sample_ir=ir,
    )


def _command_conformance_fixture() -> AdapterConformanceFixture:
    ir = RequirementParser().parse_ir(
        (
            "For every operation request:\n"
            "if actor is not authorized\n"
            "then operation must be rejected before state_change.\n"
        ),
        requirement_id="REQ-COMMAND-CONFORMANCE-001",
        title="Command adapter conformance fixture",
        claim_kind="authorization_precondition",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name="operation", expected_type="action"),
        unresolved_ref=SymbolRef(name="definitely_missing_symbol"),
        ambiguous_ref=SymbolRef(name="ambiguous_operation", expected_type="action"),
        sample_ir=ir,
    )


def _command_conformance_checks() -> CommandChecksArtifact:
    return CommandChecksArtifact.model_validate(
        {
            "checks": [
                {
                    "check_id": "CMD-CONFORMANCE",
                    "name": "Command adapter conformance check",
                    "requirement_ids": ["REQ-COMMAND-CONFORMANCE-001"],
                    "command": [sys.executable, "-m", "nlreq.cli", "conformance"],
                    "cwd": ".",
                    "timeout_seconds": 60,
                    "expected_exit_code": 0,
                    "target_paths": [],
                    "test_paths": [],
                    "requested_evidence": "TEST_VALIDATED",
                }
            ]
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
