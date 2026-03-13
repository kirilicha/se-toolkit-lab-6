import json
import subprocess
import sys

def test_agent_outputs_required_fields():
    p = subprocess.run(
        [sys.executable, "agent.py", "What does REST stand for?"],
        capture_output=True,
        text=True,
        check=True,
    )
    obj = json.loads(p.stdout.strip())
    assert "answer" in obj
    assert "tool_calls" in obj
    assert isinstance(obj["tool_calls"], list)
