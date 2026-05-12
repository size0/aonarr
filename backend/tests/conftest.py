"""Pytest safety setup.

The API tests call Base.metadata.drop_all/create_all. Force them onto a temp
database before app.db.connection is imported, so local development data is not
deleted by a test run.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="novelforgex-test-"))
os.environ.setdefault("NOVELFORGE_DATA_DIR", str(_TEST_DATA_DIR))


def pytest_sessionstart(session):
    from app.db.connection import DATA_DIR

    data_dir = Path(DATA_DIR).resolve()
    if not data_dir.name.startswith("novelforgex-test-"):
        raise RuntimeError(f"Refusing to run tests against non-test database: {data_dir}")
