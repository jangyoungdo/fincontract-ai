"""Small, dependency-free schema migration runner for the initial operational schema."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, select
from sqlalchemy.engine import Engine

from .database import Base

MIGRATION_VERSION = "0001_initial_operational_schema"
_metadata = MetaData()
schema_migrations = Table(
    "schema_migrations",
    _metadata,
    Column("version", String(100), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def upgrade_database(engine: Engine) -> str:
    """Apply the idempotent baseline on SQLite or PostgreSQL and record it."""
    _metadata.create_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        applied = connection.execute(
            select(schema_migrations.c.version).where(schema_migrations.c.version == MIGRATION_VERSION)
        ).scalar_one_or_none()
        if applied:
            return "already_current"
        connection.execute(
            schema_migrations.insert().values(
                version=MIGRATION_VERSION, applied_at=datetime.now(timezone.utc)
            )
        )
    return "upgraded"
