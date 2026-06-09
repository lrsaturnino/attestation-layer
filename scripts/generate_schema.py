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
from nlreq.adapter_certification import (
    AdapterCertificationFixture,
    AdapterCertificationReport,
    AdapterPluginManifest,
    AdapterPluginValidationReport,
)
from nlreq.agnostic_wedge import AgnosticWedgeReport
from nlreq.artifact_store import (
    ArtifactLookupResult,
    ArtifactStoreManifest,
    ReplayBundleManifest,
    ReplayBundleManifestV2,
    ReplayVerificationReport,
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
    PublicBenchmarkReleaseReport,
    PublicBenchmarkSuite,
    PublicLeaderboardEntry,
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
    FinalRealEvidenceConclusionCertificationReport,
)
from nlreq.counterexample_normalization import (
    CounterexampleExplanationReport,
    CounterexampleNormalizationReport,
)
from nlreq.controlled_semantics import ControlledRequirementSemanticsReference
from nlreq.cross_language import CrossLanguageProofObject, CrossLanguageProofObjectV2
from nlreq.evidence_boundary import (
    ProofEvidenceBoundaryReport,
    ProofProducingBackendBoundaryReport,
)
from nlreq.intake import (
    ControlledRewriteApproval,
    ControlledRewriteProposal,
    FreeFormIntakeArtifact,
    FreeFormIntakeRuntimeRecord,
    RewritePromptRegistry,
    RewriteReplayBundle,
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
from nlreq.semantic_agreement import SemanticAgreementCalibrationReport, SemanticAgreementReport
from nlreq.semantic_translation import SemanticDecompositionTree, SemanticTranslationReport
from nlreq.translation_benchmark import (
    RequirementTranslationBenchmarkReport,
    RequirementTranslationCorpus,
    RequirementTranslationReleaseBarReport,
    RequirementTranslationReleaseThresholds,
    RequirementTranslationResults,
)
from nlreq.translation_repair import TranslationRepairHistory, TranslationRepairReport
from nlreq.translator_workbench import TranslatorRunArtifact, TranslatorSelectionArtifact
from nlreq.delta_extractor import DeltaReport
from nlreq.end_to_end_gate import (
    EndToEndRequirementGateReport,
    ExtendedEndToEndRequirementGateReport,
)
from nlreq.evidence_producers import EvidenceProducerValidationReport
from nlreq.formal_backend import FormalBackendRequest, FormalBackendResponse
from nlreq.formal_claim import (
    FormalClaim,
    FormalClaimLoweringReport,
    FormalClaimSemanticsCompletionReference,
)
from nlreq.coverage_alignment import (
    CodeSpecCoverageGateReportV2,
    CodeSpecCoverageManifestV2,
    SpecCoverageGateReport,
    SpecCoverageReport,
    TraceAlignmentReport,
)
from nlreq.gate import GatePolicy, GateWaiver
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.source_impact import ProductionSourceImpactReport, SourceImpactAnalysisArtifact
from nlreq.model_checker_runner import ModelCheckerRunArtifact, ModelCheckerRunResult
from nlreq.proof_closure import (
    ClosureGateReport,
    EvidenceProducerMapping,
    ProofDispatchPlan,
    ProofObject,
)
from nlreq.policy_governance import (
    CiPolicyGovernanceReportV2,
    PolicyChangeRecord,
    WaiverAuditReport,
)
from nlreq.public_sdk import (
    PublicDocumentationCoverageReport,
    PublicDocumentationFreezeReport,
    PublicDocumentationIndex,
)
from nlreq.reference_demo import (
    BetaPilotReport,
    ExtendedReferenceDemoReport,
    ReferenceBrownfieldPilotReport,
    ReferenceDemoManifest,
    ReferenceDemoReport,
)
from nlreq.real_evidence import (
    ClaudeConvoGapAssessment,
    RealEvidenceMilestoneReport,
    RealEvidencePhasePlan,
    RealEvidencePhaseReport,
)
from nlreq.requirement_self_consistency import (
    RequirementContradictionTaxonomy,
    RequirementSelfConsistencyResult,
)
from nlreq.routing import AdapterRegistryArtifact, RoutingPolicyArtifact
from nlreq.runtime_trace_sdk import (
    TraceExtractionResult,
    TraceProducerEvidenceReport,
    TraceProducerRegistry,
)
from nlreq.signed_evidence import (
    ProducerKeyRegistry,
    SignatureVerificationReport,
    SignedEvidenceEnvelope,
)
from nlreq.source_adapter import (
    AdapterCapabilityContract,
    AdapterCapabilityRegistry,
    CodePresentation,
    SourceCallGraph,
    SourceManifest,
    SourceSymbolResolution,
)
from nlreq.spec_drift import CodeSpecManifest, SpecDriftReport
from nlreq.spec_extraction import (
    CandidateSpecReviewReport,
    SpecExtractionWorkbenchReport,
    SpeculaExtractionIntegrationReport,
)
from nlreq.spec_freshness import (
    SpecFreshnessDriftCiReport,
    SpecFreshnessLockReport,
    SpecFreshnessLockfile,
    SpecFreshnessLockfileV2,
)
from nlreq.system_composition import SandRCompositionReport
from nlreq.system_spec import SpecTraceContract, SystemSpecRegistry, SystemSpecRegistryReport
from nlreq.system_checker import SystemConsistencyResult, RequirementSetConsistencyReport
from nlreq.threat_model import ExtendedTcbReviewReport, ThreatModelReport
from nlreq.tla_projection import TlaProjectionReport
from nlreq.trace_normalization import RawTraceArtifact, TraceNormalizationReport
from nlreq.trace_validation import (
    SpecCodeAlignmentReport,
    TraceValidationGateReport,
    TraceValidationResultsArtifact,
)
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
    ParallelDispatchPlan,
    ParallelDispatchTask,
    VerificationCacheIndex,
    VerificationCacheKey,
    VerificationCacheLookup,
    VerificationCachePolicyV2,
)


SCHEMAS = {
    "requirement-ir-0.1.schema.json": RequirementIR,
    "requirement-ir-0.2.schema.json": RequirementIRV2,
    "requirement-ir-migration.schema.json": RequirementIRMigrationRecord,
    "assumptions.schema.json": AssumptionsArtifact,
    "adapter-capability-contract.schema.json": AdapterCapabilityContract,
    "adapter-capability-registry.schema.json": AdapterCapabilityRegistry,
    "adapter-certification-fixture.schema.json": AdapterCertificationFixture,
    "adapter-certification-report.schema.json": AdapterCertificationReport,
    "adapter-plugin-manifest.schema.json": AdapterPluginManifest,
    "adapter-plugin-validation-report.schema.json": AdapterPluginValidationReport,
    "adapter-registry.schema.json": AdapterRegistryArtifact,
    "agnostic-wedge-report.schema.json": AgnosticWedgeReport,
    "artifact-lookup-result.schema.json": ArtifactLookupResult,
    "artifact-store-manifest.schema.json": ArtifactStoreManifest,
    "replay-bundle-manifest-v2.schema.json": ReplayBundleManifestV2,
    "replay-verification-report.schema.json": ReplayVerificationReport,
    "backend-agreement-report.schema.json": BackendAgreementReport,
    "backend-results.schema.json": BackendResultsArtifact,
    "benchmark-corpus.schema.json": BenchmarkCorpus,
    "benchmark-results.schema.json": BenchmarkResultsArtifact,
    "benchmark-run-report.schema.json": BenchmarkRunReport,
    "benchmark-evaluation-report.schema.json": BenchmarkEvaluationReport,
    "extended-benchmark-evaluation-report.schema.json": ExtendedBenchmarkEvaluationReport,
    "public-benchmark-suite.schema.json": PublicBenchmarkSuite,
    "public-benchmark-release-report.schema.json": PublicBenchmarkReleaseReport,
    "public-leaderboard-entry.schema.json": PublicLeaderboardEntry,
    "ci-adoption-policy.schema.json": CiAdoptionPolicy,
    "ci-pr-gate-report.schema.json": CiPrGateReport,
    "extended-ci-pr-gate-report.schema.json": ExtendedCiPrGateReport,
    "conclusion-definition.schema.json": ConclusionDefinition,
    "conclusion-certification-report.schema.json": ConclusionCertificationReport,
    "extended-conclusion-certification-report.schema.json": ExtendedConclusionCertificationReport,
    "final-real-evidence-conclusion-certification-report.schema.json": FinalRealEvidenceConclusionCertificationReport,
    "conclusion-gap-checklist.schema.json": ConclusionGapChecklist,
    "conclusion-gap-check-report.schema.json": ConclusionGapCheckReport,
    "bindings.schema.json": BindingsArtifact,
    "command-checks.schema.json": CommandChecksArtifact,
    "command-results.schema.json": CommandResultsArtifact,
    "counterexample-explanation-report.schema.json": CounterexampleExplanationReport,
    "counterexample-normalization-report.schema.json": CounterexampleNormalizationReport,
    "counterexamples.schema.json": CounterexamplesArtifact,
    "cross-language-proof-object.schema.json": CrossLanguageProofObject,
    "cross-language-proof-object-v2.schema.json": CrossLanguageProofObjectV2,
    "spec-coverage-report.schema.json": SpecCoverageReport,
    "spec-coverage-gate-report.schema.json": SpecCoverageGateReport,
    "code-spec-coverage-manifest-v2.schema.json": CodeSpecCoverageManifestV2,
    "code-spec-coverage-gate-report-v2.schema.json": CodeSpecCoverageGateReportV2,
    "trace-alignment-report.schema.json": TraceAlignmentReport,
    "controlled-draft.schema.json": ControlledDraft,
    "controlled-requirement-semantics.schema.json": ControlledRequirementSemanticsReference,
    "free-form-intake.schema.json": FreeFormIntakeArtifact,
    "free-form-intake-runtime-record.schema.json": FreeFormIntakeRuntimeRecord,
    "controlled-rewrite-proposal.schema.json": ControlledRewriteProposal,
    "controlled-rewrite-approval.schema.json": ControlledRewriteApproval,
    "rewrite-prompt-registry.schema.json": RewritePromptRegistry,
    "rewrite-replay-bundle.schema.json": RewriteReplayBundle,
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
    "semantic-agreement-calibration-report.schema.json": SemanticAgreementCalibrationReport,
    "semantic-translation-report.schema.json": SemanticTranslationReport,
    "semantic-decomposition-tree.schema.json": SemanticDecompositionTree,
    "approval-workflow.schema.json": ApprovalWorkflowArtifact,
    "review-checklist.schema.json": ReviewChecklist,
    "review-status-report.schema.json": ReviewStatusReport,
    "requirement-translation-corpus.schema.json": RequirementTranslationCorpus,
    "requirement-translation-results.schema.json": RequirementTranslationResults,
    "requirement-translation-benchmark-report.schema.json": RequirementTranslationBenchmarkReport,
    "requirement-translation-release-thresholds.schema.json": RequirementTranslationReleaseThresholds,
    "requirement-translation-release-bar-report.schema.json": RequirementTranslationReleaseBarReport,
    "evidence.schema.json": EvidenceObject,
    "evidence-producer-validation.schema.json": EvidenceProducerValidationReport,
    "proof-evidence-boundary-report.schema.json": ProofEvidenceBoundaryReport,
    "proof-producing-backend-boundary-report.schema.json": ProofProducingBackendBoundaryReport,
    "formal-backend-request.schema.json": FormalBackendRequest,
    "formal-backend-response.schema.json": FormalBackendResponse,
    "formal-claim.schema.json": FormalClaim,
    "formal-claim-lowering-report.schema.json": FormalClaimLoweringReport,
    "formal-claim-semantics-completion.schema.json": FormalClaimSemanticsCompletionReference,
    "gate-policy.schema.json": GatePolicy,
    "impact-analysis.schema.json": ImpactAnalysisArtifact,
    "source-impact-analysis.schema.json": SourceImpactAnalysisArtifact,
    "production-source-impact-report.schema.json": ProductionSourceImpactReport,
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
    "beta-pilot-report.schema.json": BetaPilotReport,
    "reference-brownfield-pilot-report.schema.json": ReferenceBrownfieldPilotReport,
    "real-evidence-phase-plan.schema.json": RealEvidencePhasePlan,
    "real-evidence-phase-report.schema.json": RealEvidencePhaseReport,
    "real-evidence-milestone-report.schema.json": RealEvidenceMilestoneReport,
    "claude-convo-gap-assessment.schema.json": ClaudeConvoGapAssessment,
    "replay-bundle-manifest.schema.json": ReplayBundleManifest,
    "routing-policy.schema.json": RoutingPolicyArtifact,
    "source-call-graph.schema.json": SourceCallGraph,
    "source-code-presentation.schema.json": CodePresentation,
    "source-manifest.schema.json": SourceManifest,
    "source-symbol-resolution.schema.json": SourceSymbolResolution,
    "code-spec-manifest.schema.json": CodeSpecManifest,
    "spec-drift-report.schema.json": SpecDriftReport,
    "spec-extraction-workbench.schema.json": SpecExtractionWorkbenchReport,
    "specula-extraction-integration-report.schema.json": SpeculaExtractionIntegrationReport,
    "candidate-spec-review-report.schema.json": CandidateSpecReviewReport,
    "spec-freshness-lockfile.schema.json": SpecFreshnessLockfile,
    "spec-freshness-lock-report.schema.json": SpecFreshnessLockReport,
    "spec-freshness-lockfile-v2.schema.json": SpecFreshnessLockfileV2,
    "spec-freshness-drift-ci-report.schema.json": SpecFreshnessDriftCiReport,
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
    "requirement-contradiction-taxonomy.schema.json": RequirementContradictionTaxonomy,
    "requirement-self-consistency.schema.json": RequirementSelfConsistencyResult,
    "lowered-formal-artifact.schema.json": LoweredFormalArtifact,
    "model-checker-run.schema.json": ModelCheckerRunResult,
    "model-checker-runs.schema.json": ModelCheckerRunArtifact,
    "raw-trace-artifact.schema.json": RawTraceArtifact,
    "trace-normalization-report.schema.json": TraceNormalizationReport,
    "trace-producer-registry.schema.json": TraceProducerRegistry,
    "trace-extraction-result.schema.json": TraceExtractionResult,
    "trace-producer-evidence-report.schema.json": TraceProducerEvidenceReport,
    "trace-validation-results.schema.json": TraceValidationResultsArtifact,
    "trace-validation-gate-report.schema.json": TraceValidationGateReport,
    "trace-replay-report.schema.json": TraceReplayReport,
    "spec-trace-contract.schema.json": SpecTraceContract,
    "spec-code-alignment-report.schema.json": SpecCodeAlignmentReport,
    "tla-projection-report.schema.json": TlaProjectionReport,
    "tla-model-config.schema.json": TlaModelConfigArtifact,
    "tla-results.schema.json": TlaResultsArtifact,
    "verification-tasks.schema.json": VerificationTasksArtifact,
    "verification-budget-policy.schema.json": VerificationBudgetPolicy,
    "verification-budget-report.schema.json": VerificationBudgetReport,
    "verification-cache-index.schema.json": VerificationCacheIndex,
    "verification-cache-key.schema.json": VerificationCacheKey,
    "verification-cache-lookup.schema.json": VerificationCacheLookup,
    "verification-cache-policy-v2.schema.json": VerificationCachePolicyV2,
    "parallel-dispatch-task.schema.json": ParallelDispatchTask,
    "parallel-dispatch-plan.schema.json": ParallelDispatchPlan,
    "budgeted-verification-outcome.schema.json": BudgetedVerificationOutcome,
    "waiver.schema.json": GateWaiver,
    "waiver-audit-report.schema.json": WaiverAuditReport,
    "policy-change-record.schema.json": PolicyChangeRecord,
    "ci-policy-governance-report-v2.schema.json": CiPolicyGovernanceReportV2,
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
