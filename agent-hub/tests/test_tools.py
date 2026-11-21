import pytest
from app.tools import _safe_path,write_file,read_file,edit_file,run_command
@pytest.fixture
def workspace(tmp_path,monkeypatch):
    import app.tools as tools
    monkeypatch.setattr(tools,"_workspace",lambda:tmp_path.resolve())
    return tmp_path
def test_write_read_edit(workspace):
    assert write_file("src/sample.py","x=1\n")["success"]
    assert read_file("src/sample.py")["content"]=="x=1\n"
    edit_file("src/sample.py","x=1","x=2")
    assert read_file("src/sample.py")["content"]=="x=2\n"
def test_path_traversal_rejected(workspace):
    with pytest.raises(ValueError): _safe_path("../outside.txt")
def test_sensitive_file_rejected(workspace):
    with pytest.raises(PermissionError): _safe_path(".env")
@pytest.mark.asyncio
async def test_allowlisted_command(workspace):
    result=await run_command("python -c \"print('hello')\"")
    assert result["exit_code"]==0 and "hello" in result["stdout"]
@pytest.mark.asyncio
async def test_shell_operators_rejected(workspace):
    with pytest.raises(ValueError): await run_command("python -c \"print(1)\"; whoami")
