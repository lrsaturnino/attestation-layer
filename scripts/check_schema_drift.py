from __future__ import annotations

import json
from pathlib import Path

from nlreq.models import (
    AssumptionsArtifact,
    BindingsArtifact,
    EvidenceObject,
    RequirementIR,
    ReviewArtifact,
    StatusDecision,
    VerificationTasksArtifact,
)


SCHEMAS = {
    "requirement-ir-0.1.schema.json": RequirementIR,
    "assumptions.schema.json": AssumptionsArtifact,
    "bindings.schema.json": BindingsArtifact,
    "evidence.schema.json": EvidenceObject,
    "review.schema.json": ReviewArtifact,
    "status-decision.schema.json": StatusDecision,
    "verification-tasks.schema.json": VerificationTasksArtifact,
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
