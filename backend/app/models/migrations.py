"""Small, dependency-free schema migration runner for the operational schema."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, inspect, select, text
from sqlalchemy.engine import Engine

from .database import Base

MIGRATION_VERSION = "0002_bank_product_tagging"
_metadata = MetaData()
schema_migrations = Table(
    "schema_migrations",
    _metadata,
    Column("version", String(100), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)

# create_all() only creates missing tables; columns added to an ORM model after
# a table already exists need an explicit, idempotent ALTER TABLE here.
_NEW_COLUMNS = ("bank_name", "product_type")


def _add_missing_document_columns(engine: Engine) -> None:
    """Add bank_name/product_type to an existing documents table if absent."""
    existing = {column["name"] for column in inspect(engine).get_columns("documents")}
    with engine.begin() as connection:
        if "bank_name" not in existing:
            connection.execute(text("ALTER TABLE documents ADD COLUMN bank_name VARCHAR(255)"))
        if "product_type" not in existing:
            connection.execute(text("ALTER TABLE documents ADD COLUMN product_type VARCHAR(30)"))


def _applied_versions(engine: Engine) -> set[str]:
    with engine.begin() as connection:
        return set(connection.execute(select(schema_migrations.c.version)).scalars())


def _record_version(engine: Engine, version: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema_migrations.insert().values(version=version, applied_at=datetime.now(timezone.utc))
        )


def upgrade_database(engine: Engine) -> str:
    """Apply idempotent baseline + incremental migrations on SQLite or PostgreSQL."""
    _metadata.create_all(engine)
    Base.metadata.create_all(engine)
    applied = _applied_versions(engine)
    upgraded = False

    if "0001_initial_operational_schema" not in applied:
        _record_version(engine, "0001_initial_operational_schema")
        upgraded = True

    if "0002_bank_product_tagging" not in applied:
        _add_missing_document_columns(engine)
        _record_version(engine, "0002_bank_product_tagging")
        upgraded = True

    return "upgraded" if upgraded else "already_current"
