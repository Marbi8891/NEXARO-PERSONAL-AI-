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
        assert count >= 120
        assert conn.execute("SELECT COUNT(*) FROM prompts WHERE id LIKE 'catalog-%'").fetchone()[0] == 100
        init_db()
        count_after = conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
        assert count_after == count


def test_pack_catalogue_contains_six_packs():
    from app.main import pack_catalogue
    packs = pack_catalogue()["packs"]
    assert len(packs) == 6
    assert all(pack["prompt_ids"] for pack in packs)


def test_import_preview_accepts_prompt_and_flags_duplicates():
    from app.main import import_preview, create_prompt, PromptCreate
    create_prompt(PromptCreate(name="Import Test Prompt", category="Testing", user_template="Test {{topic}}", variables=[{"name":"topic","required":True}]))
    result = import_preview({"prompts":[{"name":"Import Test Prompt","category":"Testing","user_template":"Test {{topic}}"}]})
    assert result["valid"] == 1
    assert result["items"][0]["duplicate"]["name"] == "Import Test Prompt"


def test_workflow_crud_persists_ordered_nodes():
    from app.main import create_workflow, get_workflow, update_workflow, delete_workflow
    created = create_workflow({"name":"Test Flow","nodes":[{"prompt_id":"python-tutor"},{"prompt_id":"sql-tutor"}]})
    assert [n["prompt_id"] for n in created["nodes"]] == ["python-tutor","sql-tutor"]
    updated = update_workflow(created["id"], {"name":"Updated Flow","nodes":[{"prompt_id":"sql-tutor"},{"prompt_id":"python-tutor"}]})
    assert updated["name"] == "Updated Flow"
    assert [n["prompt_id"] for n in get_workflow(created["id"])["nodes"]] == ["sql-tutor","python-tutor"]
    assert delete_workflow(created["id"])["deleted"] is True


def test_prompt_search_filters_metadata():
    from app.main import list_prompts
    education = list_prompts(prompt_type="Education", limit=250)
    assert education
    assert all(p["prompt_type"] == "Education" for p in education)
    security = list_prompts(q="authorized", limit=250)
    assert security
    assert any("authorized" in " ".join(p["tags"]).lower() for p in security)


def test_version_restore_creates_new_version():
    from app.main import create_prompt, update_prompt, restore_prompt_version, PromptCreate
    created = create_prompt(PromptCreate(name="Version Test",category="Testing",user_template="Original {{x}}"))
    update_prompt(created["id"],PromptCreate(name="Version Test",category="Testing",user_template="Changed {{x}}",changelog="Changed"))
    restored = restore_prompt_version(created["id"],1)
    assert restored["user_template"] == "Original {{x}}"
    assert restored["version"] == 3


def test_create_prompt_rejects_unsafe_id():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        unsafe = client.post("/api/prompts", json={"id": 'x"><img src=x onerror=alert(1)>', "name": "Unsafe", "category": "Test", "user_template": "t"})
        assert unsafe.status_code == 422
        safe = client.post("/api/prompts", json={"id": "safe-id_1.0", "name": "Safe", "category": "Test", "user_template": "t"})
        assert safe.status_code == 200 and safe.json()["id"] == "safe-id_1.0"


def test_frontend_escapes_ids_in_attributes():
    import re

    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"\$\{(p|r|w|x)\.id\}", source), "IDs must go through esc() before reaching innerHTML"
    assert 'name="${name}"' not in source
