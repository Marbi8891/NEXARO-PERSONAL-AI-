import os
from pathlib import Path
import tempfile

# Keep the test database isolated from the developer's local data.
_TEST_DIR = tempfile.mkdtemp(prefix="nexaro-prompt-tests-")
os.environ["NEXARO_DB_PATH"] = str(Path(_TEST_DIR) / "test.db")

from app.main import init_db, db, render_template  # noqa: E402


def test_template_replaces_variables():
    template = "Hello {{ name }}. You are learning {{topic}}."
    assert render_template(template, {"name": "Ada", "topic": "Python"}) == "Hello Ada. You are learning Python."


def test_template_rejects_missing_variables():
    try:
        render_template("{{required}}", {})
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
    else:
        raise AssertionError("Missing variable should raise HTTP 422")


def test_seed_catalogue_initializes_once():
    init_db()
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
        assert count >= 20
        init_db()
        count_after = conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
        assert count_after == count
