from __future__ import annotations

import re
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from studio.persistence.db import make_engine, upgrade
from studio.persistence.models import Base


def test_migrations_match_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    upgrade(url)
    with make_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_core_has_no_outward_imports() -> None:
    core = Path(__file__).parent.parent / "src" / "studio" / "core"
    forbidden = re.compile(
        r"^\s*(from|import)\s+(studio\.(cli|adapters|persistence|auth|bootstrap|config)|typer|"
        r"sqlalchemy|httpx|fastapi|keyring)\b",
        re.M,
    )
    for f in core.glob("*.py"):
        assert not forbidden.search(f.read_text(encoding="utf-8")), f.name
