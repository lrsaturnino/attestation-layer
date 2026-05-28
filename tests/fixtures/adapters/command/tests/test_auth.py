import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.auth import rejects_unauthorized


def test_rejects_unauthorized() -> None:
    assert rejects_unauthorized() is True
