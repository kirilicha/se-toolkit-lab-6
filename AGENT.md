# Agent (Task 1)

Run:
uv run agent.py "your question"

The agent reads LLM config from `.env.agent.secret`:
- LLM_API_KEY
- LLM_API_BASE
- LLM_MODEL

It calls the OpenAI-compatible endpoint:
POST {LLM_API_BASE}/chat/completions

Output: a single JSON line to stdout:
{"answer": "...", "tool_calls": []}

Debug logs go to stderr.
