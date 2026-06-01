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
from nlreq.agnostic_wedge import AgnosticWedgeReport
from nlreq.formal_backend import FormalBackendRequest, FormalBackendResponse
from nlreq.coverage_alignment import SpecCoverageReport, TraceAlignmentReport
from nlreq.gate import GatePolicy, GateWaiver
from nlreq.impact import ImpactAnalysisArtifact
from nlreq.impact_v2 import ImpactAnalysisV2Artifact
from nlreq.model_checker_runner import ModelCheckerRunArtifact, ModelCheckerRunResult
from nlreq.proof_closure import (
    ClosureGateReport,
    EvidenceProducerMapping,
    ProofDispatchPlan,
    ProofObject,
)
from nlreq.requirement_self_consistency import RequirementSelfConsistencyResult
from nlreq.routing import AdapterRegistryArtifact, RoutingPolicyArtifact
from nlreq.source_adapter import (
    CodePresentation,
    SourceCallGraph,
    SourceManifest,
    SourceSymbolResolution,
)
from nlreq.spec_drift import CodeSpecManifest, SpecDriftReport
from nlreq.spec_extraction import SpecExtractionWorkbenchReport
from nlreq.system_spec import SystemSpecRegistry, SystemSpecRegistryReport
from nlreq.system_checker import SystemConsistencyResult, RequirementSetConsistencyReport
from nlreq.trace_validation import TraceValidationResultsArtifact
from nlreq.trace_replay import TraceReplayReport
from nlreq.tla_adapter import TlaModelConfigArtifact, TlaResultsArtifact
from nlreq.translator_agreement import TranslationAgreementInput, TranslationAgreementReport
from nlreq.translator import ControlledDraft, LoweredFormalArtifact


SCHEMAS = {
    "requirement-ir-0.1.schema.json": RequirementIR,
    "requirement-ir-0.2.schema.json": RequirementIRV2,
    "requirement-ir-migration.schema.json": RequirementIRMigrationRecord,
    "assumptions.schema.json": AssumptionsArtifact,
    "adapter-registry.schema.json": AdapterRegistryArtifact,
    "agnostic-wedge-report.schema.json": AgnosticWedgeReport,
    "backend-results.schema.json": BackendResultsArtifact,
    "bindings.schema.json": BindingsArtifact,
    "command-checks.schema.json": CommandChecksArtifact,
    "command-results.schema.json": CommandResultsArtifact,
    "counterexamples.schema.json": CounterexamplesArtifact,
    "spec-coverage-report.schema.json": SpecCoverageReport,
    "trace-alignment-report.schema.json": TraceAlignmentReport,
    "controlled-draft.schema.json": ControlledDraft,
    "translation-agreement-input.schema.json": TranslationAgreementInput,
    "translation-agreement-report.schema.json": TranslationAgreementReport,
    "evidence.schema.json": EvidenceObject,
    "formal-backend-request.schema.json": FormalBackendRequest,
    "formal-backend-response.schema.json": FormalBackendResponse,
    "gate-policy.schema.json": GatePolicy,
    "impact-analysis.schema.json": ImpactAnalysisArtifact,
    "impact-analysis-v2.schema.json": ImpactAnalysisV2Artifact,
    "evidence-producer-mapping.schema.json": EvidenceProducerMapping,
    "proof-dispatch-plan.schema.json": ProofDispatchPlan,
    "proof-object.schema.json": ProofObject,
    "closure-gate-report.schema.json": ClosureGateReport,
    "generated-tests.schema.json": GeneratedTestsArtifact,
    "normalized-traces.schema.json": NormalizedTraceArtifact,
    "review.schema.json": ReviewArtifact,
    "routing-policy.schema.json": RoutingPolicyArtifact,
    "source-call-graph.schema.json": SourceCallGraph,
    "source-code-presentation.schema.json": CodePresentation,
    "source-manifest.schema.json": SourceManifest,
    "source-symbol-resolution.schema.json": SourceSymbolResolution,
    "code-spec-manifest.schema.json": CodeSpecManifest,
    "spec-drift-report.schema.json": SpecDriftReport,
    "spec-extraction-workbench.schema.json": SpecExtractionWorkbenchReport,
    "status-decision.schema.json": StatusDecision,
    "system-spec-registry.schema.json": SystemSpecRegistry,
    "system-spec-registry-report.schema.json": SystemSpecRegistryReport,
    "system-consistency-result.schema.json": SystemConsistencyResult,
    "requirement-set-consistency.schema.json": RequirementSetConsistencyReport,
    "requirement-self-consistency.schema.json": RequirementSelfConsistencyResult,
    "lowered-formal-artifact.schema.json": LoweredFormalArtifact,
    "model-checker-run.schema.json": ModelCheckerRunResult,
    "model-checker-runs.schema.json": ModelCheckerRunArtifact,
    "trace-validation-results.schema.json": TraceValidationResultsArtifact,
    "trace-replay-report.schema.json": TraceReplayReport,
    "tla-model-config.schema.json": TlaModelConfigArtifact,
    "tla-results.schema.json": TlaResultsArtifact,
    "verification-tasks.schema.json": VerificationTasksArtifact,
    "waiver.schema.json": GateWaiver,
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
