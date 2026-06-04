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
from .adapter_certification import (
    AdapterCertificationReport,
    AdapterPluginManifest,
    certify_adapter,
    validate_adapter_plugin_manifest,
)
from .adoption import (
    build_ci_report,
    build_package_index,
    build_soft_gate_report,
    ci_report_markdown,
    extract_requirement_ids,
    review_checklist_template,
)
from .artifact_store import ArtifactStoreManifest, lookup_artifact, put_artifact
from .asyncapi_adapter import AsyncApiAdapter
from .asyncapi_package import build_asyncapi_package, validate_asyncapi_package
from .backend_agreement import build_backend_agreement_report
from .benchmark_corpus import build_benchmark_run_report
from .benchmark_reporting import (
    BenchmarkEvaluationReport,
    ExtendedBenchmarkDimensionResult,
    ExtendedBenchmarkEvaluationReport,
    build_benchmark_evaluation_report,
    build_extended_benchmark_evaluation_report,
)
from .ci_pr_gate import (
    ExtendedCiPrGateReport,
    build_ci_adoption_report,
    build_ci_pr_gate_report,
    ci_pr_gate_markdown,
    extended_ci_pr_gate_markdown,
)
from .command_adapter import CommandAdapter, CommandChecksArtifact, load_command_checks
from .command_package import (
    build_command_package,
    command_results_markdown,
    run_command_evidence,
    validate_command_package,
)
from .conclusion import (
    ConclusionGapChecklist,
    build_default_conclusion_definition,
    build_default_gap_checklist,
    check_gap_checklist,
)
from .conclusion_certification import (
    build_conclusion_certification_report,
    build_extended_conclusion_certification_report,
)
from .continuous import (
    build_attestation_run,
    continuous_attestation_markdown,
    load_attestation_run,
)
from .controlled_semantics import build_controlled_requirement_semantics_reference
from .coverage_alignment import (
    CodeSpecCoverageManifestV2,
    build_code_spec_coverage_gate_report_v2,
    build_spec_coverage_report,
    build_trace_alignment_report,
    migrate_code_spec_manifest_to_v2,
)
from .compositional_ir import (
    DEFAULT_MIGRATION_TIMESTAMP,
    DEFAULT_MIGRATION_TOOL_VERSION,
    migrate_requirement_ir_v1_to_v2,
    validate_requirement_ir_json,
)
from .counterexample_normalization import (
    explain_counterexamples,
    normalize_backend_counterexamples,
)
from .cross_language import CausalTraceLink, build_cross_language_proof_object
from .formal_backend import (
    FormalBackendBudget,
    FormalBackendExecution,
    build_formal_backend_request,
    check_formal_backend,
)
from .formal_claim import (
    FormalClaimLoweringReport,
    build_formal_claim,
    build_formal_claim_semantics_completion_reference,
)
from .delta_extractor import build_delta_report, delta_report_markdown
from .dsl_v2 import DslV2Parser
from .dsl_v3 import DslV3Parser
from .evidence_boundary import (
    ProofArtifactRef,
    build_proof_evidence_boundary_report,
    build_proof_producing_backend_boundary_report,
)
from .evidence_producers import validate_real_evidence_producers
from .end_to_end_gate import (
    EndToEndRequirementGateReport,
    ExtendedEndToEndRequirementGateReport,
    build_extended_requirement_gate_report,
    run_end_to_end_requirement_gate,
)
from .gate import (
    build_hard_gate_report,
    hard_gate_report_markdown,
    load_gate_policy,
    load_gate_waivers,
)
from .graphql_adapter import GraphQlAdapter
from .graphql_package import build_graphql_package, validate_graphql_package
from .impact import analyze_source_impact
from .source_impact import (
    SemanticImpactSuggestion,
    analyze_production_source_impact,
    analyze_source_impact_with_context,
)
from .intake import (
    ControlledRewriteApproval,
    ControlledRewriteProposal,
    approve_controlled_rewrite,
    create_controlled_rewrite_proposal,
    create_free_form_intake,
    draft_controlled_rewrite_with_llm,
)
from .javascript_source_adapter import JavaScriptSourceLanguageAdapter
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
from .models import Approval
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
    default_evidence_producer_mapping,
    evaluate_closure_gate,
)
from .policy_governance import build_waiver_audit_report
from .production_source_adapters import production_adapter_for_language
from .public_sdk import (
    PublicDocumentationCoverageReport,
    PublicDocumentationFreezeReport,
    PublicDocumentationIndex,
    build_default_public_documentation_index,
    build_public_documentation_freeze_report,
    validate_public_documentation_index,
)
from .provenance import (
    ClarificationResponse,
    apply_clarification_response,
    build_provenance_graph,
    clarification_requests_from_agreement,
)
from .requirement_self_consistency import check_requirement_self_consistency
from .refusal import (
    ProductRefusalReport,
    build_refusal_report_from_gate,
    refusal_report_markdown,
)
from .semantic_agreement import (
    FormalClaimAgreementCandidate,
    SemanticAgreementReport,
    SemanticAgreementResolution,
    build_semantic_agreement_report,
)
from .semantic_translation import (
    SemanticTranslationReport,
    translate_controlled_requirement_to_formal_claim,
)
from .reference_demo import (
    ExtendedReferenceDemoReport,
    ReferenceDemoManifest,
    ReferenceDemoReport,
    build_extended_reference_demo_report,
    build_reference_demo_report,
)
from .review_workflow import (
    ApprovalWorkflowArtifact,
    ReviewChecklist,
    approve_review,
    artifact_ref_from_path,
    open_review,
    review_status,
)
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
from .spec_drift import CodeSpecManifest, build_spec_drift_report, mark_stale_specs
from .spec_extraction import (
    CandidateSpec,
    CandidateSpecReviewChecklistItem,
    build_spec_extraction_workbench_report,
    build_specula_extraction_integration_report,
    promote_candidate_spec_with_review,
    reject_candidate_spec,
)
from .spec_freshness import (
    SpecFreshnessLockfile,
    SpecFreshnessLockfileV2,
    build_spec_drift_ci_report,
    build_spec_freshness_lockfile,
    build_spec_freshness_lockfile_v2,
    validate_spec_freshness_lockfile,
    validate_spec_freshness_lockfile_v2,
)
from .trace_validation import (
    build_trace_validation_gate_report,
    build_trace_validation_report,
    trace_validation_gate_markdown,
    trace_validation_markdown,
)
from .trace_normalization import RawTraceArtifact, normalize_raw_traces
from .system_spec import build_system_spec_registry_report, load_system_spec_registry
from .system_composition import build_s_and_r_composition_report
from .system_checker import (
    check_requirement_set_consistency,
    check_solver_backed_system_consistency,
    check_system_consistency,
)
from .threat_model import (
    ExtendedTcbReviewReport,
    ThreatModelReport,
    build_default_threat_model,
    build_extended_tcb_review_report,
)
from .translator import (
    ControlledDraft,
    approve_controlled_draft,
    create_controlled_draft,
    lower_ir_v2_to_tla,
    parse_approved_draft_ir_v2,
)
from .tla_projection import build_tla_projection_report
from .translator_agreement import (
    TranslationAgreementInput,
    TranslationAgreementReport,
    build_translation_agreement_report,
)
from .logical_agreement import build_logical_translation_agreement_report
from .trace_replay import build_trace_replay_report
from .runtime_trace_sdk import (
    TraceExtractionRequest,
    TraceProducerRegistry,
    build_trace_producer_evidence_report,
    producer_from_registry,
)
from .signed_evidence import (
    ProducerKeyRegistry,
    SignedEvidenceEnvelope,
    sign_evidence_payload,
    verify_signed_evidence,
)
from .tla_adapter import TlaAdapter, load_tla_model_config
from .tla_package import (
    build_tla_package,
    run_tla_checks,
    tla_results_markdown,
    validate_tla_package,
)
from .verification_budget import (
    AbstractionAssumption,
    build_verification_budget_report,
)
from .translation_benchmark import (
    RequirementTranslationCorpus,
    RequirementTranslationResults,
    build_translation_benchmark_report,
)
from .translation_repair import build_translation_repair_report
from .translator_workbench import (
    TranslatorRunArtifact,
    build_multi_pass_translator_run,
    compare_translator_run,
    select_translator_candidate,
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

    ir_v3_cmd = subcommands.add_parser("ir-v3", help="Parse DSL v3 to compositional IR JSON.")
    ir_v3_cmd.add_argument("file", type=Path)
    ir_v3_cmd.add_argument("--requirement-id", required=True)
    ir_v3_cmd.add_argument("--title", required=True)

    conclusion_definition_cmd = subcommands.add_parser(
        "conclusion-definition", help="Emit the conclusion definition artifact."
    )
    conclusion_definition_cmd.add_argument("--out", type=Path)

    conclusion_gap_checklist_cmd = subcommands.add_parser(
        "conclusion-gap-checklist", help="Emit the machine-readable conclusion gap checklist."
    )
    conclusion_gap_checklist_cmd.add_argument("--out", type=Path)

    conclusion_gap_check_cmd = subcommands.add_parser(
        "conclusion-gap-check", help="Validate conclusion gap phase and ADR references."
    )
    conclusion_gap_check_cmd.add_argument("checklist", type=Path)
    conclusion_gap_check_cmd.add_argument("--out", type=Path)

    threat_model_cmd = subcommands.add_parser("threat-model", help="Emit the default threat model.")
    threat_model_cmd.add_argument("--out", type=Path)

    public_docs_cmd = subcommands.add_parser(
        "public-docs-index", help="Emit the public documentation and SDK index."
    )
    public_docs_cmd.add_argument("--version", default="0.1")
    public_docs_cmd.add_argument("--out", type=Path)

    public_docs_check_cmd = subcommands.add_parser(
        "public-docs-check", help="Validate public documentation index paths and schema references."
    )
    public_docs_check_cmd.add_argument("index", type=Path)
    public_docs_check_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    public_docs_check_cmd.add_argument("--schema-root", type=Path, default=Path("schemas"))
    public_docs_check_cmd.add_argument("--out", type=Path)

    conclusion_certify_cmd = subcommands.add_parser(
        "conclusion-certify", help="Build a conclusion release certification report."
    )
    conclusion_certify_cmd.add_argument("--release-id", required=True)
    conclusion_certify_cmd.add_argument("--benchmark-report", type=Path, required=True)
    conclusion_certify_cmd.add_argument("--threat-model", type=Path, required=True)
    conclusion_certify_cmd.add_argument("--reference-demo-report", type=Path, required=True)
    conclusion_certify_cmd.add_argument("--docs-index", type=Path, required=True)
    conclusion_certify_cmd.add_argument("--schemas-frozen", action="store_true")
    conclusion_certify_cmd.add_argument("--out", type=Path)

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

    artifact_put_cmd = subcommands.add_parser("artifact-put", help="Store an artifact by content hash.")
    artifact_put_cmd.add_argument("file", type=Path)
    artifact_put_cmd.add_argument("--store-root", type=Path, required=True)
    artifact_put_cmd.add_argument("--logical-name", required=True)
    artifact_put_cmd.add_argument("--media-type", default="application/json")
    artifact_put_cmd.add_argument("--raw", action="store_true")
    artifact_put_cmd.add_argument("--normalized", action="store_true")
    artifact_put_cmd.add_argument("--out", type=Path)

    artifact_get_cmd = subcommands.add_parser("artifact-get", help="Resolve an artifact hash from a store manifest.")
    artifact_get_cmd.add_argument("--store-root", type=Path, required=True)
    artifact_get_cmd.add_argument("--manifest", type=Path, required=True)
    artifact_get_cmd.add_argument("--hash", required=True)
    artifact_get_cmd.add_argument("--out", type=Path)

    sign_evidence_cmd = subcommands.add_parser("sign-evidence", help="Sign a JSON evidence payload.")
    sign_evidence_cmd.add_argument("payload", type=Path)
    sign_evidence_cmd.add_argument("--producer-id", required=True)
    sign_evidence_cmd.add_argument("--key-id", required=True)
    sign_evidence_cmd.add_argument("--secret", required=True)
    sign_evidence_cmd.add_argument("--envelope-id", required=True)
    sign_evidence_cmd.add_argument("--out", type=Path)

    verify_evidence_cmd = subcommands.add_parser("verify-evidence", help="Verify a signed evidence envelope.")
    verify_evidence_cmd.add_argument("envelope", type=Path)
    verify_evidence_cmd.add_argument("--registry", type=Path, required=True)
    verify_evidence_cmd.add_argument("--secret", action="append", default=[])
    verify_evidence_cmd.add_argument("--high-assurance", action="store_true")
    verify_evidence_cmd.add_argument("--out", type=Path)

    draft_cmd = subcommands.add_parser(
        "draft-controlled", help="Create a controlled-text draft artifact."
    )
    draft_cmd.add_argument("original", type=Path)
    draft_cmd.add_argument("--suggested", type=Path, required=True)
    draft_cmd.add_argument("--out", type=Path, required=True)
    draft_cmd.add_argument("--timestamp", default="2026-06-01T00:00:00Z")
    draft_cmd.add_argument("--method", choices=["manual"], default="manual")
    draft_cmd.add_argument("--model")
    draft_cmd.add_argument("--prompt")

    intake_draft_cmd = subcommands.add_parser(
        "intake-draft", help="Create free-form intake and controlled rewrite proposal artifacts."
    )
    intake_draft_cmd.add_argument("original", type=Path)
    intake_draft_cmd.add_argument(
        "--suggested",
        type=Path,
        help="Path to pre-written controlled text (required for --method manual).",
    )
    intake_draft_cmd.add_argument("--out", type=Path, required=True)
    intake_draft_cmd.add_argument("--intake-out", type=Path)
    intake_draft_cmd.add_argument("--intake-id", required=True)
    intake_draft_cmd.add_argument("--proposal-id", required=True)
    intake_draft_cmd.add_argument("--submitted-by")
    intake_draft_cmd.add_argument("--submitted-at", default="2026-06-01T00:00:00Z")
    intake_draft_cmd.add_argument("--timestamp", default="2026-06-01T00:00:00Z")
    intake_draft_cmd.add_argument("--method", choices=["manual", "llm", "rule_based"], default="manual")
    intake_draft_cmd.add_argument("--model")
    intake_draft_cmd.add_argument("--prompt")
    intake_draft_cmd.add_argument(
        "--fixture",
        type=Path,
        help="Path to a recorded LLM fixture for offline use (--method llm only).",
    )

    intake_approve_cmd = subcommands.add_parser(
        "intake-approve", help="Approve or reject a controlled rewrite proposal."
    )
    intake_approve_cmd.add_argument("proposal", type=Path)
    intake_approve_cmd.add_argument("--approval-id", required=True)
    intake_approve_cmd.add_argument("--approved-by", required=True)
    intake_approve_cmd.add_argument("--approved-at", default="2026-06-01T00:00:00Z")
    intake_approve_cmd.add_argument("--decision", choices=["approved", "rejected"], default="approved")
    intake_approve_cmd.add_argument("--out", type=Path, required=True)

    intake_diff_cmd = subcommands.add_parser(
        "intake-diff", help="Print the hash-linked diff for a controlled rewrite proposal."
    )
    intake_diff_cmd.add_argument("proposal", type=Path)

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

    controlled_semantics_cmd = subcommands.add_parser(
        "controlled-semantics", help="Emit the DSL v3 controlled requirement semantics reference."
    )
    controlled_semantics_cmd.add_argument("--out", type=Path)

    formal_claim_cmd = subcommands.add_parser(
        "formal-claim", help="Lower compositional requirement IR to formal claim IR."
    )
    formal_claim_cmd.add_argument("file", type=Path)
    formal_claim_cmd.add_argument("--out", type=Path)

    formal_claim_semantics_cmd = subcommands.add_parser(
        "formal-claim-semantics",
        help="Emit the completed formal-claim semantics reference.",
    )
    formal_claim_semantics_cmd.add_argument("--out", type=Path)

    semantic_translate_cmd = subcommands.add_parser(
        "semantic-translate", help="Translate controlled DSL v3 text to semantic IR and formal claim IR."
    )
    semantic_translate_cmd.add_argument("file", type=Path)
    semantic_translate_cmd.add_argument("--requirement-id", required=True)
    semantic_translate_cmd.add_argument("--title", required=True)
    semantic_translate_cmd.add_argument("--translation-id")
    semantic_translate_cmd.add_argument("--out", type=Path)
    semantic_translate_cmd.add_argument(
        "--ensemble-client",
        action="append",
        dest="ensemble_clients",
        default=[],
        metavar="CLIENT",
        help=(
            "PA-5 decomposition ensemble client. Repeat for multiple clients (≥2 triggers check). "
            "Formats: 'live' (AnthropicDecompositionClient with default model), "
            "'live:<model-id>' (AnthropicDecompositionClient with given model), "
            "'recorded:<path>' (RecordedDecompositionClient replaying a RequirementIRV2 JSON fixture)."
        ),
    )

    semantic_agreement_cmd = subcommands.add_parser(
        "semantic-agreement", help="Compare formal claim candidates with semantic equivalence profiles."
    )
    semantic_agreement_cmd.add_argument("formal_claim_report", nargs="+", type=Path)
    semantic_agreement_cmd.add_argument("--candidate-id", action="append", default=[])
    semantic_agreement_cmd.add_argument("--translator-id", action="append", default=[])
    semantic_agreement_cmd.add_argument("--resolution-candidate-id")
    semantic_agreement_cmd.add_argument("--resolution-candidate-hash")
    semantic_agreement_cmd.add_argument("--resolution-reason")
    semantic_agreement_cmd.add_argument("--approved-by")
    semantic_agreement_cmd.add_argument("--approved-at")
    semantic_agreement_cmd.add_argument("--out", type=Path)

    translation_repair_cmd = subcommands.add_parser(
        "translation-repair", help="Build source-span repair prompts for translation refusal or disagreement."
    )
    translation_repair_cmd.add_argument("--translation-report", type=Path)
    translation_repair_cmd.add_argument("--agreement-report", type=Path)
    translation_repair_cmd.add_argument("--out", type=Path)

    tla_projection_cmd = subcommands.add_parser(
        "tla-projection", help="Build the TLA projection semantics report."
    )
    tla_projection_cmd.add_argument("file", type=Path)
    tla_projection_cmd.add_argument("--out", type=Path)

    translator_agreement_cmd = subcommands.add_parser(
        "translator-agreement", help="Compare multiple requirement translations structurally."
    )
    translator_agreement_cmd.add_argument("input", type=Path)
    translator_agreement_cmd.add_argument("--out", type=Path)

    logical_translator_agreement_cmd = subcommands.add_parser(
        "logical-translator-agreement", help="Compare translations with logical equivalence methods."
    )
    logical_translator_agreement_cmd.add_argument("input", type=Path)
    logical_translator_agreement_cmd.add_argument("--out", type=Path)

    translate_candidates_cmd = subcommands.add_parser(
        "translate-candidates", help="Build a multi-pass translator candidate run."
    )
    translate_candidates_cmd.add_argument("file", type=Path)
    translate_candidates_cmd.add_argument("--run-id", required=True)
    translate_candidates_cmd.add_argument("--requirement-id", required=True)
    translate_candidates_cmd.add_argument("--title", required=True)
    translate_candidates_cmd.add_argument("--out", type=Path, required=True)

    translate_compare_cmd = subcommands.add_parser(
        "translate-compare", help="Compare translator workbench candidates."
    )
    translate_compare_cmd.add_argument("run", type=Path)
    translate_compare_cmd.add_argument("--out", type=Path)

    translate_select_cmd = subcommands.add_parser(
        "translate-select", help="Select a reviewed translator candidate."
    )
    translate_select_cmd.add_argument("run", type=Path)
    translate_select_cmd.add_argument("--candidate-id", required=True)
    translate_select_cmd.add_argument("--approved-by", required=True)
    translate_select_cmd.add_argument("--approved-at", default="2026-06-01T00:00:00Z")
    translate_select_cmd.add_argument("--run-out", type=Path)
    translate_select_cmd.add_argument("--out", type=Path, required=True)

    provenance_graph_cmd = subcommands.add_parser(
        "provenance-graph", help="Build bidirectional text/IR/formal provenance graph."
    )
    provenance_graph_cmd.add_argument("--requirement-ir", type=Path, required=True)
    provenance_graph_cmd.add_argument("--lowered", type=Path)
    provenance_graph_cmd.add_argument("--out", type=Path)

    clarify_cmd = subcommands.add_parser(
        "clarify", help="Emit clarification requests from translator agreement."
    )
    clarify_cmd.add_argument("--agreement", type=Path, required=True)
    clarify_cmd.add_argument("--out", type=Path)

    apply_clarification_cmd = subcommands.add_parser(
        "apply-clarification", help="Apply a clarification response to controlled text."
    )
    apply_clarification_cmd.add_argument("--controlled", type=Path, required=True)
    apply_clarification_cmd.add_argument("--response", type=Path, required=True)
    apply_clarification_cmd.add_argument("--out", type=Path, required=True)

    review_open_cmd = subcommands.add_parser(
        "review-open", help="Open a hash-bound requirement review workflow."
    )
    review_open_cmd.add_argument("--review-id", required=True)
    review_open_cmd.add_argument("--requirement-id", required=True)
    review_open_cmd.add_argument("--artifact", action="append", required=True)
    review_open_cmd.add_argument("--out", type=Path, required=True)

    review_approve_cmd = subcommands.add_parser(
        "review-approve", help="Record a hash-bound review approval."
    )
    review_approve_cmd.add_argument("workflow", type=Path)
    review_approve_cmd.add_argument("--role", required=True)
    review_approve_cmd.add_argument("--reviewer", required=True)
    review_approve_cmd.add_argument("--decision", choices=["approved", "needs_review", "rejected"], default="approved")
    review_approve_cmd.add_argument("--approved-at", default="2026-06-01T00:00:00Z")
    review_approve_cmd.add_argument("--artifact", action="append", default=[])
    review_approve_cmd.add_argument("--checklist", type=Path)
    review_approve_cmd.add_argument("--self-audit", action="store_true")
    review_approve_cmd.add_argument("--self-audit-delay-hours", type=int)
    review_approve_cmd.add_argument("--out", type=Path, required=True)

    review_status_cmd = subcommands.add_parser(
        "review-status", help="Report whether review approvals are current."
    )
    review_status_cmd.add_argument("workflow", type=Path)
    review_status_cmd.add_argument("--artifact", action="append", default=[])
    review_status_cmd.add_argument("--required-role", action="append", default=[])
    review_status_cmd.add_argument("--out", type=Path)

    refusal_render_cmd = subcommands.add_parser(
        "refusal-render", help="Render an end-to-end gate refusal report."
    )
    refusal_render_cmd.add_argument("gate_report", type=Path)
    refusal_render_cmd.add_argument("--out", type=Path)
    refusal_render_cmd.add_argument("--markdown-out", type=Path)

    python_source_impact_cmd = subcommands.add_parser(
        "python-source-impact", help="Run deterministic Python source impact analysis."
    )
    python_source_impact_cmd.add_argument("--manifest", type=Path, required=True)
    python_source_impact_cmd.add_argument("--symbol", action="append", required=True)
    python_source_impact_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    python_source_impact_cmd.add_argument("--out", type=Path)

    python_source_impact_context_cmd = subcommands.add_parser(
        "python-source-impact-context", help="Run contextual Python source impact analysis."
    )
    python_source_impact_context_cmd.add_argument("--manifest", type=Path, required=True)
    python_source_impact_context_cmd.add_argument("--symbol", action="append", required=True)
    python_source_impact_context_cmd.add_argument("--trace-artifact", type=Path)
    python_source_impact_context_cmd.add_argument("--semantic-suggestion", action="append", default=[])
    python_source_impact_context_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    python_source_impact_context_cmd.add_argument("--out", type=Path)

    python_source_impact_production_cmd = subcommands.add_parser(
        "python-source-impact-production", help="Run production v2 Python source impact analysis."
    )
    python_source_impact_production_cmd.add_argument("--manifest", type=Path, required=True)
    python_source_impact_production_cmd.add_argument("--symbol", action="append", required=True)
    python_source_impact_production_cmd.add_argument("--trace-artifact", type=Path)
    python_source_impact_production_cmd.add_argument("--semantic-suggestion", action="append", default=[])
    python_source_impact_production_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    python_source_impact_production_cmd.add_argument("--out", type=Path)

    javascript_source_impact_cmd = subcommands.add_parser(
        "javascript-source-impact", help="Run deterministic JavaScript source impact analysis."
    )
    javascript_source_impact_cmd.add_argument("--manifest", type=Path, required=True)
    javascript_source_impact_cmd.add_argument("--symbol", action="append", required=True)
    javascript_source_impact_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    javascript_source_impact_cmd.add_argument("--out", type=Path)

    javascript_source_impact_context_cmd = subcommands.add_parser(
        "javascript-source-impact-context", help="Run contextual JavaScript source impact analysis."
    )
    javascript_source_impact_context_cmd.add_argument("--manifest", type=Path, required=True)
    javascript_source_impact_context_cmd.add_argument("--symbol", action="append", required=True)
    javascript_source_impact_context_cmd.add_argument("--trace-artifact", type=Path)
    javascript_source_impact_context_cmd.add_argument("--semantic-suggestion", action="append", default=[])
    javascript_source_impact_context_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    javascript_source_impact_context_cmd.add_argument("--out", type=Path)

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

    s_and_r_composition_cmd = subcommands.add_parser(
        "s-and-r-composition", help="Build the hash-bound S-and-R composition report."
    )
    s_and_r_composition_cmd.add_argument("--requirement-ir", type=Path, required=True)
    s_and_r_composition_cmd.add_argument("--lowered", type=Path, required=True)
    s_and_r_composition_cmd.add_argument("--registry", type=Path, required=True)
    s_and_r_composition_cmd.add_argument("--impact", type=Path, required=True)
    s_and_r_composition_cmd.add_argument("--system-consistency", type=Path, required=True)
    s_and_r_composition_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    s_and_r_composition_cmd.add_argument("--out", type=Path)

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

    coverage_manifest_migrate_cmd = subcommands.add_parser(
        "coverage-manifest-v2-migrate", help="Migrate code/spec manifest v1 to coverage manifest v2."
    )
    coverage_manifest_migrate_cmd.add_argument("--manifest", type=Path, required=True)
    coverage_manifest_migrate_cmd.add_argument("--registry", type=Path, required=True)
    coverage_manifest_migrate_cmd.add_argument("--out", type=Path)

    coverage_gate_v2_cmd = subcommands.add_parser(
        "coverage-gate-v2", help="Gate affected modules against coverage manifest v2."
    )
    coverage_gate_v2_cmd.add_argument("--impact", type=Path, required=True)
    coverage_gate_v2_cmd.add_argument("--manifest", type=Path, required=True)
    coverage_gate_v2_cmd.add_argument("--threshold", type=float, default=1.0)
    coverage_gate_v2_cmd.add_argument("--out", type=Path)

    trace_align_cmd = subcommands.add_parser(
        "trace-align", help="Classify normalized traces against requirement/spec context."
    )
    trace_align_cmd.add_argument("--requirement-ir", type=Path, required=True)
    trace_align_cmd.add_argument("--trace-artifact", type=Path, required=True)
    trace_align_cmd.add_argument("--coverage", type=Path, required=True)
    trace_align_cmd.add_argument("--out", type=Path)

    trace_replay_cmd = subcommands.add_parser(
        "trace-replay", help="Replay normalized traces against compositional requirement obligations."
    )
    trace_replay_cmd.add_argument("--requirement-ir", type=Path, required=True)
    trace_replay_cmd.add_argument("--trace-artifact", type=Path, required=True)
    trace_replay_cmd.add_argument("--coverage", type=Path, required=True)
    trace_replay_cmd.add_argument("--out", type=Path)

    spec_extract_cmd = subcommands.add_parser(
        "spec-extract", help="Generate draft candidate specs for under-specified modules."
    )
    spec_extract_cmd.add_argument("--requirement-ir", type=Path, required=True)
    spec_extract_cmd.add_argument("--impact", type=Path, required=True)
    spec_extract_cmd.add_argument("--registry", type=Path, required=True)
    spec_extract_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_extract_cmd.add_argument("--code-presentation", type=Path)
    spec_extract_cmd.add_argument("--trace-replay", type=Path)
    spec_extract_cmd.add_argument("--out", type=Path)

    specula_extract_cmd = subcommands.add_parser(
        "specula-extract", help="Generate candidate-only specs with structural validation."
    )
    specula_extract_cmd.add_argument("--requirement-ir", type=Path, required=True)
    specula_extract_cmd.add_argument("--impact", type=Path, required=True)
    specula_extract_cmd.add_argument("--registry", type=Path, required=True)
    specula_extract_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    specula_extract_cmd.add_argument("--code-presentation", type=Path)
    specula_extract_cmd.add_argument("--trace-replay", type=Path)
    specula_extract_cmd.add_argument("--out", type=Path)

    candidate_review_cmd = subcommands.add_parser(
        "candidate-spec-review", help="Promote or reject a candidate spec with hash-bound review."
    )
    candidate_review_cmd.add_argument("candidate", type=Path)
    candidate_review_cmd.add_argument("--decision", choices=["promote", "reject"], required=True)
    candidate_review_cmd.add_argument("--reviewer-id", required=True)
    candidate_review_cmd.add_argument("--reviewed-at", default="2026-06-03T00:00:00Z")
    candidate_review_cmd.add_argument("--approved-hash")
    candidate_review_cmd.add_argument("--version", default="1")
    candidate_review_cmd.add_argument("--rejection-reason", action="append", default=[])
    candidate_review_cmd.add_argument("--checklist", action="append", default=[])
    candidate_review_cmd.add_argument("--out", type=Path)

    spec_drift_cmd = subcommands.add_parser(
        "spec-drift", help="Detect source/spec drift from a code-to-spec manifest."
    )
    spec_drift_cmd.add_argument("--manifest", type=Path, required=True)
    spec_drift_cmd.add_argument("--registry", type=Path)
    spec_drift_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_drift_cmd.add_argument("--out", type=Path)
    spec_drift_cmd.add_argument("--updated-registry-out", type=Path)

    spec_freshness_lock_cmd = subcommands.add_parser(
        "spec-freshness-lock", help="Build a spec freshness lockfile."
    )
    spec_freshness_lock_cmd.add_argument("--manifest", type=Path, required=True)
    spec_freshness_lock_cmd.add_argument("--registry", type=Path, required=True)
    spec_freshness_lock_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_freshness_lock_cmd.add_argument("--lock-id", default="spec-freshness")
    spec_freshness_lock_cmd.add_argument("--out", type=Path)

    spec_freshness_lock_v2_cmd = subcommands.add_parser(
        "spec-freshness-lock-v2", help="Build a timestamped spec freshness lockfile v2."
    )
    spec_freshness_lock_v2_cmd.add_argument("--manifest", type=Path, required=True)
    spec_freshness_lock_v2_cmd.add_argument("--registry", type=Path, required=True)
    spec_freshness_lock_v2_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_freshness_lock_v2_cmd.add_argument("--lock-id", default="spec-freshness")
    spec_freshness_lock_v2_cmd.add_argument("--validated-at", default="2026-06-03T00:00:00Z")
    spec_freshness_lock_v2_cmd.add_argument("--out", type=Path)

    spec_freshness_check_cmd = subcommands.add_parser(
        "spec-freshness-check", help="Validate a spec freshness lockfile."
    )
    spec_freshness_check_cmd.add_argument("--manifest", type=Path, required=True)
    spec_freshness_check_cmd.add_argument("--registry", type=Path, required=True)
    spec_freshness_check_cmd.add_argument("--lockfile", type=Path, required=True)
    spec_freshness_check_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_freshness_check_cmd.add_argument("--out", type=Path)

    spec_freshness_ci_cmd = subcommands.add_parser(
        "spec-freshness-ci", help="Validate freshness lockfile v2 for CI drift gating."
    )
    spec_freshness_ci_cmd.add_argument("--manifest", type=Path, required=True)
    spec_freshness_ci_cmd.add_argument("--registry", type=Path, required=True)
    spec_freshness_ci_cmd.add_argument("--lockfile", type=Path, required=True)
    spec_freshness_ci_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    spec_freshness_ci_cmd.add_argument("--now")
    spec_freshness_ci_cmd.add_argument("--max-validation-age-hours", type=float)
    spec_freshness_ci_cmd.add_argument("--out", type=Path)

    delta_extract_cmd = subcommands.add_parser(
        "delta-extract", help="Extract actionable deltas from failed verification reports."
    )
    delta_extract_cmd.add_argument("--self-consistency", type=Path)
    delta_extract_cmd.add_argument("--system-consistency", type=Path)
    delta_extract_cmd.add_argument("--spec-coverage", type=Path)
    delta_extract_cmd.add_argument("--trace-replay", type=Path)
    delta_extract_cmd.add_argument("--spec-drift", type=Path)
    delta_extract_cmd.add_argument("--out", type=Path)
    delta_extract_cmd.add_argument("--markdown-out", type=Path)

    verification_budget_cmd = subcommands.add_parser(
        "verification-budget", help="Build a verification budget and abstraction report."
    )
    verification_budget_cmd.add_argument("--requirement-ir", type=Path, required=True)
    verification_budget_cmd.add_argument(
        "--requirement-class",
        choices=["safety", "liveness", "trace_grounded", "system_compatibility"],
        required=True,
    )
    verification_budget_cmd.add_argument("--assumption", action="append", default=[])
    verification_budget_cmd.add_argument("--out", type=Path)

    evidence_producers_cmd = subcommands.add_parser(
        "evidence-producers-validate",
        help="Validate real producer metadata for backend evidence.",
    )
    evidence_producers_cmd.add_argument("--backend-result", action="append", type=Path, default=[])
    evidence_producers_cmd.add_argument("--producer-mapping", type=Path)
    evidence_producers_cmd.add_argument("--out", type=Path)

    proof_boundary_cmd = subcommands.add_parser(
        "proof-evidence-boundary", help="Classify bounded vs inductive proof evidence."
    )
    proof_boundary_cmd.add_argument("proof_object", type=Path)
    proof_boundary_cmd.add_argument("--out", type=Path)

    proof_backend_boundary_cmd = subcommands.add_parser(
        "proof-backend-boundary",
        help="Validate proof-producing backend evidence requirements.",
    )
    proof_backend_boundary_cmd.add_argument("--backend-result", type=Path, required=True)
    proof_backend_boundary_cmd.add_argument("--producer-mapping", type=Path)
    proof_backend_boundary_cmd.add_argument("--proof-artifact", action="append", default=[])
    proof_backend_boundary_cmd.add_argument("--checker-command", nargs=argparse.REMAINDER)
    proof_backend_boundary_cmd.add_argument("--out", type=Path)

    backend_agreement_cmd = subcommands.add_parser(
        "backend-agreement",
        help="Compare overlapping backend results and report hidden disagreements.",
    )
    backend_agreement_cmd.add_argument("--backend-result", action="append", type=Path, default=[])
    backend_agreement_cmd.add_argument(
        "--formal-backend-response", action="append", type=Path, default=[]
    )
    backend_agreement_cmd.add_argument("--overlap-key")
    backend_agreement_cmd.add_argument(
        "--policy", choices=["blocking", "report_only"], default="blocking"
    )
    backend_agreement_cmd.add_argument("--out", type=Path)

    counterexample_cmd = subcommands.add_parser(
        "counterexample-normalize", help="Normalize backend counterexamples into portable traces."
    )
    counterexample_cmd.add_argument("--formal-backend-response", action="append", type=Path, default=[])
    counterexample_cmd.add_argument("--out", type=Path)

    counterexample_explain_cmd = subcommands.add_parser(
        "counterexample-explain",
        help="Explain normalized counterexamples with formal-claim source mappings.",
    )
    counterexample_explain_cmd.add_argument("--normalization", type=Path, required=True)
    counterexample_explain_cmd.add_argument("--formal-claim", type=Path)
    counterexample_explain_cmd.add_argument("--formal-backend-response", action="append", type=Path, default=[])
    counterexample_explain_cmd.add_argument("--out", type=Path)
    counterexample_explain_cmd.add_argument("--markdown-out", type=Path)

    proof_object_cmd = subcommands.add_parser(
        "proof-object", help="Aggregate backend evidence into a proof closure object."
    )
    proof_object_cmd.add_argument("--requirement-ir", type=Path, required=True)
    proof_object_cmd.add_argument("--system-consistency", action="append", type=Path, default=[])
    proof_object_cmd.add_argument("--formal-backend-response", action="append", type=Path, default=[])
    proof_object_cmd.add_argument("--backend-result", action="append", type=Path, default=[])
    proof_object_cmd.add_argument("--spec-coverage", type=Path)
    proof_object_cmd.add_argument("--trace-alignment", type=Path)
    proof_object_cmd.add_argument("--backend-agreement", type=Path)
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

    cross_language_cmd = subcommands.add_parser(
        "cross-language-proof", help="Build a cross-language proof object from manifests and traces."
    )
    cross_language_cmd.add_argument("--proof-object", type=Path, required=True)
    cross_language_cmd.add_argument("--source-manifest", action="append", type=Path, default=[])
    cross_language_cmd.add_argument("--trace-artifact", action="append", type=Path, default=[])
    cross_language_cmd.add_argument("--causal-link", action="append", default=[])
    cross_language_cmd.add_argument("--out", type=Path)
    cross_language_cmd.add_argument("--fail-on-blocking", action="store_true")

    requirement_gate_cmd = subcommands.add_parser(
        "requirement-gate",
        help="Run the end-to-end requirement intake, verification, and closure gate.",
    )
    requirement_gate_cmd.add_argument("file", type=Path)
    requirement_gate_cmd.add_argument("--requirement-id", required=True)
    requirement_gate_cmd.add_argument("--title", required=True)
    requirement_gate_cmd.add_argument("--source-manifest", type=Path, required=True)
    requirement_gate_cmd.add_argument(
        "--source-language", choices=["python", "javascript"], required=True
    )
    requirement_gate_cmd.add_argument("--symbol", action="append", required=True)
    requirement_gate_cmd.add_argument("--registry", type=Path, required=True)
    requirement_gate_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    requirement_gate_cmd.add_argument("--artifact-dir", type=Path, required=True)
    requirement_gate_cmd.add_argument("--out", type=Path)
    requirement_gate_cmd.add_argument("--markdown-out", type=Path)
    requirement_gate_cmd.add_argument("--downstream-action", default="merge")
    requirement_gate_cmd.add_argument("--self-check-backend", default="tla-runner")
    requirement_gate_cmd.add_argument("--checker-id")
    requirement_gate_cmd.add_argument("--checker-command", nargs=argparse.REMAINDER)
    requirement_gate_cmd.add_argument("--timeout-seconds", type=int)
    requirement_gate_cmd.add_argument("--max-depth", type=int)
    requirement_gate_cmd.add_argument("--max-states", type=int)
    requirement_gate_cmd.add_argument("--memory-budget-mb", type=int)
    requirement_gate_cmd.add_argument("--solver-option", action="append", default=[])
    requirement_gate_cmd.add_argument("--expected-exit-code", type=int, default=0)
    requirement_gate_cmd.add_argument("--tool-version")
    requirement_gate_cmd.add_argument("--tool-version-command", nargs="+")
    requirement_gate_cmd.add_argument(
        "--output-limit-bytes", type=int, default=DEFAULT_RUNNER_OUTPUT_LIMIT_BYTES
    )
    requirement_gate_cmd.add_argument("--fail-on-refusal", action="store_true")

    benchmark_corpus_cmd = subcommands.add_parser(
        "benchmark-corpus",
        help="Evaluate observed requirement-gate results against a benchmark corpus.",
    )
    benchmark_corpus_cmd.add_argument("--corpus", type=Path, required=True)
    benchmark_corpus_cmd.add_argument("--results", type=Path, required=True)
    benchmark_corpus_cmd.add_argument("--out", type=Path)

    benchmark_evaluate_cmd = subcommands.add_parser(
        "benchmark-evaluate", help="Evaluate benchmark corpus with release metrics and budgets."
    )
    benchmark_evaluate_cmd.add_argument("--corpus", type=Path, required=True)
    benchmark_evaluate_cmd.add_argument("--results", type=Path, required=True)
    benchmark_evaluate_cmd.add_argument("--false-closure-budget", type=float, default=0.0)
    benchmark_evaluate_cmd.add_argument("--out", type=Path)

    benchmark_translation_cmd = subcommands.add_parser(
        "benchmark-translation",
        help="Evaluate translation workbench results against a requirement translation corpus.",
    )
    benchmark_translation_cmd.add_argument("--corpus", type=Path, required=True)
    benchmark_translation_cmd.add_argument("--results", type=Path, required=True)
    benchmark_translation_cmd.add_argument("--out", type=Path)

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

    waiver_audit_cmd = subcommands.add_parser(
        "waiver-audit", help="Audit waiver governance against the gate policy."
    )
    waiver_audit_cmd.add_argument("--policy", type=Path, required=True)
    waiver_audit_cmd.add_argument("--waiver", action="append", type=Path, default=[])
    waiver_audit_cmd.add_argument("--out", type=Path)

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

    trace_gate_cmd = subcommands.add_parser(
        "trace-validation-gate", help="Gate trace grounding against coverage and freshness context."
    )
    trace_gate_cmd.add_argument("--requirement-ir", type=Path, required=True)
    trace_gate_cmd.add_argument("--trace-artifact", type=Path, required=True)
    trace_gate_cmd.add_argument("--coverage", type=Path, required=True)
    trace_gate_cmd.add_argument("--freshness", type=Path)
    trace_gate_cmd.add_argument("--allow-lossy", action="store_true")
    trace_gate_cmd.add_argument("--out", type=Path)
    trace_gate_cmd.add_argument("--markdown-out", type=Path)

    trace_normalize_cmd = subcommands.add_parser(
        "trace-normalize", help="Normalize raw trace artifact to normalized trace schema."
    )
    trace_normalize_cmd.add_argument("raw", type=Path)
    trace_normalize_cmd.add_argument("--out", type=Path)

    trace_extract_cmd = subcommands.add_parser(
        "trace-extract", help="Extract normalized traces through a registered local JSON producer."
    )
    trace_extract_cmd.add_argument("--registry", type=Path, required=True)
    trace_extract_cmd.add_argument("--producer-id", required=True)
    trace_extract_cmd.add_argument("--trace-source", required=True)
    trace_extract_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    trace_extract_cmd.add_argument("--requirement-id", action="append", default=[])
    trace_extract_cmd.add_argument("--run-id")
    trace_extract_cmd.add_argument("--out", type=Path)

    trace_producer_evidence_cmd = subcommands.add_parser(
        "trace-producer-evidence", help="Classify trace producer extraction evidence for closure."
    )
    trace_producer_evidence_cmd.add_argument("--registry", type=Path, required=True)
    trace_producer_evidence_cmd.add_argument("--producer-id", required=True)
    trace_producer_evidence_cmd.add_argument("--extraction-result", type=Path, required=True)
    trace_producer_evidence_cmd.add_argument("--high-assurance", action="store_true")
    trace_producer_evidence_cmd.add_argument("--require-signature", action="store_true")
    trace_producer_evidence_cmd.add_argument("--allow-missing-replay", action="store_true")
    trace_producer_evidence_cmd.add_argument("--out", type=Path)

    adapter_certify_cmd = subcommands.add_parser(
        "adapter-certify", help="Run adapter certification suite for production adapters."
    )
    adapter_certify_cmd.add_argument(
        "--language",
        choices=["solidity", "go", "typescript", "javascript", "rust", "java"],
        required=True,
    )
    adapter_certify_cmd.add_argument("--manifest", type=Path, required=True)
    adapter_certify_cmd.add_argument("--symbol", action="append", default=[])
    adapter_certify_cmd.add_argument("--required-capability", action="append", default=[])
    adapter_certify_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    adapter_certify_cmd.add_argument("--out", type=Path)

    adapter_capabilities_cmd = subcommands.add_parser(
        "adapter-capabilities", help="Emit a production adapter v2 capability contract."
    )
    adapter_capabilities_cmd.add_argument(
        "--language",
        choices=["solidity", "go", "typescript", "javascript", "rust", "java"],
        required=True,
    )
    adapter_capabilities_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    adapter_capabilities_cmd.add_argument("--out", type=Path)

    adapter_plugin_validate_cmd = subcommands.add_parser(
        "adapter-plugin-validate",
        help="Validate an adapter plugin manifest against a certification report.",
    )
    adapter_plugin_validate_cmd.add_argument("--plugin-manifest", type=Path, required=True)
    adapter_plugin_validate_cmd.add_argument("--certification-report", type=Path, required=True)
    adapter_plugin_validate_cmd.add_argument("--out", type=Path)

    ci_pr_gate_cmd = subcommands.add_parser(
        "ci-pr-gate", help="Render a CI/PR gate report from an end-to-end gate report."
    )
    ci_pr_gate_cmd.add_argument("gate_report", type=Path)
    ci_pr_gate_cmd.add_argument("--mode", choices=["report_only", "soft_gate", "hard_gate"], default="report_only")
    ci_pr_gate_cmd.add_argument("--out", type=Path)
    ci_pr_gate_cmd.add_argument("--markdown-out", type=Path)

    extended_gate_cmd = subcommands.add_parser(
        "requirement-gate-extended",
        help="Build the milestone group 9 extended pipeline gate from an end-to-end gate report.",
    )
    extended_gate_cmd.add_argument("gate_report", type=Path)
    extended_gate_cmd.add_argument("--stage-status", action="append", default=[])
    extended_gate_cmd.add_argument("--artifact-hash", action="append", default=[])
    extended_gate_cmd.add_argument("--artifact-path", action="append", default=[])
    extended_gate_cmd.add_argument("--evidence-level", action="append", default=[])
    extended_gate_cmd.add_argument("--out", type=Path)

    ci_adoption_cmd = subcommands.add_parser(
        "ci-adoption", help="Build an extended CI adoption report from an extended gate report."
    )
    ci_adoption_cmd.add_argument("extended_gate_report", type=Path)
    ci_adoption_cmd.add_argument("--mode", choices=["report_only", "soft_gate", "hard_gate"])
    ci_adoption_cmd.add_argument("--waiver-id", action="append", default=[])
    ci_adoption_cmd.add_argument("--out", type=Path)
    ci_adoption_cmd.add_argument("--markdown-out", type=Path)

    benchmark_extended_cmd = subcommands.add_parser(
        "benchmark-extended", help="Build an extended release benchmark report."
    )
    benchmark_extended_cmd.add_argument("--base-report", type=Path, required=True)
    benchmark_extended_cmd.add_argument(
        "--dimension",
        action="append",
        default=[],
        help="Dimension in name=score,total,passed,failed,threshold form.",
    )
    benchmark_extended_cmd.add_argument("--threshold", action="append", default=[])
    benchmark_extended_cmd.add_argument("--out", type=Path)

    reference_demo_extended_cmd = subcommands.add_parser(
        "reference-demo-extended",
        help="Validate the extended reference demo with gate reports and replay bundles.",
    )
    reference_demo_extended_cmd.add_argument("--manifest", type=Path, required=True)
    reference_demo_extended_cmd.add_argument("--base-report", type=Path, required=True)
    reference_demo_extended_cmd.add_argument("--gate-report", action="append", type=Path, required=True)
    reference_demo_extended_cmd.add_argument("--replay-bundle-hash", action="append", default=[])
    reference_demo_extended_cmd.add_argument("--out", type=Path)

    public_docs_freeze_cmd = subcommands.add_parser(
        "public-docs-freeze", help="Build the public SDK and documentation freeze report."
    )
    public_docs_freeze_cmd.add_argument("--index", type=Path, required=True)
    public_docs_freeze_cmd.add_argument("--coverage-report", type=Path, required=True)
    public_docs_freeze_cmd.add_argument("--schema-hash", action="append", default=[])
    public_docs_freeze_cmd.add_argument("--topic", action="append", default=[])
    public_docs_freeze_cmd.add_argument("--commitment", action="append", default=[])
    public_docs_freeze_cmd.add_argument("--out", type=Path)

    tcb_review_cmd = subcommands.add_parser(
        "tcb-review", help="Build the extended TCB review report."
    )
    tcb_review_cmd.add_argument("threat_model", type=Path)
    tcb_review_cmd.add_argument("--release-artifact-hash", action="append", default=[])
    tcb_review_cmd.add_argument("--accepted-residual-risk", action="append", default=[])
    tcb_review_cmd.add_argument("--out", type=Path)

    extended_certify_cmd = subcommands.add_parser(
        "extended-conclusion-certify",
        help="Build the milestone group 9 extended conclusion certification report.",
    )
    extended_certify_cmd.add_argument("--release-id", required=True)
    extended_certify_cmd.add_argument("--gate-report", type=Path, required=True)
    extended_certify_cmd.add_argument("--ci-report", type=Path, required=True)
    extended_certify_cmd.add_argument("--benchmark-report", type=Path, required=True)
    extended_certify_cmd.add_argument("--reference-demo-report", type=Path, required=True)
    extended_certify_cmd.add_argument("--docs-freeze-report", type=Path, required=True)
    extended_certify_cmd.add_argument("--tcb-review-report", type=Path, required=True)
    extended_certify_cmd.add_argument("--schemas-frozen", action="store_true")
    extended_certify_cmd.add_argument("--producer-evidence-present", action="store_true")
    extended_certify_cmd.add_argument("--release-bundle-hash")
    extended_certify_cmd.add_argument("--signed-release-bundle-hash")
    extended_certify_cmd.add_argument("--allow-unsigned-release-bundle", action="store_true")
    extended_certify_cmd.add_argument("--out", type=Path)

    reference_demo_cmd = subcommands.add_parser(
        "reference-demo-check", help="Validate reference demo artifact presence."
    )
    reference_demo_cmd.add_argument("manifest", type=Path)
    reference_demo_cmd.add_argument("--project-root", type=Path, default=Path.cwd())
    reference_demo_cmd.add_argument("--out", type=Path)

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
        if args.command == "ir-v3":
            ir = DslV3Parser().parse_ir(
                args.file.read_text(),
                requirement_id=args.requirement_id,
                title=args.title,
            )
            print(canonical_json(ir))
            return 0
        if args.command == "conclusion-definition":
            from .jsonutil import write_json

            artifact = build_default_conclusion_definition()
            if args.out:
                write_json(args.out, artifact)
                print(f"Conclusion definition: {args.out}")
            else:
                print(canonical_json(artifact), end="")
            return 0
        if args.command == "conclusion-gap-checklist":
            from .jsonutil import write_json

            checklist = build_default_gap_checklist()
            if args.out:
                write_json(args.out, checklist)
                print(f"Conclusion gap checklist: {args.out}")
            else:
                print(canonical_json(checklist), end="")
            return 0
        if args.command == "conclusion-gap-check":
            from .jsonutil import write_json

            checklist = ConclusionGapChecklist.model_validate_json(args.checklist.read_text())
            report = check_gap_checklist(checklist)
            if args.out:
                write_json(args.out, report)
                print(f"Conclusion gap check: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "threat-model":
            from .jsonutil import write_json

            report = build_default_threat_model()
            if args.out:
                write_json(args.out, report)
                print(f"Threat model report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "public-docs-index":
            from .jsonutil import write_json

            index = build_default_public_documentation_index(version=args.version)
            if args.out:
                write_json(args.out, index)
                print(f"Public docs index: {args.out}")
            else:
                print(canonical_json(index), end="")
            return 0
        if args.command == "public-docs-check":
            from .jsonutil import write_json

            index = PublicDocumentationIndex.model_validate_json(args.index.read_text())
            existing_paths = _existing_public_doc_paths(index, project_root=args.project_root)
            schema_root = args.schema_root
            if not schema_root.is_absolute():
                schema_root = args.project_root / schema_root
            existing_schemas = {
                path.name
                for path in schema_root.glob("*.schema.json")
                if path.is_file()
            }
            report = validate_public_documentation_index(
                index,
                existing_paths=existing_paths,
                existing_schemas=existing_schemas,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Public docs check: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "conclusion-certify":
            from .benchmark_reporting import BenchmarkEvaluationReport
            from .jsonutil import write_json
            from .reference_demo import ReferenceDemoReport
            from .threat_model import ThreatModelReport

            report = build_conclusion_certification_report(
                release_id=args.release_id,
                benchmark=BenchmarkEvaluationReport.model_validate_json(args.benchmark_report.read_text()),
                threat_model=ThreatModelReport.model_validate_json(args.threat_model.read_text()),
                demo=ReferenceDemoReport.model_validate_json(args.reference_demo_report.read_text()),
                docs=PublicDocumentationIndex.model_validate_json(args.docs_index.read_text()),
                schemas_frozen=args.schemas_frozen,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Conclusion certification report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "certified" else 1
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
        if args.command == "artifact-put":
            from .jsonutil import write_json

            record = put_artifact(
                store_root=args.store_root,
                source_path=args.file,
                logical_name=args.logical_name,
                media_type=args.media_type,
                raw=args.raw,
                normalized=args.normalized,
            )
            if args.out:
                write_json(args.out, record)
                print(f"Artifact record: {args.out}")
            else:
                print(canonical_json(record), end="")
            return 0
        if args.command == "artifact-get":
            from .jsonutil import write_json

            manifest = ArtifactStoreManifest.model_validate_json(args.manifest.read_text())
            result = lookup_artifact(
                store_root=args.store_root,
                manifest=manifest,
                artifact_hash=args.hash,
            )
            if args.out:
                write_json(args.out, result)
                print(f"Artifact lookup: {args.out}")
            else:
                print(canonical_json(result), end="")
            return 0 if result.status == "found" else 1
        if args.command == "sign-evidence":
            from .jsonutil import write_json

            envelope = sign_evidence_payload(
                payload=read_json(args.payload),
                producer_id=args.producer_id,
                key_id=args.key_id,
                secret=args.secret,
                envelope_id=args.envelope_id,
            )
            if args.out:
                write_json(args.out, envelope)
                print(f"Signed evidence envelope: {args.out}")
            else:
                print(canonical_json(envelope), end="")
            return 0
        if args.command == "verify-evidence":
            from .jsonutil import write_json

            report = verify_signed_evidence(
                envelope=SignedEvidenceEnvelope.model_validate_json(args.envelope.read_text()),
                registry=ProducerKeyRegistry.model_validate_json(args.registry.read_text()),
                secrets_by_key_id=_secrets_from_args(args.secret),
                require_high_assurance_trust=args.high_assurance,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Signature verification report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "valid" else 1
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
        if args.command == "intake-draft":
            from .jsonutil import write_json

            intake = create_free_form_intake(
                intake_id=args.intake_id,
                original_text=args.original.read_text(),
                submitted_by=args.submitted_by,
                submitted_at=args.submitted_at,
            )
            if args.method == "llm":
                from .llm_client import AnthropicLlmClient, RecordedLlmClient

                if args.fixture is not None:
                    client = RecordedLlmClient(args.fixture.read_text())
                    # Fixture replays don't speak to a real model; record the
                    # caller-supplied model name as-is (may be None).
                    effective_model = args.model
                else:
                    # Resolve the effective model before construction so the
                    # concrete model id is always recorded in provenance.
                    effective_model = args.model or "claude-haiku-4-5-20251001"
                    client = AnthropicLlmClient(model=effective_model)
                proposal = draft_controlled_rewrite_with_llm(
                    intake=intake,
                    client=client,
                    proposal_id=args.proposal_id,
                    timestamp=args.timestamp,
                    model=effective_model,
                )
            else:
                if args.suggested is None:
                    print(
                        "error: --suggested is required for --method manual (or rule_based)",
                        file=sys.stderr,
                    )
                    return 1
                proposal = create_controlled_rewrite_proposal(
                    intake=intake,
                    proposal_id=args.proposal_id,
                    proposed_controlled_text=args.suggested.read_text(),
                    timestamp=args.timestamp,
                    method=args.method,
                    model=args.model,
                    prompt=args.prompt,
                )
            if args.intake_out:
                write_json(args.intake_out, intake)
                print(f"Free-form intake: {args.intake_out}")
            write_json(args.out, proposal)
            print(f"Controlled rewrite proposal: {args.out}")
            return 0
        if args.command == "intake-approve":
            from .jsonutil import write_json

            proposal = ControlledRewriteProposal.model_validate_json(args.proposal.read_text())
            approval = approve_controlled_rewrite(
                proposal,
                approval_id=args.approval_id,
                approved_by=args.approved_by,
                approved_at=args.approved_at,
                decision=args.decision,
            )
            write_json(args.out, approval)
            print(f"Controlled rewrite approval: {args.out}")
            return 0
        if args.command == "intake-diff":
            proposal = ControlledRewriteProposal.model_validate_json(args.proposal.read_text())
            print(proposal.diff, end="")
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
        if args.command == "controlled-semantics":
            from .jsonutil import write_json

            reference = build_controlled_requirement_semantics_reference()
            if args.out:
                write_json(args.out, reference)
                print(f"Controlled semantics reference: {args.out}")
            else:
                print(canonical_json(reference), end="")
            return 0
        if args.command == "formal-claim":
            from .jsonutil import write_json
            from .models import RequirementIRV2

            ir = validate_requirement_ir_json(args.file.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("formal-claim requires ir_version 0.2")
            report = build_formal_claim(ir)
            if args.out:
                write_json(args.out, report)
                print(f"Formal claim report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "lowered" else 1
        if args.command == "formal-claim-semantics":
            from .jsonutil import write_json

            reference = build_formal_claim_semantics_completion_reference()
            if args.out:
                write_json(args.out, reference)
                print(f"Formal claim semantics reference: {args.out}")
            else:
                print(canonical_json(reference), end="")
            return 0 if reference.result == "complete" else 1
        if args.command == "semantic-translate":
            from .jsonutil import write_json

            decomposition_clients = None
            if args.ensemble_clients:
                from .decomposition_client import (
                    AnthropicDecompositionClient,
                    RecordedDecompositionClient,
                )
                from .models import RequirementIRV2

                decomposition_clients = []
                for spec in args.ensemble_clients:
                    if spec == "live":
                        decomposition_clients.append(AnthropicDecompositionClient())
                    elif spec.startswith("live:"):
                        model_id = spec.removeprefix("live:")
                        decomposition_clients.append(AnthropicDecompositionClient(model=model_id))
                    elif spec.startswith("recorded:"):
                        fixture_path = Path(spec.removeprefix("recorded:"))
                        fixture_ir = RequirementIRV2.model_validate_json(fixture_path.read_text())
                        decomposition_clients.append(RecordedDecompositionClient(fixture=fixture_ir))
                    else:
                        print(
                            f"nlreq: unknown --ensemble-client spec {spec!r}. "
                            "Use 'live', 'live:<model-id>', or 'recorded:<fixture-path>'.",
                            file=sys.stderr,
                        )
                        return 2

            report = translate_controlled_requirement_to_formal_claim(
                controlled_text=args.file.read_text(),
                requirement_id=args.requirement_id,
                title=args.title,
                translation_id=args.translation_id,
                decomposition_clients=decomposition_clients,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Semantic translation report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "accepted" else 1
        if args.command == "semantic-agreement":
            from .jsonutil import write_json

            reports = [
                FormalClaimLoweringReport.model_validate_json(path.read_text())
                for path in args.formal_claim_report
            ]
            candidates = [
                FormalClaimAgreementCandidate(
                    candidate_id=args.candidate_id[index]
                    if index < len(args.candidate_id)
                    else f"candidate-{index + 1}",
                    translator_id=args.translator_id[index]
                    if index < len(args.translator_id)
                    else f"translator-{index + 1}",
                    report=report,
                )
                for index, report in enumerate(reports)
            ]
            resolution = None
            if args.resolution_candidate_id is not None:
                if args.approved_by is None or args.approved_at is None:
                    raise ValueError("semantic-agreement resolution requires --approved-by and --approved-at")
                resolution = SemanticAgreementResolution(
                    selected_candidate_id=args.resolution_candidate_id,
                    selected_candidate_hash=args.resolution_candidate_hash,
                    reason=args.resolution_reason or "reviewer selected semantic candidate",
                    approval=Approval(
                        status="approved",
                        approved_by=args.approved_by,
                        approved_at=args.approved_at,
                    ),
                )
            report = build_semantic_agreement_report(candidates, resolution=resolution)
            if args.out:
                write_json(args.out, report)
                print(f"Semantic agreement report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.acceptance_allowed else 1
        if args.command == "translation-repair":
            from .jsonutil import write_json

            report = build_translation_repair_report(
                translation=SemanticTranslationReport.model_validate_json(args.translation_report.read_text())
                if args.translation_report
                else None,
                agreement=SemanticAgreementReport.model_validate_json(args.agreement_report.read_text())
                if args.agreement_report
                else None,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Translation repair report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "tla-projection":
            from .jsonutil import write_json
            from .models import RequirementIRV2

            ir = validate_requirement_ir_json(args.file.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("tla-projection requires ir_version 0.2")
            report = build_tla_projection_report(ir)
            if args.out:
                write_json(args.out, report)
                print(f"TLA projection report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "projected" else 1
        if args.command == "translator-agreement":
            from .jsonutil import write_json

            report = build_translation_agreement_report(
                TranslationAgreementInput.model_validate_json(args.input.read_text())
            )
            if args.out:
                write_json(args.out, report)
                print(f"Translator agreement report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "logical-translator-agreement":
            from .jsonutil import write_json

            agreement_input = TranslationAgreementInput.model_validate_json(args.input.read_text())
            report = build_logical_translation_agreement_report(agreement_input.candidates)
            if args.out:
                write_json(args.out, report)
                print(f"Logical translator agreement report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "translate-candidates":
            from .jsonutil import write_json

            run = build_multi_pass_translator_run(
                run_id=args.run_id,
                controlled_text=args.file.read_text(),
                requirement_id=args.requirement_id,
                title=args.title,
            )
            write_json(args.out, run)
            print(f"Translator run: {args.out}")
            return 0
        if args.command == "translate-compare":
            from .jsonutil import write_json

            run = TranslatorRunArtifact.model_validate_json(args.run.read_text())
            report = compare_translator_run(run)
            if args.out:
                write_json(args.out, report)
                print(f"Translator comparison report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "translate-select":
            from .jsonutil import write_json

            run = TranslatorRunArtifact.model_validate_json(args.run.read_text())
            updated, selection = select_translator_candidate(
                run,
                candidate_id=args.candidate_id,
                approved_by=args.approved_by,
                approved_at=args.approved_at,
            )
            if args.run_out:
                write_json(args.run_out, updated)
                print(f"Updated translator run: {args.run_out}")
            write_json(args.out, selection)
            print(f"Translator selection: {args.out}")
            return 0
        if args.command == "provenance-graph":
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .translator import LoweredFormalArtifact

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("provenance-graph requires ir_version 0.2")
            graph = build_provenance_graph(
                ir,
                lowered=LoweredFormalArtifact.model_validate_json(args.lowered.read_text())
                if args.lowered
                else None,
            )
            if args.out:
                write_json(args.out, graph)
                print(f"Provenance graph: {args.out}")
            else:
                print(canonical_json(graph), end="")
            return 0
        if args.command == "clarify":
            from .jsonutil import write_json

            raw_agreement = read_json(args.agreement)
            if "candidates" in raw_agreement:
                agreement = build_translation_agreement_report(
                    TranslationAgreementInput.model_validate(raw_agreement)
                )
            else:
                agreement = TranslationAgreementReport.model_validate(raw_agreement)
            requests = clarification_requests_from_agreement(agreement)
            if args.out:
                write_json(args.out, requests)
                print(f"Clarification requests: {args.out}")
            else:
                print(canonical_json(requests), end="")
            return 0
        if args.command == "apply-clarification":
            from .jsonutil import write_json

            response = ClarificationResponse.model_validate_json(args.response.read_text())
            artifact = apply_clarification_response(args.controlled.read_text(), response)
            write_json(args.out, artifact)
            print(f"Clarified controlled text: {args.out}")
            return 0
        if args.command == "review-open":
            from .jsonutil import write_json

            workflow = open_review(
                review_id=args.review_id,
                requirement_id=args.requirement_id,
                artifact_refs=_artifact_refs_from_args(args.artifact),
            )
            write_json(args.out, workflow)
            print(f"Review workflow: {args.out}")
            return 0
        if args.command == "review-approve":
            from .jsonutil import write_json

            workflow = ApprovalWorkflowArtifact.model_validate_json(args.workflow.read_text())
            updated = approve_review(
                workflow,
                role=args.role,
                reviewer=args.reviewer,
                decision=args.decision,
                approved_at=args.approved_at,
                current_artifact_refs=_artifact_refs_from_args(args.artifact)
                if args.artifact
                else None,
                checklist=ReviewChecklist.model_validate_json(args.checklist.read_text())
                if args.checklist
                else None,
                self_audit=args.self_audit,
                self_audit_delay_hours=args.self_audit_delay_hours,
            )
            write_json(args.out, updated)
            print(f"Review workflow: {args.out}")
            return 0
        if args.command == "review-status":
            from .jsonutil import write_json

            workflow = ApprovalWorkflowArtifact.model_validate_json(args.workflow.read_text())
            report = review_status(
                workflow,
                current_artifact_refs=_artifact_refs_from_args(args.artifact)
                if args.artifact
                else None,
                required_roles=args.required_role or None,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Review status: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "refusal-render":
            from .jsonutil import write_json
            from .end_to_end_gate import EndToEndRequirementGateReport

            gate_report = EndToEndRequirementGateReport.model_validate_json(
                args.gate_report.read_text()
            )
            report = build_refusal_report_from_gate(gate_report)
            if args.out:
                write_json(args.out, report)
                print(f"Refusal report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.markdown_out:
                args.markdown_out.write_text(refusal_report_markdown(report))
                print(f"Refusal markdown: {args.markdown_out}")
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
        if args.command == "python-source-impact-context":
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact

            adapter = PythonSourceLanguageAdapter(project_root=args.project_root)
            manifest = adapter.parse_manifest(args.manifest)
            traces = (
                NormalizedTraceArtifact.model_validate_json(args.trace_artifact.read_text())
                if args.trace_artifact
                else None
            )
            artifact = analyze_source_impact_with_context(
                adapter,
                manifest,
                symbols=args.symbol,
                traces=traces,
                semantic_suggestions=_semantic_suggestions_from_args(
                    args.semantic_suggestion
                ),
            )
            if args.out:
                write_json(args.out, artifact)
                print(f"Python contextual source impact: {args.out}")
            else:
                print(canonical_json(artifact), end="")
            return 0
        if args.command == "python-source-impact-production":
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact

            adapter = PythonSourceLanguageAdapter(project_root=args.project_root)
            manifest = adapter.parse_manifest(args.manifest)
            traces = (
                NormalizedTraceArtifact.model_validate_json(args.trace_artifact.read_text())
                if args.trace_artifact
                else None
            )
            report = analyze_production_source_impact(
                adapter,
                manifest,
                symbols=args.symbol,
                traces=traces,
                semantic_suggestions=_semantic_suggestions_from_args(
                    args.semantic_suggestion
                ),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Production source impact report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.closure_effect != "block" else 1
        if args.command == "javascript-source-impact":
            from .jsonutil import write_json

            adapter = JavaScriptSourceLanguageAdapter(project_root=args.project_root)
            manifest = adapter.parse_manifest(args.manifest)
            artifact = analyze_source_impact(adapter, manifest, symbols=args.symbol)
            if args.out:
                write_json(args.out, artifact)
                print(f"JavaScript source impact: {args.out}")
            else:
                print(canonical_json(artifact), end="")
            return 0
        if args.command == "javascript-source-impact-context":
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact

            adapter = JavaScriptSourceLanguageAdapter(project_root=args.project_root)
            manifest = adapter.parse_manifest(args.manifest)
            traces = (
                NormalizedTraceArtifact.model_validate_json(args.trace_artifact.read_text())
                if args.trace_artifact
                else None
            )
            artifact = analyze_source_impact_with_context(
                adapter,
                manifest,
                symbols=args.symbol,
                traces=traces,
                semantic_suggestions=_semantic_suggestions_from_args(
                    args.semantic_suggestion
                ),
            )
            if args.out:
                write_json(args.out, artifact)
                print(f"JavaScript contextual source impact: {args.out}")
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
        if args.command == "s-and-r-composition":
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .system_checker import SystemConsistencyResult
            from .translator import LoweredFormalArtifact

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("s-and-r-composition requires ir_version 0.2")
            report = build_s_and_r_composition_report(
                requirement=ir,
                lowered=LoweredFormalArtifact.model_validate_json(args.lowered.read_text()),
                registry=load_system_spec_registry(args.registry),
                impact=ImpactAnalysisArtifact.model_validate_json(args.impact.read_text()),
                project_root=args.project_root,
                consistency=SystemConsistencyResult.model_validate_json(
                    args.system_consistency.read_text()
                ),
            )
            if args.out:
                write_json(args.out, report)
                print(f"S-and-R composition report: {args.out}")
            else:
                print(canonical_json(report), end="")
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
        if args.command == "coverage-manifest-v2-migrate":
            from .jsonutil import write_json

            manifest = migrate_code_spec_manifest_to_v2(
                CodeSpecManifest.model_validate_json(args.manifest.read_text()),
                registry=load_system_spec_registry(args.registry),
            )
            if args.out:
                write_json(args.out, manifest)
                print(f"Coverage manifest v2: {args.out}")
            else:
                print(canonical_json(manifest), end="")
            return 0
        if args.command == "coverage-gate-v2":
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json
            from .source_impact import ProductionSourceImpactReport

            try:
                impact = ProductionSourceImpactReport.model_validate_json(
                    args.impact.read_text()
                )
            except ValueError:
                impact = ImpactAnalysisArtifact.model_validate_json(args.impact.read_text())
            report = build_code_spec_coverage_gate_report_v2(
                impact=impact,
                manifest=CodeSpecCoverageManifestV2.model_validate_json(
                    args.manifest.read_text()
                ),
                threshold=args.threshold,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Coverage gate v2 report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
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
        if args.command == "trace-replay":
            from .coverage_alignment import SpecCoverageReport
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact, RequirementIRV2

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("trace-replay requires ir_version 0.2")
            report = build_trace_replay_report(
                requirement=ir,
                traces=NormalizedTraceArtifact.model_validate_json(args.trace_artifact.read_text()),
                coverage=SpecCoverageReport.model_validate_json(args.coverage.read_text()),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Trace replay report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "spec-extract":
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .source_adapter import CodePresentation
            from .trace_replay import TraceReplayReport

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("spec-extract requires ir_version 0.2")
            report = build_spec_extraction_workbench_report(
                requirement=ir,
                impact=ImpactAnalysisArtifact.model_validate_json(args.impact.read_text()),
                registry=load_system_spec_registry(args.registry),
                project_root=args.project_root,
                code_presentation=CodePresentation.model_validate_json(
                    args.code_presentation.read_text()
                )
                if args.code_presentation
                else None,
                trace_replay=TraceReplayReport.model_validate_json(args.trace_replay.read_text())
                if args.trace_replay
                else None,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Spec extraction workbench report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "specula-extract":
            from .impact import ImpactAnalysisArtifact
            from .jsonutil import write_json
            from .models import RequirementIRV2
            from .source_adapter import CodePresentation
            from .trace_replay import TraceReplayReport

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("specula-extract requires ir_version 0.2")
            report = build_specula_extraction_integration_report(
                requirement=ir,
                impact=ImpactAnalysisArtifact.model_validate_json(args.impact.read_text()),
                registry=load_system_spec_registry(args.registry),
                project_root=args.project_root,
                code_presentation=CodePresentation.model_validate_json(
                    args.code_presentation.read_text()
                )
                if args.code_presentation
                else None,
                trace_replay=TraceReplayReport.model_validate_json(args.trace_replay.read_text())
                if args.trace_replay
                else None,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Specula extraction integration report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result != "blocked" else 1
        if args.command == "candidate-spec-review":
            from .jsonutil import write_json

            candidate = CandidateSpec.model_validate_json(args.candidate.read_text())
            checklist = _candidate_review_checklist_from_args(args.checklist)
            if args.decision == "promote":
                if not args.approved_hash:
                    raise ValueError("candidate-spec-review promote requires --approved-hash")
                report = promote_candidate_spec_with_review(
                    candidate,
                    approved_hash=args.approved_hash,
                    version=args.version,
                    reviewer_id=args.reviewer_id,
                    reviewed_at=args.reviewed_at,
                    checklist=checklist,
                )
            else:
                report = reject_candidate_spec(
                    candidate,
                    reviewer_id=args.reviewer_id,
                    reviewed_at=args.reviewed_at,
                    rejection_reasons=args.rejection_reason,
                    checklist=checklist,
                )
            if args.out:
                write_json(args.out, report)
                print(f"Candidate spec review report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.decision != "blocked" else 1
        if args.command == "spec-drift":
            from .jsonutil import write_json

            report = build_spec_drift_report(
                CodeSpecManifest.model_validate_json(args.manifest.read_text()),
                project_root=args.project_root,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Spec drift report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.updated_registry_out:
                if args.registry is None:
                    raise ValueError("spec-drift requires --registry with --updated-registry-out")
                updated = mark_stale_specs(load_system_spec_registry(args.registry), report)
                write_json(args.updated_registry_out, updated)
                print(f"Updated system spec registry: {args.updated_registry_out}")
            return 0
        if args.command == "spec-freshness-lock":
            from .jsonutil import write_json

            lockfile = build_spec_freshness_lockfile(
                manifest=CodeSpecManifest.model_validate_json(args.manifest.read_text()),
                registry=load_system_spec_registry(args.registry),
                project_root=args.project_root,
                lock_id=args.lock_id,
            )
            if args.out:
                write_json(args.out, lockfile)
                print(f"Spec freshness lockfile: {args.out}")
            else:
                print(canonical_json(lockfile), end="")
            return 0
        if args.command == "spec-freshness-lock-v2":
            from .jsonutil import write_json

            lockfile = build_spec_freshness_lockfile_v2(
                manifest=CodeSpecManifest.model_validate_json(args.manifest.read_text()),
                registry=load_system_spec_registry(args.registry),
                project_root=args.project_root,
                lock_id=args.lock_id,
                validated_at=args.validated_at,
            )
            if args.out:
                write_json(args.out, lockfile)
                print(f"Spec freshness lockfile v2: {args.out}")
            else:
                print(canonical_json(lockfile), end="")
            return 0
        if args.command == "spec-freshness-check":
            from .jsonutil import write_json

            report = validate_spec_freshness_lockfile(
                manifest=CodeSpecManifest.model_validate_json(args.manifest.read_text()),
                registry=load_system_spec_registry(args.registry),
                lockfile=SpecFreshnessLockfile.model_validate_json(args.lockfile.read_text()),
                project_root=args.project_root,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Spec freshness report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "spec-freshness-ci":
            from .jsonutil import write_json

            report = build_spec_drift_ci_report(
                manifest=CodeSpecManifest.model_validate_json(args.manifest.read_text()),
                registry=load_system_spec_registry(args.registry),
                lockfile=SpecFreshnessLockfileV2.model_validate_json(
                    args.lockfile.read_text()
                ),
                project_root=args.project_root,
                now=args.now,
                max_validation_age_hours=args.max_validation_age_hours,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Spec freshness CI report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "delta-extract":
            from .coverage_alignment import SpecCoverageReport
            from .jsonutil import write_json
            from .requirement_self_consistency import RequirementSelfConsistencyResult
            from .spec_drift import SpecDriftReport
            from .system_checker import SystemConsistencyResult
            from .trace_replay import TraceReplayReport

            report = build_delta_report(
                self_consistency=RequirementSelfConsistencyResult.model_validate_json(
                    args.self_consistency.read_text()
                )
                if args.self_consistency
                else None,
                system_consistency=SystemConsistencyResult.model_validate_json(
                    args.system_consistency.read_text()
                )
                if args.system_consistency
                else None,
                spec_coverage=SpecCoverageReport.model_validate_json(
                    args.spec_coverage.read_text()
                )
                if args.spec_coverage
                else None,
                trace_replay=TraceReplayReport.model_validate_json(
                    args.trace_replay.read_text()
                )
                if args.trace_replay
                else None,
                spec_drift=SpecDriftReport.model_validate_json(args.spec_drift.read_text())
                if args.spec_drift
                else None,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Delta report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.markdown_out:
                args.markdown_out.write_text(delta_report_markdown(report))
                print(f"Delta markdown: {args.markdown_out}")
            return 0
        if args.command == "verification-budget":
            from .jsonutil import write_json
            from .models import RequirementIRV2

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("verification-budget requires ir_version 0.2")
            report = build_verification_budget_report(
                ir,
                requirement_class=args.requirement_class,
                assumptions=_assumptions_from_args(args.assumption),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Verification budget report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "evidence-producers-validate":
            from .jsonutil import write_json
            from .models import BackendResult
            from .proof_closure import EvidenceProducerMapping

            mapping = (
                EvidenceProducerMapping.model_validate_json(args.producer_mapping.read_text())
                if args.producer_mapping
                else default_evidence_producer_mapping()
            )
            report = validate_real_evidence_producers(
                [
                    BackendResult.model_validate_json(path.read_text())
                    for path in args.backend_result
                ],
                mapping,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Evidence producer validation report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "proof-evidence-boundary":
            from .jsonutil import write_json
            from .proof_closure import ProofObject

            report = build_proof_evidence_boundary_report(
                ProofObject.model_validate_json(args.proof_object.read_text())
            )
            if args.out:
                write_json(args.out, report)
                print(f"Proof evidence boundary report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "proof-backend-boundary":
            from .jsonutil import write_json
            from .models import BackendResult
            from .proof_closure import EvidenceProducerMapping

            mapping = (
                EvidenceProducerMapping.model_validate_json(args.producer_mapping.read_text())
                if args.producer_mapping
                else default_evidence_producer_mapping()
            )
            report = build_proof_producing_backend_boundary_report(
                backend_result=BackendResult.model_validate_json(args.backend_result.read_text()),
                producer_mapping=mapping,
                proof_artifacts=_proof_artifacts_from_args(args.proof_artifact),
                checker_command=_normalize_remainder_command(args.checker_command)
                if args.checker_command
                else None,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Proof backend boundary report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "accepted" else 1
        if args.command == "backend-agreement":
            from .formal_backend import FormalBackendResponse
            from .jsonutil import write_json
            from .models import BackendResult

            backend_results = [
                BackendResult.model_validate_json(path.read_text())
                for path in args.backend_result
            ]
            for path in args.formal_backend_response:
                response = FormalBackendResponse.model_validate_json(path.read_text())
                details = dict(response.result.details)
                details.setdefault("formal_target", response.target)
                backend_results.append(response.result.model_copy(update={"details": details}))
            report = build_backend_agreement_report(
                backend_results,
                policy=args.policy,
                overlap_key=args.overlap_key,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Backend agreement report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "counterexample-normalize":
            from .formal_backend import FormalBackendResponse
            from .jsonutil import write_json

            report = normalize_backend_counterexamples(
                [
                    FormalBackendResponse.model_validate_json(path.read_text())
                    for path in args.formal_backend_response
                ]
            )
            if args.out:
                write_json(args.out, report)
                print(f"Counterexample normalization report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "counterexample-explain":
            from .counterexample_normalization import CounterexampleNormalizationReport
            from .formal_backend import FormalBackendResponse
            from .formal_claim import FormalClaim
            from .jsonutil import write_json

            report = explain_counterexamples(
                CounterexampleNormalizationReport.model_validate_json(
                    args.normalization.read_text()
                ),
                formal_claim=FormalClaim.model_validate_json(args.formal_claim.read_text())
                if args.formal_claim
                else None,
                backend_responses=[
                    FormalBackendResponse.model_validate_json(path.read_text())
                    for path in args.formal_backend_response
                ],
            )
            if args.out:
                write_json(args.out, report)
                print(f"Counterexample explanation report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.markdown_out:
                args.markdown_out.write_text(
                    "\n\n".join(item.markdown for item in report.explanations)
                )
                print(f"Counterexample explanation markdown: {args.markdown_out}")
            return 0
        if args.command == "proof-object":
            from .coverage_alignment import SpecCoverageReport, TraceAlignmentReport
            from .backend_agreement import BackendAgreementReport
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
                backend_agreement=(
                    BackendAgreementReport.model_validate_json(args.backend_agreement.read_text())
                    if args.backend_agreement
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
        if args.command == "cross-language-proof":
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact
            from .proof_closure import ProofObject
            from .source_adapter import SourceManifest

            report = build_cross_language_proof_object(
                proof=ProofObject.model_validate_json(args.proof_object.read_text()),
                manifests=[
                    SourceManifest.model_validate_json(path.read_text())
                    for path in args.source_manifest
                ],
                traces=[
                    NormalizedTraceArtifact.model_validate_json(path.read_text())
                    for path in args.trace_artifact
                ],
                causal_links=_causal_links_from_args(args.causal_link),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Cross-language proof object: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.fail_on_blocking and report.result == "blocked":
                return 1
            return 0
        if args.command == "requirement-gate":
            from .jsonutil import write_json

            if args.source_language == "python":
                source_adapter = PythonSourceLanguageAdapter(project_root=args.project_root)
            elif args.source_language == "javascript":
                source_adapter = JavaScriptSourceLanguageAdapter(project_root=args.project_root)
            else:  # pragma: no cover - argparse constrains choices
                raise ValueError(f"unsupported source language: {args.source_language}")
            checker_command = (
                _normalize_remainder_command(args.checker_command)
                if args.checker_command
                else None
            )
            execution = _requirement_gate_execution_from_args(args, checker_command)
            report = run_end_to_end_requirement_gate(
                controlled_text=args.file.read_text(),
                requirement_id=args.requirement_id,
                title=args.title,
                source_adapter=source_adapter,
                source_manifest=source_adapter.parse_manifest(args.source_manifest),
                symbols=args.symbol,
                registry=load_system_spec_registry(args.registry),
                project_root=args.project_root,
                artifact_dir=args.artifact_dir,
                downstream_action=args.downstream_action,
                self_check_backend=args.self_check_backend,
                budget=_formal_backend_budget_from_args(args),
                execution=execution,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Requirement gate report: {args.out}")
            else:
                print(canonical_json(report), end="")
            if args.markdown_out:
                refusal = build_refusal_report_from_gate(report)
                args.markdown_out.write_text(refusal_report_markdown(refusal))
                print(f"Requirement gate markdown: {args.markdown_out}")
            if args.fail_on_refusal and report.decision != "accepted":
                return 1
            return 0
        if args.command == "benchmark-corpus":
            from .benchmark_corpus import BenchmarkCorpus, BenchmarkResultsArtifact
            from .jsonutil import write_json

            report = build_benchmark_run_report(
                BenchmarkCorpus.model_validate_json(args.corpus.read_text()),
                BenchmarkResultsArtifact.model_validate_json(args.results.read_text()).root,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Benchmark corpus report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "benchmark-evaluate":
            from .benchmark_corpus import BenchmarkCorpus, BenchmarkResultsArtifact
            from .jsonutil import write_json

            report = build_benchmark_evaluation_report(
                BenchmarkCorpus.model_validate_json(args.corpus.read_text()),
                BenchmarkResultsArtifact.model_validate_json(args.results.read_text()).root,
                false_closure_budget=args.false_closure_budget,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Benchmark evaluation report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "benchmark-extended":
            from .jsonutil import write_json

            report = build_extended_benchmark_evaluation_report(
                BenchmarkEvaluationReport.model_validate_json(args.base_report.read_text()),
                [_dimension_result_from_arg(value) for value in args.dimension],
                release_thresholds=_key_float_map_from_args(args.threshold),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Extended benchmark evaluation report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "benchmark-translation":
            from .jsonutil import write_json

            report = build_translation_benchmark_report(
                RequirementTranslationCorpus.model_validate_json(args.corpus.read_text()),
                RequirementTranslationResults.model_validate_json(args.results.read_text()),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Requirement translation benchmark report: {args.out}")
            else:
                print(canonical_json(report), end="")
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
        if args.command == "waiver-audit":
            from .jsonutil import write_json

            report = build_waiver_audit_report(
                policy=load_gate_policy(args.policy),
                waivers=load_gate_waivers(args.waiver),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Waiver audit report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
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
        if args.command == "trace-validation-gate":
            from .coverage_alignment import SpecCoverageReport
            from .jsonutil import write_json
            from .models import NormalizedTraceArtifact, RequirementIRV2
            from .spec_freshness import SpecFreshnessDriftCiReport

            ir = validate_requirement_ir_json(args.requirement_ir.read_text())
            if not isinstance(ir, RequirementIRV2):
                raise ValueError("trace-validation-gate requires ir_version 0.2")
            freshness = (
                SpecFreshnessDriftCiReport.model_validate_json(args.freshness.read_text())
                if args.freshness
                else None
            )
            report = build_trace_validation_gate_report(
                requirement=ir,
                traces=NormalizedTraceArtifact.model_validate_json(args.trace_artifact.read_text()),
                coverage=SpecCoverageReport.model_validate_json(args.coverage.read_text()),
                freshness=freshness,
                high_assurance=not args.allow_lossy,
            )
            wrote_output = False
            if args.out:
                write_json(args.out, report)
                print(f"Trace validation gate report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(trace_validation_gate_markdown(report))
                print(f"Trace validation gate markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0 if report.result == "satisfied" else 1
        if args.command == "trace-normalize":
            from .jsonutil import write_json

            report = normalize_raw_traces(
                RawTraceArtifact.model_validate_json(args.raw.read_text())
            )
            if args.out:
                write_json(args.out, report)
                print(f"Trace normalization report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0
        if args.command == "trace-extract":
            from .jsonutil import write_json

            registry = TraceProducerRegistry.model_validate_json(args.registry.read_text())
            producer = producer_from_registry(registry, args.producer_id)
            report = producer.extract(
                TraceExtractionRequest(
                    producer_id=args.producer_id,
                    trace_source=args.trace_source,
                    requirement_ids=args.requirement_id,
                    run_id=args.run_id,
                ),
                project_root=args.project_root,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Trace extraction result: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.status == "extracted" else 1
        if args.command == "trace-producer-evidence":
            from .jsonutil import write_json
            from .runtime_trace_sdk import TraceExtractionResult

            registry = TraceProducerRegistry.model_validate_json(args.registry.read_text())
            registration = next(
                (
                    producer
                    for producer in registry.producers
                    if producer.producer_id == args.producer_id
                ),
                None,
            )
            if registration is None:
                raise ValueError(f"unknown trace producer: {args.producer_id}")
            report = build_trace_producer_evidence_report(
                registration=registration,
                result=TraceExtractionResult.model_validate_json(
                    args.extraction_result.read_text()
                ),
                high_assurance=args.high_assurance,
                require_signature=args.require_signature,
                require_replay=not args.allow_missing_replay,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Trace producer evidence report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "accepted" else 1
        if args.command == "adapter-certify":
            from .jsonutil import write_json

            adapter = production_adapter_for_language(args.language, project_root=args.project_root)
            manifest = adapter.parse_manifest(args.manifest)
            report = certify_adapter(
                adapter,
                manifest,
                symbol_refs=[SymbolRef(name=symbol) for symbol in args.symbol],
                required_capabilities=args.required_capability,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Adapter certification report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "certified" else 1
        if args.command == "adapter-capabilities":
            from .jsonutil import write_json

            adapter = production_adapter_for_language(args.language, project_root=args.project_root)
            contract = adapter.capability_contract()
            if args.out:
                write_json(args.out, contract)
                print(f"Adapter capability contract: {args.out}")
            else:
                print(canonical_json(contract), end="")
            return 0
        if args.command == "adapter-plugin-validate":
            from .jsonutil import write_json

            report = validate_adapter_plugin_manifest(
                AdapterPluginManifest.model_validate_json(args.plugin_manifest.read_text()),
                AdapterCertificationReport.model_validate_json(
                    args.certification_report.read_text()
                ),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Adapter plugin validation report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "accepted" else 1
        if args.command == "ci-pr-gate":
            from .end_to_end_gate import EndToEndRequirementGateReport
            from .jsonutil import write_json

            report = build_ci_pr_gate_report(
                EndToEndRequirementGateReport.model_validate_json(args.gate_report.read_text()),
                mode=args.mode,
            )
            wrote_output = False
            if args.out:
                write_json(args.out, report)
                print(f"CI/PR gate report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(ci_pr_gate_markdown(report))
                print(f"CI/PR gate markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0 if report.result != "blocked" else 1
        if args.command == "requirement-gate-extended":
            from .jsonutil import write_json

            report = build_extended_requirement_gate_report(
                EndToEndRequirementGateReport.model_validate_json(args.gate_report.read_text()),
                stage_statuses=_key_value_map_from_args(args.stage_status),
                artifact_hashes=_key_value_map_from_args(args.artifact_hash),
                artifact_paths=_key_value_map_from_args(args.artifact_path),
                evidence_levels=_key_value_map_from_args(args.evidence_level),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Extended requirement gate report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.downstream_action_allowed else 1
        if args.command == "ci-adoption":
            from .jsonutil import write_json

            report = build_ci_adoption_report(
                ExtendedEndToEndRequirementGateReport.model_validate_json(
                    args.extended_gate_report.read_text()
                ),
                mode=args.mode,
                waiver_ids=args.waiver_id,
            )
            wrote_output = False
            if args.out:
                write_json(args.out, report)
                print(f"CI adoption report: {args.out}")
                wrote_output = True
            if args.markdown_out:
                args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
                args.markdown_out.write_text(extended_ci_pr_gate_markdown(report))
                print(f"CI adoption markdown: {args.markdown_out}")
                wrote_output = True
            if not wrote_output:
                print(canonical_json(report), end="")
            return 0 if report.result != "blocked" else 1
        if args.command == "reference-demo-extended":
            from .jsonutil import write_json

            report = build_extended_reference_demo_report(
                ReferenceDemoManifest.model_validate_json(args.manifest.read_text()),
                ReferenceDemoReport.model_validate_json(args.base_report.read_text()),
                gate_reports=[
                    ExtendedEndToEndRequirementGateReport.model_validate_json(path.read_text())
                    for path in args.gate_report
                ],
                replay_bundle_hashes=_key_value_map_from_args(args.replay_bundle_hash),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Extended reference demo report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "reproducible" else 1
        if args.command == "public-docs-freeze":
            from .jsonutil import write_json

            report = build_public_documentation_freeze_report(
                PublicDocumentationIndex.model_validate_json(args.index.read_text()),
                PublicDocumentationCoverageReport.model_validate_json(
                    args.coverage_report.read_text()
                ),
                frozen_schema_hashes=_key_value_map_from_args(args.schema_hash),
                covered_topics=args.topic,
                compatibility_commitments=args.commitment,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Public docs freeze report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "passed" else 1
        if args.command == "tcb-review":
            from .jsonutil import write_json

            report = build_extended_tcb_review_report(
                ThreatModelReport.model_validate_json(args.threat_model.read_text()),
                release_artifact_hashes=_key_value_map_from_args(args.release_artifact_hash),
                accepted_residual_risks=args.accepted_residual_risk,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Extended TCB review report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "complete" else 1
        if args.command == "extended-conclusion-certify":
            from .jsonutil import write_json

            report = build_extended_conclusion_certification_report(
                release_id=args.release_id,
                gate=ExtendedEndToEndRequirementGateReport.model_validate_json(
                    args.gate_report.read_text()
                ),
                ci=ExtendedCiPrGateReport.model_validate_json(args.ci_report.read_text()),
                benchmark=ExtendedBenchmarkEvaluationReport.model_validate_json(
                    args.benchmark_report.read_text()
                ),
                demo=ExtendedReferenceDemoReport.model_validate_json(
                    args.reference_demo_report.read_text()
                ),
                docs=PublicDocumentationFreezeReport.model_validate_json(
                    args.docs_freeze_report.read_text()
                ),
                tcb_review=ExtendedTcbReviewReport.model_validate_json(
                    args.tcb_review_report.read_text()
                ),
                schemas_frozen=args.schemas_frozen,
                producer_evidence_present=args.producer_evidence_present,
                release_bundle_hash=args.release_bundle_hash,
                signed_release_bundle_hash=args.signed_release_bundle_hash,
                require_signed_release_bundle=not args.allow_unsigned_release_bundle,
            )
            if args.out:
                write_json(args.out, report)
                print(f"Extended conclusion certification report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "certified" else 1
        if args.command == "reference-demo-check":
            from .jsonutil import write_json

            manifest = ReferenceDemoManifest.model_validate_json(args.manifest.read_text())
            report = build_reference_demo_report(
                manifest,
                existing_paths=_existing_demo_paths(manifest, project_root=args.project_root),
                actual_decisions_by_requirement=_reference_demo_actual_decisions(
                    manifest,
                    project_root=args.project_root,
                ),
            )
            if args.out:
                write_json(args.out, report)
                print(f"Reference demo report: {args.out}")
            else:
                print(canonical_json(report), end="")
            return 0 if report.result == "reproducible" else 1
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


def _requirement_gate_execution_from_args(
    args: argparse.Namespace, checker_command: list[str] | None
) -> FormalBackendExecution | None:
    if not any(
        [
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
        artifact_dir=(args.artifact_dir / "formal-self-check").as_posix(),
        expected_exit_code=args.expected_exit_code,
        tool_version=args.tool_version,
        tool_version_command=args.tool_version_command,
        output_limit_bytes=args.output_limit_bytes,
    )


def _semantic_suggestions_from_args(entries: list[str]) -> list[SemanticImpactSuggestion]:
    suggestions: list[SemanticImpactSuggestion] = []
    for entry in entries:
        parts = entry.split(":", 2)
        if len(parts) == 1:
            suggestions.append(
                SemanticImpactSuggestion(module_id=parts[0], reason="CLI suggestion")
            )
        elif len(parts) == 2:
            suggestions.append(
                SemanticImpactSuggestion(module_id=parts[0], reason=parts[1])
            )
        else:
            source = parts[2]
            if source not in {"llm", "manual", "heuristic"}:
                raise ValueError(f"unsupported semantic suggestion source: {source}")
            suggestions.append(
                SemanticImpactSuggestion(
                    module_id=parts[0],
                    reason=parts[1],
                    source=source,  # type: ignore[arg-type]
                )
            )
    return suggestions


def _candidate_review_checklist_from_args(
    entries: list[str],
) -> list[CandidateSpecReviewChecklistItem] | None:
    if not entries:
        return None
    checklist: list[CandidateSpecReviewChecklistItem] = []
    for entry in entries:
        if "=" not in entry:
            raise ValueError("--checklist values must use item_id=approved|rejected[:notes]")
        item_id, payload = entry.split("=", 1)
        status_text, _, notes = payload.partition(":")
        if status_text not in {"approved", "rejected"}:
            raise ValueError("checklist status must be approved or rejected")
        checklist.append(
            CandidateSpecReviewChecklistItem(
                item_id=item_id,
                status=status_text,  # type: ignore[arg-type]
                notes=notes or None,
            )
        )
    return checklist


def _assumptions_from_args(entries: list[str]) -> list[AbstractionAssumption]:
    assumptions: list[AbstractionAssumption] = []
    for entry in entries:
        parts = entry.split(":", 3)
        if len(parts) < 3:
            raise ValueError("assumption must be ID:scope:statement[:reviewed]")
        reviewed = len(parts) == 4 and parts[3].lower() == "reviewed"
        assumptions.append(
            AbstractionAssumption(
                assumption_id=parts[0],
                scope=parts[1],
                statement=parts[2],
                reviewed=reviewed,
            )
        )
    return assumptions


def _proof_artifacts_from_args(entries: list[str]) -> list[ProofArtifactRef]:
    artifacts: list[ProofArtifactRef] = []
    for entry in entries:
        parts = entry.split(":", 2)
        if len(parts) < 3:
            raise ValueError("proof artifact must be ID:kind:sha256[@path]")
        kind = parts[1]
        if kind not in {"theorem_statement", "proof_script", "checked_proof", "checker_log"}:
            raise ValueError(f"unsupported proof artifact kind: {kind}")
        artifact_hash, _, artifact_path = parts[2].partition("@")
        artifacts.append(
            ProofArtifactRef(
                artifact_id=parts[0],
                kind=kind,  # type: ignore[arg-type]
                sha256=artifact_hash,
                path=artifact_path or None,
            )
        )
    return artifacts


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


def _artifact_refs_from_args(values: list[str]):
    refs = []
    for value in values:
        if "=" not in value:
            raise ValueError("--artifact values must use name=path")
        name, raw_path = value.split("=", 1)
        if not name:
            raise ValueError("--artifact name cannot be empty")
        refs.append(artifact_ref_from_path(name, Path(raw_path)))
    return refs


def _secrets_from_args(values: list[str]) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--secret values must use key_id=secret")
        key_id, secret = value.split("=", 1)
        if not key_id or not secret:
            raise ValueError("--secret key_id and secret cannot be empty")
        secrets[key_id] = secret
    return secrets


def _key_value_map_from_args(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("values must use key=value")
        key, item = value.split("=", 1)
        if not key or not item:
            raise ValueError("key and value cannot be empty")
        parsed[key] = item
    return parsed


def _key_float_map_from_args(values: list[str]) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in _key_value_map_from_args(values).items()
    }


def _dimension_result_from_arg(value: str) -> ExtendedBenchmarkDimensionResult:
    if "=" not in value:
        raise ValueError("--dimension values must use name=score,total,passed,failed,threshold")
    name, payload = value.split("=", 1)
    parts = [part.strip() for part in payload.split(",")]
    if len(parts) not in {4, 5}:
        raise ValueError("--dimension requires score,total,passed,failed[,threshold]")
    score = float(parts[0])
    total_cases = int(parts[1])
    passed_cases = int(parts[2])
    failed_cases = int(parts[3])
    threshold = float(parts[4]) if len(parts) == 5 else 1.0
    return ExtendedBenchmarkDimensionResult(
        dimension=name,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        score=score,
        threshold=threshold,
        passed=score >= threshold and failed_cases == 0,
    )


def _causal_links_from_args(values: list[str]) -> list[CausalTraceLink]:
    links: list[CausalTraceLink] = []
    for value in values:
        if value.startswith("@"):
            payload = read_json(Path(value[1:]))
        else:
            import json

            payload = json.loads(value)
        if isinstance(payload, list):
            links.extend(CausalTraceLink.model_validate(item) for item in payload)
        else:
            links.append(CausalTraceLink.model_validate(payload))
    return links


def _existing_demo_paths(manifest: ReferenceDemoManifest, *, project_root: Path) -> set[str]:
    paths = [
        manifest.source_root,
        *manifest.system_specs,
        *manifest.trace_artifacts,
        *[item.controlled_text_path for item in manifest.requirements],
        *[
            item.expected_report_path
            for item in manifest.requirements
            if item.expected_report_path is not None
        ],
    ]
    existing: set[str] = set()
    for path in paths:
        if (project_root / path).exists():
            existing.add(path)
    return existing


def _reference_demo_actual_decisions(
    manifest: ReferenceDemoManifest,
    *,
    project_root: Path,
) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for requirement in manifest.requirements:
        if requirement.expected_report_path is None:
            continue
        report_path = project_root / requirement.expected_report_path
        if not report_path.exists():
            continue
        decision = _extract_reference_demo_decision(read_json(report_path))
        if decision is not None:
            decisions[requirement.requirement_id] = decision
    return decisions


def _extract_reference_demo_decision(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    decision = payload.get("decision")
    if decision in {"accepted", "refused", "unknown"}:
        return decision
    status = payload.get("status")
    if status in {"accepted", "refused", "unknown"}:
        return status
    result = payload.get("result")
    if result in {"accepted", "refused", "unknown"}:
        return result
    if result in {"certified", "reproducible", "passed"}:
        return "accepted"
    if result in {"blocked", "failed"}:
        return "refused"
    return None


def _existing_public_doc_paths(index: PublicDocumentationIndex, *, project_root: Path) -> set[str]:
    paths = [*[doc.path for doc in index.docs], *[example.path for example in index.examples]]
    existing: set[str] = set()
    for path in paths:
        if (project_root / path).exists():
            existing.add(path)
    return existing


if __name__ == "__main__":
    raise SystemExit(main())
