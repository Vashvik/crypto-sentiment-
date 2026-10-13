import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def temp_db(tmp_path):
    from app import db

    original = db.database_path()
    db.set_database_path(tmp_path / "test.db")
    db.init_db()
    yield tmp_path / "test.db"
    db.set_database_path(original)
