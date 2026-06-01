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
from nlreq.formal_backend import FormalBackendRequest, FormalBackendResponse
from nlreq.gate import GatePolicy, GateWaiver
from nlreq.routing import AdapterRegistryArtifact, RoutingPolicyArtifact
from nlreq.trace_validation import TraceValidationResultsArtifact
from nlreq.tla_adapter import TlaModelConfigArtifact, TlaResultsArtifact


SCHEMAS = {
    "requirement-ir-0.1.schema.json": RequirementIR,
    "requirement-ir-0.2.schema.json": RequirementIRV2,
    "requirement-ir-migration.schema.json": RequirementIRMigrationRecord,
    "assumptions.schema.json": AssumptionsArtifact,
    "adapter-registry.schema.json": AdapterRegistryArtifact,
    "backend-results.schema.json": BackendResultsArtifact,
    "bindings.schema.json": BindingsArtifact,
    "command-checks.schema.json": CommandChecksArtifact,
    "command-results.schema.json": CommandResultsArtifact,
    "counterexamples.schema.json": CounterexamplesArtifact,
    "evidence.schema.json": EvidenceObject,
    "formal-backend-request.schema.json": FormalBackendRequest,
    "formal-backend-response.schema.json": FormalBackendResponse,
    "gate-policy.schema.json": GatePolicy,
    "generated-tests.schema.json": GeneratedTestsArtifact,
    "normalized-traces.schema.json": NormalizedTraceArtifact,
    "review.schema.json": ReviewArtifact,
    "routing-policy.schema.json": RoutingPolicyArtifact,
    "status-decision.schema.json": StatusDecision,
    "trace-validation-results.schema.json": TraceValidationResultsArtifact,
    "tla-model-config.schema.json": TlaModelConfigArtifact,
    "tla-results.schema.json": TlaResultsArtifact,
    "verification-tasks.schema.json": VerificationTasksArtifact,
    "waiver.schema.json": GateWaiver,
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failed = False
    for filename, model in SCHEMAS.items():
        expected = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        path = root / "schemas" / filename
        actual = path.read_text() if path.exists() else ""
        if actual != expected:
            print(f"schema drift: {path}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
