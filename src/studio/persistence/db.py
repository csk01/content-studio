from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

_MIGRATIONS = Path(__file__).parent / "migrations"


def make_engine(url: str) -> Engine:
    return create_engine(url)


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str) -> None:
    """Bring the database schema to head. Schema changes only happen via Alembic."""
    command.upgrade(alembic_config(url), "head")
