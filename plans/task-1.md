# Task 1 plan

Provider: Qwen Code API via qwen-code-oai-proxy on VM (OpenAI-compatible).
Config is stored in .env.agent.secret: LLM_API_KEY, LLM_API_BASE, LLM_MODEL.

agent.py:
- reads question from argv
- loads .env.agent.secret
- calls POST {LLM_API_BASE}/chat/completions
- prints one-line JSON to stdout: {"answer": "...", "tool_calls": []}
- prints debug only to stderr

Test:
- run agent.py as subprocess
- parse stdout JSON
- check that "answer" and "tool_calls" exist
