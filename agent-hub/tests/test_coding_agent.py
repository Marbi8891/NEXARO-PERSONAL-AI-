import pytest
class FakeOllama:
    def __init__(self): self.calls=0
    async def chat_with_tools(self,*,model,messages,tools):
        self.calls+=1
        if self.calls==1:
            return {"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"write_file","arguments":{"path":"calculator.py","content":"def add(a, b): return a + b\n"}}}]}}
        if self.calls==2:
            return {"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"run_command","arguments":{"command":"python -c \"import calculator; assert calculator.add(2,3)==5; print('OK')\""}}}]}}
        return {"message":{"role":"assistant","content":"Implemented calculator.py and verified the command."}}
@pytest.mark.asyncio
async def test_agent_executes_tools(tmp_path,monkeypatch):
    import app.tools as tools
    monkeypatch.setattr(tools,"_workspace",lambda:tmp_path.resolve())
    # This test covers the opt-in path where commands are explicitly allowed.
    monkeypatch.setattr(tools.settings,"coding_agent_allow_commands",True)
    from app.coding_agent import CodingAgent
    result=await CodingAgent(FakeOllama()).execute("Create calculator add function and verify",max_iterations=5)
    assert result["status"]=="completed"
    assert (tmp_path/"calculator.py").exists()
    assert result["tool_calls"]==2
    assert any(e["tool"]=="run_command" and e["success"] for e in result["events"]), result["events"]

@pytest.mark.asyncio
async def test_agent_cannot_run_commands_by_default(tmp_path,monkeypatch):
    import app.tools as tools
    monkeypatch.setattr(tools,"_workspace",lambda:tmp_path.resolve())
    monkeypatch.setattr(tools.settings,"coding_agent_allow_commands",False)
    from app.coding_agent import CodingAgent
    fake=FakeOllama()
    seen_tools=[]
    original=fake.chat_with_tools
    async def spy(*,model,messages,tools):
        seen_tools.append({t["function"]["name"] for t in tools})
        return await original(model=model,messages=messages,tools=tools)
    fake.chat_with_tools=spy
    result=await CodingAgent(fake).execute("Create calculator add function and verify",max_iterations=5)
    assert all("run_command" not in names for names in seen_tools)
    command_events=[e for e in result["events"] if e["tool"]=="run_command"]
    assert command_events and not command_events[0]["success"]
    assert command_events[0]["result"]["error"]=="PermissionError"
