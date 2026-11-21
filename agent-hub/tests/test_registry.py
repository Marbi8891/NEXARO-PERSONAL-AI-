from pathlib import Path
import json
from app.registry import AgentRegistry

def test_registry_loads_catalogue(tmp_path: Path):
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(json.dumps({"agents":[{"id":"test_agent","name":"Test","enabled":True}]}), encoding="utf-8")
    registry = AgentRegistry(catalogue)
    registry.load()
    assert registry.get_agent("test_agent")["name"] == "Test"
    assert len(registry.list_agents()) == 1

def test_unknown_agent_returns_none(tmp_path: Path):
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(json.dumps({"agents":[]}), encoding="utf-8")
    registry = AgentRegistry(catalogue)
    registry.load()
    assert registry.get_agent("not_found") is None
