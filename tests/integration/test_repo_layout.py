from __future__ import annotations

from pathlib import Path


def test_expected_top_level_dirs_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in ["macro", "industry", "company", "contracts", "integration", "shared", "alembic"]:
        assert (root / name).exists()
