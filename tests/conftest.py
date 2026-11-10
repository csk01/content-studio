from __future__ import annotations

from pathlib import Path

import pytest

from studio.persistence.db import make_engine, upgrade
from studio.persistence.repo import SqlRepository


@pytest.fixture
def mp4(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 600_000)
    return p


@pytest.fixture
def repo(tmp_path: Path) -> SqlRepository:
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    upgrade(url)
    return SqlRepository(make_engine(url))
