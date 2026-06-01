from __future__ import annotations

import json
from pathlib import Path

from generate_schema import SCHEMAS


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
