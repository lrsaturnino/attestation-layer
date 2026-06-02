from __future__ import annotations

import json
from pathlib import Path

from nlreq.models import (
    AssumptionsArtifact,
    BackendResultsArtifact,
    BindingsArtifact,
    CounterexamplesArtifact,
    EvidenceObject,
    GeneratedTestsArtifact,
    NormalizedTraceArtifact,
    RequirementIR,
    RequirementIRMigrationRecord,
    RequirementIRV2,
    ReviewArtifact,
    StatusDecision,
    VerificationTasksArtifact,
)
from nlreq.command_adapter import CommandChecksArtifact, CommandResultsArtifact
from nlreq.adapter_certification import AdapterCertificationReport
from nlreq.agnostic_wedge import AgnosticWedgeReport
from nlreq.artifact_store import (
    ArtifactLookupResult,
    ArtifactStoreManifest,
    ReplayBundleManifest,
)
from nlreq.backend_agreement import BackendAgreementReport
from nlreq.benchmark_corpus import (
    BenchmarkCorpus,
    BenchmarkResultsArtifact,
    BenchmarkRunReport,
)
from nlreq.benchmark_reporting import (
    BenchmarkEvaluationReport,
    ExtendedBenchmarkEvaluationReport,
)
from nlreq.ci_pr_gate import CiAdoptionPolicy, CiPrGateReport, ExtendedCiPrGateReport
from nlreq.conclusion import (
    ConclusionDefinition,
    ConclusionGapCheckReport,
    ConclusionGapChecklist,
)
from nlreq.conclusion_certification import (
    ConclusionCertificationReport,
    ExtendedConclusionCertificationReport,
)
from nlreq.counterexample_normalization import CounterexampleNormalizationReport
from nlreq.controlled_semantics import ControlledRequirementSemanticsReference
from nlreq.cross_language import CrossLanguageProofObject
from nlreq.evidence_boundary import ProofEvidenceBoundaryReport
from nlreq.intake import (
    ControlledRewriteApproval,
    ControlledRewriteProposal,
    FreeFormIntakeArtifact,
)
from nlreq.logical_agreement import LogicalTranslationAgreementReport
from nlreq.provenance import (
    ClarificationRequest,
    ClarificationResponse,
    ClarifiedControlledText,
    ProvenanceGraph,
)
from nlreq.refusal import ProductRefusalReport
from nlreq.review_workflow import ApprovalWorkflowArtifact, ReviewChecklist, ReviewStatusReport
from nlreq.semantic_agreement import SemanticAgreementReport
from nlreq.semantic_translation import SemanticTranslationReport
from nlreq.translation_benchmark import (
    RequirementTranslationBenchmarkReport,
    RequirementTranslationCorpus,
    RequirementTranslationResults,
)
from nlreq.translation_repair import TranslationRepairReport
from nlreq.translator_workbench import TranslatorRunArtifact, TranslatorSelectionArtifact
from nlreq.delta_extractor import DeltaReport
from nlreq.end_to_end_gate import (
    EndToEndRequirementGateReport,
    ExtendedEndToEndRequirementGateReport,
)
from nlreq.evidence_producers import EvidenceProducerValidationReport
from nlreq.formal_backend import FormalBackendRequest, FormalBackendResponse
from nlreq.formal_claim import FormalClaim, FormalClaimLoweringReport
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.gate import GatePolicy, GateWaiver
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.source_impact import SourceImpactAnalysisArtifact
from nlreq.model_checker_runner import ModelCheckerRunArtifact, ModelCheckerRunResult
from nlreq.proof_closure import (
    ClosureGateReport,
    EvidenceProducerMapping,
    ProofDispatchPlan,
    ProofObject,
)
from nlreq.policy_governance import WaiverAuditReport
from nlreq.public_sdk import (
    PublicDocumentationCoverageReport,
    PublicDocumentationFreezeReport,
    PublicDocumentationIndex,
)
from nlreq.reference_demo import (
    ExtendedReferenceDemoReport,
    ReferenceDemoManifest,
    ReferenceDemoReport,
)
from nlreq.requirement_self_consistency import RequirementSelfConsistencyResult
from nlreq.routing import AdapterRegistryArtifact, RoutingPolicyArtifact
from nlreq.runtime_trace_sdk import TraceExtractionResult, TraceProducerRegistry
from nlreq.signed_evidence import (
    ProducerKeyRegistry,
    SignatureVerificationReport,
    SignedEvidenceEnvelope,
)
from nlreq.source_adapter import (
    CodePresentation,
    SourceCallGraph,
    SourceManifest,
    SourceSymbolResolution,
)
from nlreq.spec_drift import CodeSpecManifest, SpecDriftReport
from nlreq.spec_extraction import SpecExtractionWorkbenchReport
from nlreq.spec_freshness import SpecFreshnessLockReport, SpecFreshnessLockfile
from nlreq.system_composition import SandRCompositionReport
from nlreq.system_spec import SystemSpecRegistry, SystemSpecRegistryReport
from nlreq.system_checker import SystemConsistencyResult, RequirementSetConsistencyReport
from nlreq.threat_model import ExtendedTcbReviewReport, ThreatModelReport
from nlreq.tla_projection import TlaProjectionReport
from nlreq.trace_normalization import RawTraceArtifact, TraceNormalizationReport
from nlreq.trace_validation import TraceValidationResultsArtifact
from nlreq.trace_replay import TraceReplayReport
from nlreq.tla_adapter import TlaModelConfigArtifact, TlaResultsArtifact
from nlreq.translator_agreement import TranslationAgreementInput, TranslationAgreementReport
from nlreq.translator import ControlledDraft, LoweredFormalArtifact
from nlreq.verification_budget import (
    BudgetedVerificationOutcome,
    VerificationBudgetReport,
    VerificationBudgetPolicy,
)
from nlreq.verification_cache import (
    VerificationCacheIndex,
    VerificationCacheKey,
    VerificationCacheLookup,
)


SCHEMAS = {
    "requirement-ir-0.1.schema.json": RequirementIR,
    "requirement-ir-0.2.schema.json": RequirementIRV2,
    "requirement-ir-migration.schema.json": RequirementIRMigrationRecord,
    "assumptions.schema.json": AssumptionsArtifact,
    "adapter-certification-report.schema.json": AdapterCertificationReport,
    "adapter-registry.schema.json": AdapterRegistryArtifact,
    "agnostic-wedge-report.schema.json": AgnosticWedgeReport,
    "artifact-lookup-result.schema.json": ArtifactLookupResult,
    "artifact-store-manifest.schema.json": ArtifactStoreManifest,
    "backend-agreement-report.schema.json": BackendAgreementReport,
    "backend-results.schema.json": BackendResultsArtifact,
    "benchmark-corpus.schema.json": BenchmarkCorpus,
    "benchmark-results.schema.json": BenchmarkResultsArtifact,
    "benchmark-run-report.schema.json": BenchmarkRunReport,
    "benchmark-evaluation-report.schema.json": BenchmarkEvaluationReport,
    "extended-benchmark-evaluation-report.schema.json": ExtendedBenchmarkEvaluationReport,
    "ci-adoption-policy.schema.json": CiAdoptionPolicy,
    "ci-pr-gate-report.schema.json": CiPrGateReport,
    "extended-ci-pr-gate-report.schema.json": ExtendedCiPrGateReport,
    "conclusion-definition.schema.json": ConclusionDefinition,
    "conclusion-certification-report.schema.json": ConclusionCertificationReport,
    "extended-conclusion-certification-report.schema.json": ExtendedConclusionCertificationReport,
    "conclusion-gap-checklist.schema.json": ConclusionGapChecklist,
    "conclusion-gap-check-report.schema.json": ConclusionGapCheckReport,
    "bindings.schema.json": BindingsArtifact,
    "command-checks.schema.json": CommandChecksArtifact,
    "command-results.schema.json": CommandResultsArtifact,
    "counterexample-normalization-report.schema.json": CounterexampleNormalizationReport,
    "counterexamples.schema.json": CounterexamplesArtifact,
    "cross-language-proof-object.schema.json": CrossLanguageProofObject,
    "spec-coverage-report.schema.json": SpecCoverageReport,
    "trace-alignment-report.schema.json": TraceAlignmentReport,
    "controlled-draft.schema.json": ControlledDraft,
    "controlled-requirement-semantics.schema.json": ControlledRequirementSemanticsReference,
    "free-form-intake.schema.json": FreeFormIntakeArtifact,
    "controlled-rewrite-proposal.schema.json": ControlledRewriteProposal,
    "controlled-rewrite-approval.schema.json": ControlledRewriteApproval,
    "delta-report.schema.json": DeltaReport,
    "end-to-end-requirement-gate.schema.json": EndToEndRequirementGateReport,
    "extended-end-to-end-requirement-gate.schema.json": ExtendedEndToEndRequirementGateReport,
    "translation-agreement-input.schema.json": TranslationAgreementInput,
    "translation-agreement-report.schema.json": TranslationAgreementReport,
    "logical-translation-agreement-report.schema.json": LogicalTranslationAgreementReport,
    "translator-run.schema.json": TranslatorRunArtifact,
    "translator-selection.schema.json": TranslatorSelectionArtifact,
    "translation-repair-report.schema.json": TranslationRepairReport,
    "provenance-graph.schema.json": ProvenanceGraph,
    "clarification-request.schema.json": ClarificationRequest,
    "clarification-response.schema.json": ClarificationResponse,
    "clarified-controlled-text.schema.json": ClarifiedControlledText,
    "product-refusal-report.schema.json": ProductRefusalReport,
    "semantic-agreement-report.schema.json": SemanticAgreementReport,
    "semantic-translation-report.schema.json": SemanticTranslationReport,
    "approval-workflow.schema.json": ApprovalWorkflowArtifact,
    "review-checklist.schema.json": ReviewChecklist,
    "review-status-report.schema.json": ReviewStatusReport,
    "requirement-translation-corpus.schema.json": RequirementTranslationCorpus,
    "requirement-translation-results.schema.json": RequirementTranslationResults,
    "requirement-translation-benchmark-report.schema.json": RequirementTranslationBenchmarkReport,
    "evidence.schema.json": EvidenceObject,
    "evidence-producer-validation.schema.json": EvidenceProducerValidationReport,
    "proof-evidence-boundary-report.schema.json": ProofEvidenceBoundaryReport,
    "formal-backend-request.schema.json": FormalBackendRequest,
    "formal-backend-response.schema.json": FormalBackendResponse,
    "formal-claim.schema.json": FormalClaim,
    "formal-claim-lowering-report.schema.json": FormalClaimLoweringReport,
    "gate-policy.schema.json": GatePolicy,
    "impact-analysis.schema.json": ImpactAnalysisArtifact,
    "source-impact-analysis.schema.json": SourceImpactAnalysisArtifact,
    "evidence-producer-mapping.schema.json": EvidenceProducerMapping,
    "proof-dispatch-plan.schema.json": ProofDispatchPlan,
    "proof-object.schema.json": ProofObject,
    "producer-key-registry.schema.json": ProducerKeyRegistry,
    "public-documentation-index.schema.json": PublicDocumentationIndex,
    "public-documentation-coverage-report.schema.json": PublicDocumentationCoverageReport,
    "public-documentation-freeze-report.schema.json": PublicDocumentationFreezeReport,
    "closure-gate-report.schema.json": ClosureGateReport,
    "generated-tests.schema.json": GeneratedTestsArtifact,
    "normalized-traces.schema.json": NormalizedTraceArtifact,
    "review.schema.json": ReviewArtifact,
    "reference-demo-manifest.schema.json": ReferenceDemoManifest,
    "reference-demo-report.schema.json": ReferenceDemoReport,
    "extended-reference-demo-report.schema.json": ExtendedReferenceDemoReport,
    "replay-bundle-manifest.schema.json": ReplayBundleManifest,
    "routing-policy.schema.json": RoutingPolicyArtifact,
    "source-call-graph.schema.json": SourceCallGraph,
    "source-code-presentation.schema.json": CodePresentation,
    "source-manifest.schema.json": SourceManifest,
    "source-symbol-resolution.schema.json": SourceSymbolResolution,
    "code-spec-manifest.schema.json": CodeSpecManifest,
    "spec-drift-report.schema.json": SpecDriftReport,
    "spec-extraction-workbench.schema.json": SpecExtractionWorkbenchReport,
    "spec-freshness-lockfile.schema.json": SpecFreshnessLockfile,
    "spec-freshness-lock-report.schema.json": SpecFreshnessLockReport,
    "signed-evidence-envelope.schema.json": SignedEvidenceEnvelope,
    "signature-verification-report.schema.json": SignatureVerificationReport,
    "s-and-r-composition-report.schema.json": SandRCompositionReport,
    "status-decision.schema.json": StatusDecision,
    "system-spec-registry.schema.json": SystemSpecRegistry,
    "system-spec-registry-report.schema.json": SystemSpecRegistryReport,
    "system-consistency-result.schema.json": SystemConsistencyResult,
    "threat-model-report.schema.json": ThreatModelReport,
    "extended-tcb-review-report.schema.json": ExtendedTcbReviewReport,
    "requirement-set-consistency.schema.json": RequirementSetConsistencyReport,
    "requirement-self-consistency.schema.json": RequirementSelfConsistencyResult,
    "lowered-formal-artifact.schema.json": LoweredFormalArtifact,
    "model-checker-run.schema.json": ModelCheckerRunResult,
    "model-checker-runs.schema.json": ModelCheckerRunArtifact,
    "raw-trace-artifact.schema.json": RawTraceArtifact,
    "trace-normalization-report.schema.json": TraceNormalizationReport,
    "trace-producer-registry.schema.json": TraceProducerRegistry,
    "trace-extraction-result.schema.json": TraceExtractionResult,
    "trace-validation-results.schema.json": TraceValidationResultsArtifact,
    "trace-replay-report.schema.json": TraceReplayReport,
    "tla-projection-report.schema.json": TlaProjectionReport,
    "tla-model-config.schema.json": TlaModelConfigArtifact,
    "tla-results.schema.json": TlaResultsArtifact,
    "verification-tasks.schema.json": VerificationTasksArtifact,
    "verification-budget-policy.schema.json": VerificationBudgetPolicy,
    "verification-budget-report.schema.json": VerificationBudgetReport,
    "verification-cache-index.schema.json": VerificationCacheIndex,
    "verification-cache-key.schema.json": VerificationCacheKey,
    "verification-cache-lookup.schema.json": VerificationCacheLookup,
    "budgeted-verification-outcome.schema.json": BudgetedVerificationOutcome,
    "waiver.schema.json": GateWaiver,
    "waiver-audit-report.schema.json": WaiverAuditReport,
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "schemas"
    out_dir.mkdir(exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        (out_dir / filename).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
