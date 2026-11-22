from pathlib import Path

import pytest

from nexaro_core.obsidian.vault import (
    ObsidianVault,
    VaultNotConfiguredError,
    VaultPathError,
)


def test_unconfigured_vault_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    vault = ObsidianVault(None)
    assert vault.status() == {"configured": False, "available": False, "note_count": 0}


def test_list_read_and_search_notes(tmp_path: Path) -> None:
    (tmp_path / "DAW").mkdir()
    note = tmp_path / "DAW" / "Promises.md"
    note.write_text("# Promesas\n\nJavaScript async promises #javascript", encoding="utf-8")

    vault = ObsidianVault(tmp_path)
    listed = vault.list_notes()
    assert listed[0]["path"] == "DAW/Promises.md"
    assert listed[0]["title"] == "Promesas"
    assert "javascript" in listed[0]["tags"]
    assert vault.read_note("DAW/Promises.md")["content"].startswith("# Promesas")
    assert vault.search("promises")[0]["path"] == "DAW/Promises.md"


def test_excludes_obsidian_hidden_and_git_directories(tmp_path: Path) -> None:
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "visible.md").write_text("visible", encoding="utf-8")
    (tmp_path / ".obsidian" / "private.md").write_text("secret", encoding="utf-8")
    (tmp_path / ".hidden" / "private.md").write_text("secret", encoding="utf-8")
    (tmp_path / ".git" / "private.md").write_text("secret", encoding="utf-8")

    vault = ObsidianVault(tmp_path)
    assert [note["path"] for note in vault.list_notes()] == ["visible.md"]
    assert vault.search("secret") == []


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("not in vault", encoding="utf-8")
    vault = ObsidianVault(vault_dir)

    with pytest.raises(VaultPathError):
        vault.read_note("../outside.md")


def test_non_markdown_and_missing_note_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("text", encoding="utf-8")
    vault = ObsidianVault(tmp_path)
    with pytest.raises(VaultPathError):
        vault.read_note("note.txt")
    with pytest.raises(VaultPathError):
        vault.read_note("missing.md")


def test_missing_vault_raises_for_listing(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path / "missing")
    with pytest.raises(VaultNotConfiguredError):
        vault.list_notes()


def test_symlink_outside_vault_is_not_listed_or_searchable(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("sensitive content", encoding="utf-8")
    link = vault_dir / "external.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available on this platform")

    vault = ObsidianVault(vault_dir)
    assert vault.list_notes() == []
    assert vault.search("sensitive") == []
