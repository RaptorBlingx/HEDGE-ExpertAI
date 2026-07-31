#!/usr/bin/env python3
"""Apply ordered PostgreSQL migrations exactly once under an advisory lock."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).with_name("migrations")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://hedge:hedge-dev-only@postgres:5432/hedge",
)


def main() -> None:
    migration_files = sorted(MIGRATIONS.glob("*.up.sql"))
    if not migration_files:
        raise SystemExit("no migrations found")

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (1_716_704_981,))
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}

            for migration_file in migration_files:
                version = migration_file.name.removesuffix(".up.sql")
                if version in applied:
                    continue
                cursor.execute(migration_file.read_text())
                cursor.execute(
                    """
                    INSERT INTO schema_migrations (version)
                    VALUES (%s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (version,),
                )
                print(f"applied migration {version}")


if __name__ == "__main__":
    main()
