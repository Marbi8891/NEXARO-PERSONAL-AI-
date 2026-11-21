import pytest
class FakeOllama:
    def __init__(self): self.calls=0
    async def chat_with_tools(self,*,model,messages,tools):
        self.calls+=1
        if self.calls==1:
            return {"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"write_file","arguments":{"path":"calculator.py","content":"def add(a, b): return a + b\\n"}}}]}}
        if self.calls==2:
            return {"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"run_command","arguments":{"command":"python -c \"import calculator; assert calculator.add(2,3)==5; print('OK')\""}}}]}}
        return {"message":{"role":"assistant","content":"Implemented calculator.py and verified the command."}}
@pytest.mark.asyncio
async def test_agent_executes_tools(tmp_path,monkeypatch):
    import app.tools as tools
    monkeypatch.setattr(tools,"_workspace",lambda:tmp_path.resolve())
    from app.coding_agent import CodingAgent
    result=await CodingAgent(FakeOllama()).execute("Create calculator add function and verify",max_iterations=5)
    assert result["status"]=="completed"
    assert (tmp_path/"calculator.py").exists()
    assert result["tool_calls"]==2
    assert any(e["tool"]=="run_command" and e["success"] for e in result["events"])
