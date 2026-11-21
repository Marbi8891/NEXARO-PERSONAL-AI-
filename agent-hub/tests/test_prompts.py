from app.prompts import build_agent_prompt

def test_prompt_includes_runtime_safety():
    result = build_agent_prompt({"name":"Example","system_prompt":"Do useful work."})
    assert "no tools" in result.lower()
    assert "untrusted data" in result.lower()
    assert "Do useful work." in result
