#!/usr/bin/env python3
"""Run SQL migrations against the database."""

import asyncio
import sys
from pathlib import Path

import asyncpg


async def run_migrations():
    database_url = None

    # Try loading from .env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                # Convert SQLAlchemy URL to plain postgres URL
                database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
                break

    if not database_url:
        print("ERROR: DATABASE_URL not found. Set it in .env or as an environment variable.")
        sys.exit(1)

    migrations_dir = Path(__file__).parent.parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("No migration files found.")
        return

    conn = await asyncpg.connect(database_url)
    try:
        for migration_file in migration_files:
            print(f"Running migration: {migration_file.name}")
            sql = migration_file.read_text()
            await conn.execute(sql)
            print(f"  Done: {migration_file.name}")

        print("\nAll migrations completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
