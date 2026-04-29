import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from app.core.config import get_settings


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def main() -> None:
    settings = get_settings()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError("No migration files found")
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for migration_file in migration_files:
                cur.execute(migration_file.read_text(encoding="utf-8"))
        conn.commit()
    print(f"applied_migrations_ok count={len(migration_files)}")


if __name__ == "__main__":
    main()
