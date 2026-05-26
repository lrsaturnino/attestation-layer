import subprocess
import sys


def test_schema_generation_has_no_drift() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_schema_drift.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
