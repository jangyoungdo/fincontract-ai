from sqlalchemy import inspect, select

from app.models import get_engine
from app.models.migrations import MIGRATION_VERSION, schema_migrations, upgrade_database


def test_initial_migration_is_recorded_and_idempotent() -> None:
    engine = get_engine()
    first = upgrade_database(engine)
    second = upgrade_database(engine)
    assert first in {"upgraded", "already_current"}
    assert second == "already_current"
    assert {"documents", "analyses", "audit_events", "schema_migrations"}.issubset(
        inspect(engine).get_table_names()
    )
    with engine.connect() as connection:
        assert connection.execute(
            select(schema_migrations.c.version).where(schema_migrations.c.version == MIGRATION_VERSION)
        ).scalar_one() == MIGRATION_VERSION


def test_bank_product_tagging_columns_exist_after_upgrade() -> None:
    engine = get_engine()
    upgrade_database(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    assert {"bank_name", "product_type"}.issubset(columns)
