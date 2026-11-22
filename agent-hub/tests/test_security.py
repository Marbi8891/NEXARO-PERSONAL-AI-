"""Access control for the coding agent endpoint and tool permissions (no Ollama needed)."""
import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.tools as tools
from app.config import Settings, settings

TOKEN="test-token-123"
BODY={"task":"list files","max_iterations":1}

class FakeAgent:
    async def execute(self,**kwargs): return {"status":"completed","kwargs":kwargs}

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main,"coding_agent",FakeAgent())
    with TestClient(main.app) as c: yield c

def configure(monkeypatch,enabled,token=""):
    monkeypatch.setattr(settings,"coding_agent_enabled",enabled)
    monkeypatch.setattr(settings,"agent_hub_api_token",token)

def test_coding_agent_disabled_by_default():
    fresh=Settings(_env_file=None)
    assert fresh.coding_agent_enabled is False
    assert fresh.coding_agent_allow_commands is False
    assert fresh.agent_hub_api_token==""

def test_disabled_endpoint_returns_503(client,monkeypatch):
    configure(monkeypatch,False,TOKEN)
    assert client.post("/api/coding/execute",json=BODY,headers={"Authorization":f"Bearer {TOKEN}"}).status_code==503
    assert client.get("/health").json()["coding_agent"]=="disabled"

def test_enabled_without_token_is_misconfigured(client,monkeypatch):
    configure(monkeypatch,True,"")
    assert client.post("/api/coding/execute",json=BODY).status_code==503
    assert client.get("/health").json()["coding_agent"]=="misconfigured"

@pytest.mark.parametrize("header",[None,"Bearer wrong","Basic "+TOKEN,TOKEN])
def test_missing_or_wrong_token_rejected(client,monkeypatch,header):
    configure(monkeypatch,True,TOKEN)
    headers={"Authorization":header} if header else {}
    assert client.post("/api/coding/execute",json=BODY,headers=headers).status_code==401

def test_valid_token_reaches_agent(client,monkeypatch):
    configure(monkeypatch,True,TOKEN)
    r=client.post("/api/coding/execute",json=BODY,headers={"Authorization":f"Bearer {TOKEN}"})
    assert r.status_code==200 and r.json()["status"]=="completed"

def test_run_command_hidden_and_blocked_by_default(monkeypatch):
    monkeypatch.setattr(settings,"coding_agent_allow_commands",False)
    assert "run_command" not in {t["function"]["name"] for t in tools.enabled_tool_schemas()}
    with pytest.raises(PermissionError):
        import asyncio
        asyncio.run(tools.execute_tool("run_command",{"command":"python -c \"print(1)\""}))

def test_run_command_offered_when_allowed(monkeypatch):
    monkeypatch.setattr(settings,"coding_agent_allow_commands",True)
    assert "run_command" in {t["function"]["name"] for t in tools.enabled_tool_schemas()}

@pytest.mark.parametrize("path",[".git/config",".git/hooks/pre-commit","sub/.git/config"])
def test_git_internals_are_denied(tmp_path,monkeypatch,path):
    monkeypatch.setattr(tools,"_workspace",lambda:tmp_path.resolve())
    with pytest.raises(PermissionError):
        tools.write_file(path,"[core]\n\tfsmonitor = evil\n")

def test_env_example_catalogue_path_resolves():
    from pathlib import Path
    env=Path(__file__).resolve().parents[1]/".env.example"
    s=Settings(_env_file=str(env))
    assert s.catalogue_path.exists(), s.catalogue_path
