#!/usr/bin/env python3
"""Apply the idempotent operational database schema."""
from app.models import get_engine
from app.models.migrations import upgrade_database

if __name__ == "__main__":
    print(f"database migration: {upgrade_database(get_engine())}")
