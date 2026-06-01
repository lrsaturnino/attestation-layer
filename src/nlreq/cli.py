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
from .agnostic_wedge import build_agnostic_wedge_report
from .adoption import (
    build_ci_report,
    build_package_index,
    build_soft_gate_report,
    ci_report_markdown,
    extract_requirement_ids,
    review_checklist_template,
)
from .asyncapi_adapter import AsyncApiAdapter
from .asyncapi_package import build_asyncapi_package, validate_asyncapi_package
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
from .coverage_alignment import build_spec_coverage_report, build_trace_alignment_report
from .compositional_ir import (
    DEFAULT_MIGRATION_TIMESTAMP,
    DEFAULT_MIGRATION_TOOL_VERSION,
    migrate_requirement_ir_v1_to_v2,
    validate_requirement_ir_json,
)
from .formal_backend import (
    FormalBackendBudget,
    FormalBackendExecution,
    build_formal_backend_request,
    check_formal_backend,
)
from .dsl_v2 import DslV2Parser
from .gate import (
    build_hard_gate_report,
    hard_gate_report_markdown,
    load_gate_policy,
    load_gate_waivers,
)
from .graphql_adapter import GraphQlAdapter
from .graphql_package import build_graphql_package, validate_graphql_package
from .impact import analyze_source_impact
from .jsonschema_adapter import JsonSchemaAdapter
from .jsonschema_package import build_json_schema_package, validate_json_schema_package
from .jsonutil import canonical_json, read_json
from .model_checker_runner import (
    DEFAULT_OUTPUT_LIMIT_BYTES as DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES,
    ModelCheckerBudget,
    ModelCheckerCommand,
    run_model_checker,
)
from .models import EvidenceObject, RequirementIR, StatusDecision, SymbolRef
from .openapi_adapter import OpenApiAdapter
from .openapi_package import build_openapi_package, validate_openapi_package
from .package import build_package, validate_package
from .parser import RequirementParser
from .protobuf_adapter import ProtobufAdapter
from .protobuf_package import build_protobuf_package, validate_protobuf_package
from .python_package import build_python_package, validate_python_package
from .python_source_adapter import PythonSourceLanguageAdapter
from .proof_closure import (
    backend_results_from_formal_response,
    backend_results_from_system_consistency,
    build_proof_object,
    evaluate_closure_gate,
)
from .requirement_self_consistency import check_requirement_self_consistency
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
from .system_spec import build_system_spec_registry_report, load_system_spec_registry
from .system_checker import (
    check_requirement_set_consistency,
    check_solver_backed_system_consistency,
    check_system_consistency,
)
from .translator import (
    ControlledDraft,
    approve_controlled_draft,
    create_controlled_draft,
    lower_ir_v2_to_tla,
    parse_approved_draft_ir_v2,
)
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

    ir_v2_cmd = subcommands.add_parser("ir-v2", help="Parse DSL v2 to compositional IR JSON.")
    ir_v2_cmd.add_argument("file", type=Path)
    ir_v2_cmd.add_argument("--requirement-id", required=True)
    ir_v2_cmd.add_argument("--title", required=True)

    package_cmd = subcommands.add_parser("package", help="Build a Phase 0 requirement package.")
    package_cmd.add_argument("file", type=Path)
    package_cmd.add_argument("--out", type=Path, required=True)
    package_cmd.add_argument("--requirement-id", required=True)
    package_cmd.add_argument("--title", required=True)
    package_cmd.add_argument("--claim-kind", required=True)

    validate_ir_cmd = subcommands.add_parser("validate-ir", help="Validate IR JSON.")
    validate_ir_cmd.add_argument("file", type=Path)

    migrate_ir_cmd = subcommands.add_parser(
        "migrate-ir", help="Migrate flat IR 0.1 JSON to compositional IR 0.2 JSON."
    )
    migrate_ir_cmd.add_argument("file", type=Path)
    migrate_ir_cmd.add_argument("--out", type=Path, required=True)
    migrate_ir_cmd.add_argument("--migration-record", type=Path, required=True)
    migrate_ir_cmd.add_argument("--tool-version", default=DEFAULT_MIGRATION_TOOL_VERSION)
    migrate_ir_cmd.add_argument("--timestamp", default=DEFAULT_MIGRATION_TIMESTAMP)

    formal_backend_check_cmd = subcommands.add_parser(
        "formal-backend-check", help="Check compositional IR against a formal backend boundary."
    )
    formal_backend_check_cmd.add_argument("file", type=Path)
    formal_backend_check_cmd.add_argument("--backend", default="tla-boundary")
    formal_backend_check_cmd.add_argument("--artifact-dir", type=Path)
    formal_backend_check_cmd.add_argument("--checker-id")
    formal_backend_check_cmd.add_argument("--checker-command", nargs=argparse.REMAINDER)
    formal_backend_check_cmd.add_argument("--timeout-seconds", type=int)
    formal_backend_check_cmd.add_argument("--max-depth", type=int)
    formal_backend_check_cmd.add_argument("--max-states", type=int)
    formal_backend_check_cmd.add_argument("--memory-budget-mb", type=int)
    formal_backend_check_cmd.add_argument("--solver-option", action="append", default=[])
    formal_backend_check_cmd.add_argument("--expected-exit-code", type=int, default=0)
    formal_backend_check_cmd.add_argument("--tool-version")
    formal_backend_check_cmd.add_argument("--tool-version-command", nargs="+")
    formal_backend_check_cmd.add_argument(
        "--output-limit-bytes", type=int, default=DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES
    )

    model_checker_run_cmd = subcommands.add_parser(
        "model-checker-run", help="Run a local model checker with normalized metadata."
    )
    model_checker_run_cmd.add_argument("--run-id", required=True)
    model_checker_run_cmd.add_argument("--checker-id", required=True)
    model_checker_run_cmd.add_argument("--cwd", type=Path, default=Path("."))
    model_checker_run_cmd.add_argument("--timeout-seconds", type=int)
    model_checker_run_cmd.add_argument("--max-depth", type=int)
    model_checker_run_cmd.add_argument("--max-states", type=int)
    model_checker_run_cmd.add_argument("--memory-budget-mb", type=int)
    model_checker_run_cmd.add_argument("--solver-option", action="append", default=[])
    model_checker_run_cmd.add_argument("--expected-exit-code", type=int, default=0)
    model_checker_run_cmd.add_argument("--tool-version")
    model_checker_run_cmd.add_argument("--tool-version-command", nargs="+")
    model_checker_run_cmd.add_argument(
        "--output-limit-bytes", type=int, default=DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES
    )
    model_checker_run_cmd.add_argument("--out", type=Path)
    model_checker_run_cmd.add_argument("model_checker_command", nargs=argparse.REMAINDER)

    draft_cmd = subcommands.add_parser(
        "draft-controlled", help="Create a controlled-text draft artifact."
    )
    draft_cmd.add_argument("original", type=Path)
    draft_cmd.add_argument("--suggested", type=Path, required=True)
    draft_cmd.add_argument("--out", type=Path, required=True)
    draft_cmd.add_argument("--timestamp", default="2026-06-01T00:00:00Z")
    draft_cmd.add_argument("--method", choices=["manual", "llm"], default="manual")
    draft_cmd.add_argument("--model")
    draft_cmd.add_argument("--prompt")

    approve_draft_cmd = subcommands.add_parser(
        "approve-draft", help="Approve a controlled-text draft artifact."
    )
    approve_draft_cmd.add_argument("draft", type=Path)
    approve_draft_cmd.add_argument("--approved-by", required=True)
    approve_draft_cmd.add_argument("--approved-at", default="2026-06-01T00:00:00Z")
    approve_draft_cmd.add_argument("--out", type=Path, required=True)

    ir_v2_from_draft_cmd = subcommands.add_parser(
        "ir-v2-from-draft", help="Parse an approved draft artifact to compositional IR."
    )
    ir_v2_from_draft_cmd.add_argument("draft", type=Path)
    ir_v2_from_draft_cmd.add_argument("--requirement-id", required=True)
    ir_v2_from_draft_cmd.add_argument("--title", required=True)

    lower_ir_v2_cmd = subcommands.add_parser(
        "lower-ir-v2", help="Lower compositional IR to the first formal target artifact."
    )
    lower_ir_v2_cmd.add_argument("file", type=Path)
    lower_ir_v2_cmd.add_argument("--out", type=Path)

    python_source_impact_cmd = subcommands.add_parser(
        "python-source-impact", help="Run deterministic Python source impact analysis."
    )
    python_source_impact_cmd.add_argument("--manifest", type=Path, required=True)
    python_source_impact_cmd.add_argument("--symbol", action="append", required=True)
    python_source_impact_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    python_source_impact_cmd.add_argument("--out", type=Path)

    system_spec_cmd = subcommands.add_parser(
        "system-spec-registry", help="Validate and report system spec registry freshness."
    )
    system_spec_cmd.add_argument("registry", type=Path)
    system_spec_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    system_spec_cmd.add_argument("--module-id", action="append", default=[])
    system_spec_cmd.add_argument("--out", type=Path)

    system_consistency_cmd = subcommands.add_parser(
        "system-consistency-check", help="Run deterministic S-and-R consistency check."
    )
    system_consistency_cmd.add_argument("--requirement-ir", type=Path, required=True)
    system_consistency_cmd.add_argument("--lowered", type=Path, required=True)
    system_consistency_cmd.add_argument("--registry", type=Path, required=True)
    system_consistency_cmd.add_argument("--impact", type=Path, required=True)
    system_consistency_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    system_consistency_cmd.add_argument("--out", type=Path)

    solver_system_cmd = subcommands.add_parser(
        "solver-system-consistency-check",
        help="Run solver-backed S-and-R consistency over fresh reviewed specs.",
    )
    solver_system_cmd.add_argument("--requirement-ir", type=Path, required=True)
    solver_system_cmd.add_argument("--lowered", type=Path, required=True)
    solver_system_cmd.add_argument("--registry", type=Path, required=True)
    solver_system_cmd.add_argument("--impact", type=Path, required=True)
    solver_system_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    solver_system_cmd.add_argument("--artifact-dir", type=Path)
    solver_system_cmd.add_argument("--checker-id")
    solver_system_cmd.add_argument("--checker-command", nargs=argparse.REMAINDER)
    solver_system_cmd.add_argument("--timeout-seconds", type=int)
    solver_system_cmd.add_argument("--max-depth", type=int)
    solver_system_cmd.add_argument("--max-states", type=int)
    solver_system_cmd.add_argument("--memory-budget-mb", type=int)
    solver_system_cmd.add_argument("--solver-option", action="append", default=[])
    solver_system_cmd.add_argument("--expected-exit-code", type=int, default=0)
    solver_system_cmd.add_argument("--tool-version")
    solver_system_cmd.add_argument("--tool-version-command", nargs="+")
    solver_system_cmd.add_argument(
        "--output-limit-bytes", type=int, default=DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES
    )
    solver_system_cmd.add_argument("--out", type=Path)

    req_set_cmd = subcommands.add_parser(
        "requirement-set-consistency", help="Check flat requirement set contradictions."
    )
    req_set_cmd.add_argument("ir", nargs="+", type=Path)
    req_set_cmd.add_argument("--out", type=Path)

    req_self_cmd = subcommands.add_parser(
        "requirement-self-consistency", help="Check one compositional requirement before S-and-R."
    )
    req_self_cmd.add_argument("--requirement-ir", type=Path, required=True)
    req_self_cmd.add_argument("--backend", default="tla-runner")
    req_self_cmd.add_argument("--artifact-dir", type=Path)
    req_self_cmd.add_argument("--checker-id")
    req_self_cmd.add_argument("--checker-command", nargs=argparse.REMAINDER)
    req_self_cmd.add_argument("--timeout-seconds", type=int)
    req_self_cmd.add_argument("--max-depth", type=int)
    req_self_cmd.add_argument("--max-states", type=int)
    req_self_cmd.add_argument("--memory-budget-mb", type=int)
    req_self_cmd.add_argument("--solver-option", action="append", default=[])
    req_self_cmd.add_argument("--expected-exit-code", type=int, default=0)
    req_self_cmd.add_argument("--tool-version")
    req_self_cmd.add_argument("--tool-version-command", nargs="+")
    req_self_cmd.add_argument(
        "--output-limit-bytes", type=int, default=DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES
    )
    req_self_cmd.add_argument("--out", type=Path)

    spec_coverage_cmd = subcommands.add_parser(
        "spec-coverage", help="Build spec coverage report for affected modules."
    )
    spec_coverage_cmd.add_argument("--impact", type=Path, required=True)
    spec_coverage_cmd.add_argument("--registry", type=Path, required=True)
    spec_coverage_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_coverage_cmd.add_argument("--threshold", type=float, default=1.0)
    spec_coverage_cmd.add_argument("--out", type=Path)

    trace_align_cmd = subcommands.add_parser(
        "trace-align", help="Classify normalized traces against requirement/spec context."
    )
    trace_align_cmd.add_argument("--requirement-ir", type=Path, required=True)
    trace_align_cmd.add_argument("--trace-artifact", type=Path, required=True)
    trace_align_cmd.add_argument("--coverage", type=Path, required=True)
    trace_align_cmd.add_argument("--out", type=Path)

    proof_object_cmd = subcommands.add_parser(
        "proof-object", help="Aggregate backend evidence into a proof closure object."
    )
    proof_object_cmd.add_argument("--requirement-ir", type=Path, required=True)
    proof_object_cmd.add_argument("--system-consistency", action="append", type=Path, default=[])
    proof_object_cmd.add_argument("--formal-backend-response", action="append", type=Path, default=[])
    proof_object_cmd.add_argument("--backend-result", action="append", type=Path, default=[])
    proof_object_cmd.add_argument("--spec-coverage", type=Path)
    proof_object_cmd.add_argument("--trace-alignment", type=Path)
    proof_object_cmd.add_argument("--producer-mapping", type=Path)
    proof_object_cmd.add_argument("--out", type=Path)

    closure_gate_cmd = subcommands.add_parser(
        "closure-gate", help="Evaluate whether a downstream action has a closed proof object."
    )
    closure_gate_cmd.add_argument("proof_object", type=Path)
    closure_gate_cmd.add_argument("--downstream-action", default="merge")
    closure_gate_cmd.add_argument("--out", type=Path)
    closure_gate_cmd.add_argument("--fail-on-blocking", action="store_true")

    agnostic_wedge_cmd = subcommands.add_parser(
        "agnostic-wedge", help="Validate a closed proof object across languages or formalisms."
    )
    agnostic_wedge_cmd.add_argument("--proof-object", type=Path, required=True)
    agnostic_wedge_cmd.add_argument("--source-manifest", action="append", type=Path, default=[])
    agnostic_wedge_cmd.add_argument("--formal-backend-response", action="append", type=Path, default=[])
    agnostic_wedge_cmd.add_argument("--requirement-ir", type=Path)
    agnostic_wedge_cmd.add_argument("--out", type=Path)
    agnostic_wedge_cmd.add_argument("--fail-on-blocking", action="store_true")

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

    json_schema_conformance_cmd = subcommands.add_parser(
        "json-schema-conformance", help="Run conformance against a JSON Schema adapter."
    )
    json_schema_conformance_cmd.add_argument("schema", type=Path)
    json_schema_conformance_cmd.add_argument("--json-schema-name")
    json_schema_conformance_cmd.add_argument("--resolved-ref", default="operation")
    json_schema_conformance_cmd.add_argument("--resolved-type", default="action")
    json_schema_conformance_cmd.add_argument("--unresolved-ref", default="definitely_missing_symbol")
    json_schema_conformance_cmd.add_argument("--ambiguous-ref", default="duplicate_operation")
    json_schema_conformance_cmd.add_argument("--ambiguous-type", default="action")

    json_schema_package_cmd = subcommands.add_parser(
        "json-schema-package", help="Build a JSON Schema-adapter requirement package."
    )
    json_schema_package_cmd.add_argument("file", type=Path)
    json_schema_package_cmd.add_argument("--out", type=Path, required=True)
    json_schema_package_cmd.add_argument("--requirement-id", required=True)
    json_schema_package_cmd.add_argument("--title", required=True)
    json_schema_package_cmd.add_argument("--claim-kind", required=True)
    json_schema_package_cmd.add_argument("--schema", type=Path, required=True)
    json_schema_package_cmd.add_argument("--json-schema-name")

    json_schema_validate_cmd = subcommands.add_parser(
        "json-schema-validate", help="Validate a JSON Schema-adapter requirement package."
    )
    json_schema_validate_cmd.add_argument("package_dir", type=Path)
    json_schema_validate_cmd.add_argument("--schema", type=Path, required=True)
    json_schema_validate_cmd.add_argument("--json-schema-name")

    asyncapi_conformance_cmd = subcommands.add_parser(
        "asyncapi-conformance", help="Run conformance against an AsyncAPI adapter."
    )
    asyncapi_conformance_cmd.add_argument("document", type=Path)
    asyncapi_conformance_cmd.add_argument("--asyncapi-name")
    asyncapi_conformance_cmd.add_argument("--resolved-ref", default="operation")
    asyncapi_conformance_cmd.add_argument("--resolved-type", default="action")
    asyncapi_conformance_cmd.add_argument("--unresolved-ref", default="definitely_missing_symbol")
    asyncapi_conformance_cmd.add_argument("--ambiguous-ref", default="duplicate_operation")
    asyncapi_conformance_cmd.add_argument("--ambiguous-type", default="action")

    asyncapi_package_cmd = subcommands.add_parser(
        "asyncapi-package", help="Build an AsyncAPI-adapter requirement package."
    )
    asyncapi_package_cmd.add_argument("file", type=Path)
    asyncapi_package_cmd.add_argument("--out", type=Path, required=True)
    asyncapi_package_cmd.add_argument("--requirement-id", required=True)
    asyncapi_package_cmd.add_argument("--title", required=True)
    asyncapi_package_cmd.add_argument("--claim-kind", required=True)
    asyncapi_package_cmd.add_argument("--document", type=Path, required=True)
    asyncapi_package_cmd.add_argument("--asyncapi-name")

    asyncapi_validate_cmd = subcommands.add_parser(
        "asyncapi-validate", help="Validate an AsyncAPI-adapter requirement package."
    )
    asyncapi_validate_cmd.add_argument("package_dir", type=Path)
    asyncapi_validate_cmd.add_argument("--document", type=Path, required=True)
    asyncapi_validate_cmd.add_argument("--asyncapi-name")

    protobuf_conformance_cmd = subcommands.add_parser(
        "protobuf-conformance", help="Run conformance against a Protobuf/gRPC adapter."
    )
    protobuf_conformance_cmd.add_argument("schema", type=Path)
    protobuf_conformance_cmd.add_argument("--protobuf-name")
    protobuf_conformance_cmd.add_argument("--resolved-ref", default="operation")
    protobuf_conformance_cmd.add_argument("--resolved-type", default="action")
    protobuf_conformance_cmd.add_argument("--unresolved-ref", default="definitely_missing_symbol")
    protobuf_conformance_cmd.add_argument("--ambiguous-ref", default="duplicate_operation")
    protobuf_conformance_cmd.add_argument("--ambiguous-type", default="action")

    protobuf_package_cmd = subcommands.add_parser(
        "protobuf-package", help="Build a Protobuf/gRPC-adapter requirement package."
    )
    protobuf_package_cmd.add_argument("file", type=Path)
    protobuf_package_cmd.add_argument("--out", type=Path, required=True)
    protobuf_package_cmd.add_argument("--requirement-id", required=True)
    protobuf_package_cmd.add_argument("--title", required=True)
    protobuf_package_cmd.add_argument("--claim-kind", required=True)
    protobuf_package_cmd.add_argument("--schema", type=Path, required=True)
    protobuf_package_cmd.add_argument("--protobuf-name")

    protobuf_validate_cmd = subcommands.add_parser(
        "protobuf-validate", help="Validate a Protobuf/gRPC-adapter requirement package."
    )
    protobuf_validate_cmd.add_argument("package_dir", type=Path)
    protobuf_validate_cmd.add_argument("--schema", type=Path, required=True)
    protobuf_validate_cmd.add_argument("--protobuf-name")

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
        if args.command == "ir-v2":
            ir = DslV2Parser().parse_ir(
                args.file.read_text(),
                requirement_id=args.requirement_id,
                title=args.title,
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
            validate_requirement_ir_json(args.file.read_text())
            print("IR: valid")
            return 0
        if args.command == "migrate-ir":
            from .jsonutil import write_json

            source_ir = RequirementIR.model_validate_json(args.file.read_text())
            migrated, record = migrate_requirement_ir_v1_to_v2(
                source_ir,
                tool_version=args.tool_version,
                timestamp=args.timestamp,
            )
            write_json(args.out, migrated)
            write_json(args.migration_record, record)
            print(f"Migrated IR: {args.out}")
            print(f"Migration record: {args.migration_record}")
            return 0
        if args.command == "formal-backend-check":
            from .models import RequirementIRV2

            ir = validate_requirement_ir_json(args.file.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("formal-backend-check requires ir_version 0.2")
            checker_command = (
                _normalize_remainder_command(args.checker_command)
                if args.checker_command
                else None
            )
            request = build_formal_backend_request(
                ir,
                backend_id=args.backend,
                budget=_formal_backend_budget_from_args(args),
                execution=_formal_backend_execution_from_args(args, checker_command),
            )
            print(canonical_json(check_formal_backend(request)), end="")
            return 0
        if args.command == "model-checker-run":
            command = _normalize_remainder_command(args.model_checker_command)
            if not command:
                raise ValueError("model-checker-run requires a command after --")
            request = ModelCheckerCommand(
                run_id=args.run_id,
                checker_id=args.checker_id,
                command=command,
                cwd=args.cwd.as_posix(),
                budget=ModelCheckerBudget(
                    timeout_seconds=args.timeout_seconds,
                    max_depth=args.max_depth,
                    max_states=args.max_states,
                    memory_budget_mb=args.memory_budget_mb,
                    solver_options=_parse_solver_options(args.solver_option),
                ),
                expected_exit_code=args.expected_exit_code,
                tool_version=args.tool_version,
                tool_version_command=args.tool_version_command,
                output_limit_bytes=args.output_limit_bytes,
            )
            result = run_model_checker(request)
            if args.out is not None:
                from .jsonutil import write_json

                write_json(args.out, result)
                print(f"Model checker run: {args.out}")
            else:
                print(canonical_json(result), end="")
            return 0
        if args.command == "draft-controlled":
            from .jsonutil import write_json

            draft = create_controlled_draft(
                original_text=args.original.read_text(),
                suggested_text=args.suggested.read_text(),
                timestamp=args.timestamp,
                method=args.method,
                model=args.model,
                prompt=args.prompt,
            )
            write_json(args.out, draft)
            print(f"Controlled draft: {args.out}")
            return 0
        if args.command == "approve-draft":
            from .jsonutil import write_json

            draft = ControlledDraft.model_validate_json(args.draft.read_text())
            approved = approve_controlled_draft(
                draft,
                approved_by=args.approved_by,
                approved_at=args.approved_at,
            )
            write_json(args.out, approved)
            print(f"Approved draft: {args.out}")
            return 0
        if args.command == "ir-v2-from-draft":
            draft = ControlledDraft.model_validate_json(args.draft.read_text())
            ir = parse_approved_draft_ir_v2(
                draft,
                requirement_id=args.requirement_id,
                title=args.title,
            )
            print(canonical_json(ir), end="")
            return 0
        if args.command == "lower-ir-v2":
            from .jsonutil import write_json
            from .models import RequirementIRV2

            ir = validate_requirement_ir_json(args.file.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("lower-ir-v2 requires ir_version 0.2")
            artifact = lower_ir_v2_to_tla(ir)
            if args.out:
                write_json(args.out, artifact)
                print(f"Lowered formal artifact: {args.out}")
            else:
                print(canonical_json(artifact), end="")
            return 0
        if args.command == "python-source-impact":
            from .jsonutil import write_json

            adapter = PythonSourceLanguageAdapter(project_root=args.project_root)
            manifest = adapter.parse_manifest(args.manifest)
            artifact = analyze_source_impact(adapter, manifest, symbols=args.symbol)
            if args.out:
                write_json(args.out, artifact)
                print(f"Python source impact: {args.out}")
            else:
                print(canonical_json(artifact), end="")
            return 0
        if args.command == "system-spec-registry":
            from .jsonutil import write_json

            registry = load_system_spec_registry(args.registry)
            report = build_system_spec_registry_report(
                registry,
                project_root=args.project_root,
                module_ids=args.module_id,
            )
            if args.out:
                write_json(args.out, report)
                print(f"System spec registry report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "system-consistency-check":
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .translator import LoweredFormalArtifact

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("system-consistency-check requires ir_version 0.2")
            result = check_system_consistency(
                requirement=ir,
                lowered=LoweredFormalArtifact.model_validate_json(args.lowered.read_text()),
                registry=load_system_spec_registry(args.registry),
                impact=ImpactAnalysisArtifact.model_validate_json(args.impact.read_text()),
                project_root=args.project_root,
            )
            if args.out:
                write_json(args.out, result)
                print(f"System consistency result: {args.out}")
            else:
                print(canonical_json(result), end="")
            return 0
        if args.command == "solver-system-consistency-check":
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .translator import LoweredFormalArtifact

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("solver-system-consistency-check requires ir_version 0.2")
            checker_command = (
                _normalize_remainder_command(args.checker_command)
                if args.checker_command
                else None
            )
            result = check_solver_backed_system_consistency(
                requirement=ir,
                lowered=LoweredFormalArtifact.model_validate_json(args.lowered.read_text()),
                registry=load_system_spec_registry(args.registry),
                impact=ImpactAnalysisArtifact.model_validate_json(args.impact.read_text()),
                project_root=args.project_root,
                budget=_formal_backend_budget_from_args(args),
                execution=_formal_backend_execution_from_args(args, checker_command),
            )
            if args.out:
                write_json(args.out, result)
                print(f"Solver-backed system consistency result: {args.out}")
            else:
                print(canonical_json(result), end="")
            return 0
        if args.command == "requirement-set-consistency":
            from .jsonutil import write_json

            report = check_requirement_set_consistency(
                [RequirementIR.model_validate_json(path.read_text()) for path in args.ir]
            )
            if args.out:
                write_json(args.out, report)
                print(f"Requirement set consistency: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "requirement-self-consistency":
            from .jsonutil import write_json
            from .models import RequirementIRV2

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("requirement-self-consistency requires ir_version 0.2")
            checker_command = (
                _normalize_remainder_command(args.checker_command)
                if args.checker_command
                else None
            )
            report = check_requirement_self_consistency(
                ir,
                backend_id=args.backend,
                budget=_formal_backend_budget_from_args(args),
                execution=_formal_backend_execution_from_args(args, checker_command),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Requirement self-consistency: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "spec-coverage":
            from .coverage_alignment import SpecCoverageReport
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json

            report = build_spec_coverage_report(
                impact=ImpactAnalysisArtifact.model_validate_json(args.impact.read_text()),
                registry=load_system_spec_registry(args.registry),
                project_root=args.project_root,
                threshold=args.threshold,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Spec coverage report: {args.out}")
            else:
                print(canonical_json(SpecCoverageReport.model_validate(report)), end="")
            return 0
        if args.command == "trace-align":
            from .coverage_alignment import SpecCoverageReport
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact, RequirementIRV2

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("trace-align requires ir_version 0.2")
            report = build_trace_alignment_report(
                requirement=ir,
                traces=NormalizedTraceArtifact.model_validate_json(args.trace_artifact.read_text()),
                coverage=SpecCoverageReport.model_validate_json(args.coverage.read_text()),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Trace alignment report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "proof-object":
            from .coverage_alignment import SpecCoverageReport, TraceAlignmentReport
            from .formal_backend import FormalBackendResponse
            from .jsonutil import write_json
            from .models import BackendResult, RequirementIRV2
            from .proof_closure import EvidenceProducerMapping
            from .system_checker import SystemConsistencyResult

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("proof-object requires ir_version 0.2")
            backend_results: list[BackendResult] = []
            for path in args.system_consistency:
                backend_results.extend(
                    backend_results_from_system_consistency(
                        SystemConsistencyResult.model_validate_json(path.read_text())
                    )
                )
            for path in args.formal_backend_response:
                backend_results.extend(
                    backend_results_from_formal_response(
                        FormalBackendResponse.model_validate_json(path.read_text())
                    )
                )
            for path in args.backend_result:
                backend_results.append(BackendResult.model_validate_json(path.read_text()))
            proof = build_proof_object(
                requirement=ir,
                backend_results=backend_results,
                coverage=(
                    SpecCoverageReport.model_validate_json(args.spec_coverage.read_text())
                    if args.spec_coverage
                    else None
                ),
                trace_alignment=(
                    TraceAlignmentReport.model_validate_json(args.trace_alignment.read_text())
                    if args.trace_alignment
                    else None
                ),
                producer_mapping=(
                    EvidenceProducerMapping.model_validate_json(args.producer_mapping.read_text())
                    if args.producer_mapping
                    else None
                ),
            )
            if args.out:
                write_json(args.out, proof)
                print(f"Proof object: {args.out}")
            else:
                print(canonical_json(proof), end="")
            return 0
        if args.command == "closure-gate":
            from .jsonutil import write_json
            from .proof_closure import ProofObject

            proof = ProofObject.model_validate_json(args.proof_object.read_text())
            report = evaluate_closure_gate(proof, downstream_action=args.downstream_action)
            if args.out:
                write_json(args.out, report)
                print(f"Closure gate report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.fail_on_blocking and report.result == "blocked":
                return 1
            return 0
        if args.command == "agnostic-wedge":
            from .formal_backend import FormalBackendResponse
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .proof_closure import ProofObject
            from .source_adapter import SourceManifest

            requirement = None
            if args.requirement_ir:
                ir = validate_requirement_ir_json(args.requirement_ir.read_text())
                if not isinstance(ir, RequirementIRV2):
                    raise ValueError("agnostic-wedge requires ir_version 0.2")
                requirement = ir
            report = build_agnostic_wedge_report(
                proof=ProofObject.model_validate_json(args.proof_object.read_text()),
                source_manifests=[
                    SourceManifest.model_validate_json(path.read_text())
                    for path in args.source_manifest
                ],
                formal_responses=[
                    FormalBackendResponse.model_validate_json(path.read_text())
                    for path in args.formal_backend_response
                ],
                requirement=requirement,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Agnostic wedge report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.fail_on_blocking and report.result == "blocked":
                return 1
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
        if args.command == "json-schema-conformance":
            adapter = JsonSchemaAdapter(
                args.schema,
                schema_name=args.json_schema_name or args.schema.stem,
            )
            report = assert_adapter_conforms(
                adapter,
                _json_schema_conformance_fixture(
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
        if args.command == "json-schema-package":
            adapter = JsonSchemaAdapter(
                args.schema,
                schema_name=args.json_schema_name or args.schema.stem,
            )
            build_json_schema_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "json-schema-validate":
            adapter = JsonSchemaAdapter(
                args.schema,
                schema_name=args.json_schema_name or args.schema.stem,
            )
            ir, evidence, status = validate_json_schema_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "asyncapi-conformance":
            adapter = AsyncApiAdapter(
                args.document,
                document_name=args.asyncapi_name or args.document.stem,
            )
            report = assert_adapter_conforms(
                adapter,
                _asyncapi_conformance_fixture(
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
        if args.command == "asyncapi-package":
            adapter = AsyncApiAdapter(
                args.document,
                document_name=args.asyncapi_name or args.document.stem,
            )
            build_asyncapi_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "asyncapi-validate":
            adapter = AsyncApiAdapter(
                args.document,
                document_name=args.asyncapi_name or args.document.stem,
            )
            ir, evidence, status = validate_asyncapi_package(args.package_dir, adapter)
            _print_package_validation(ir, evidence, status)
            return 0
        if args.command == "protobuf-conformance":
            adapter = ProtobufAdapter(
                args.schema,
                schema_name=args.protobuf_name or args.schema.stem,
            )
            report = assert_adapter_conforms(
                adapter,
                _protobuf_conformance_fixture(
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
        if args.command == "protobuf-package":
            adapter = ProtobufAdapter(
                args.schema,
                schema_name=args.protobuf_name or args.schema.stem,
            )
            build_protobuf_package(
                controlled_text=args.file.read_text(),
                output_dir=args.out,
                requirement_id=args.requirement_id,
                title=args.title,
                claim_kind=args.claim_kind,
                adapter=adapter,
            )
            print(f"Package: {args.out}")
            return 0
        if args.command == "protobuf-validate":
            adapter = ProtobufAdapter(
                args.schema,
                schema_name=args.protobuf_name or args.schema.stem,
            )
            ir, evidence, status = validate_protobuf_package(args.package_dir, adapter)
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
                json_schema_adapter=_optional_json_schema_adapter(args),
                asyncapi_adapter=_optional_asyncapi_adapter(args),
                protobuf_adapter=_optional_protobuf_adapter(args),
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
    parser.add_argument("--json-schema-document", type=Path)
    parser.add_argument("--json-schema-name")
    parser.add_argument("--asyncapi-document", type=Path)
    parser.add_argument("--asyncapi-name")
    parser.add_argument("--protobuf-schema", type=Path)
    parser.add_argument("--protobuf-name")
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


def _optional_json_schema_adapter(args: argparse.Namespace) -> JsonSchemaAdapter | None:
    if args.json_schema_document is None:
        return None
    return JsonSchemaAdapter(
        args.json_schema_document,
        schema_name=args.json_schema_name or args.json_schema_document.stem,
    )


def _optional_asyncapi_adapter(args: argparse.Namespace) -> AsyncApiAdapter | None:
    if args.asyncapi_document is None:
        return None
    return AsyncApiAdapter(
        args.asyncapi_document,
        document_name=args.asyncapi_name or args.asyncapi_document.stem,
    )


def _optional_protobuf_adapter(args: argparse.Namespace) -> ProtobufAdapter | None:
    if args.protobuf_schema is None:
        return None
    return ProtobufAdapter(
        args.protobuf_schema,
        schema_name=args.protobuf_name or args.protobuf_schema.stem,
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


def _parse_solver_options(entries: list[str]) -> dict[str, str | int | float | bool]:
    options: dict[str, str | int | float | bool] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"solver option must be KEY=VALUE: {entry}")
        key, value = entry.split("=", 1)
        if not key:
            raise ValueError(f"solver option key must be non-empty: {entry}")
        options[key] = _parse_scalar_option(value)
    return options


def _parse_scalar_option(value: str) -> str | int | float | bool:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _normalize_remainder_command(command: list[str] | None) -> list[str]:
    normalized = list(command or [])
    if normalized and normalized[0] == "--":
        return normalized[1:]
    return normalized


def _formal_backend_budget_from_args(args: argparse.Namespace) -> FormalBackendBudget | None:
    if not any(
        [
            args.timeout_seconds,
            args.max_depth,
            args.max_states,
            args.memory_budget_mb,
            args.solver_option,
        ]
    ):
        return None
    return FormalBackendBudget(
        timeout_seconds=args.timeout_seconds,
        max_depth=args.max_depth,
        max_states=args.max_states,
        memory_budget_mb=args.memory_budget_mb,
        solver_options=_parse_solver_options(args.solver_option),
    )


def _formal_backend_execution_from_args(
    args: argparse.Namespace, checker_command: list[str] | None
) -> FormalBackendExecution | None:
    if not any(
        [
            args.artifact_dir,
            args.checker_id,
            checker_command,
            args.tool_version,
            args.tool_version_command,
            args.expected_exit_code,
            args.output_limit_bytes != DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES,
        ]
    ):
        return None
    return FormalBackendExecution(
        checker_id=args.checker_id or "tlc",
        command=checker_command,
        artifact_dir=args.artifact_dir.as_posix() if args.artifact_dir else None,
        expected_exit_code=args.expected_exit_code,
        tool_version=args.tool_version,
        tool_version_command=args.tool_version_command,
        output_limit_bytes=args.output_limit_bytes,
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


def _json_schema_conformance_fixture(
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
            "if actor is approved\n"
            'then operation must set operation_status to "accepted".\n'
        ),
        requirement_id="REQ-JSON-SCHEMA-CONFORMANCE-001",
        title="JSON Schema adapter conformance fixture",
        claim_kind="state_postcondition",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name=resolved_ref, expected_type=resolved_type),
        unresolved_ref=SymbolRef(name=unresolved_ref),
        ambiguous_ref=SymbolRef(name=ambiguous_ref, expected_type=ambiguous_type),
        sample_ir=ir,
    )


def _asyncapi_conformance_fixture(
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
            "if actor is approved\n"
            "then operation must emit operation_accepted.\n"
        ),
        requirement_id="REQ-ASYNCAPI-CONFORMANCE-001",
        title="AsyncAPI adapter conformance fixture",
        claim_kind="event_state_correspondence",
    )
    return AdapterConformanceFixture(
        resolved_ref=SymbolRef(name=resolved_ref, expected_type=resolved_type),
        unresolved_ref=SymbolRef(name=unresolved_ref),
        ambiguous_ref=SymbolRef(name=ambiguous_ref, expected_type=ambiguous_type),
        sample_ir=ir,
    )


def _protobuf_conformance_fixture(
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
        requirement_id="REQ-PROTOBUF-CONFORMANCE-001",
        title="Protobuf/gRPC adapter conformance fixture",
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
