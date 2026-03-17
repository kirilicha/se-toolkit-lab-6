import json
import subprocess
import sys


def run_agent(question: str) -> dict:
    result = subprocess.run(
        [sys.executable, "agent.py", question],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_merge_conflict_question_uses_read_file():
    data = run_agent("How do you resolve a merge conflict?")

    assert "answer" in data
    assert "source" in data
    assert "tool_calls" in data
    assert any(call["tool"] == "read_file" for call in data["tool_calls"])


def test_list_wiki_question_uses_list_files():
    data = run_agent("What files are in the wiki?")

    assert "answer" in data
    assert "source" in data
    assert "tool_calls" in data
    assert any(call["tool"] == "list_files" for call in data["tool_calls"])