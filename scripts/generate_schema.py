from __future__ import annotations

import json
from pathlib import Path

from nlreq.models import EvidenceObject, RequirementIR, StatusDecision


SCHEMAS = {
    "requirement-ir-0.1.schema.json": RequirementIR,
    "evidence.schema.json": EvidenceObject,
    "status-decision.schema.json": StatusDecision,
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
