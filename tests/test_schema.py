import subprocess
import sys
from pathlib import Path


def test_schema_generation_has_no_drift() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_schema_drift.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_auxiliary_artifact_schemas_are_committed() -> None:
    schema_dir = Path("schemas")

    assert (schema_dir / "assumptions.schema.json").exists()
    assert (schema_dir / "bindings.schema.json").exists()
    assert (schema_dir / "review.schema.json").exists()
    assert (schema_dir / "verification-tasks.schema.json").exists()
