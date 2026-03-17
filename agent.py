import json
import os
import sys
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent
MAX_TOOL_CALLS = 10


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> tuple[str, str, str]:
    load_env_file(".env.agent.secret")

    api_key = os.environ.get("LLM_API_KEY", "").strip()
    api_base = os.environ.get("LLM_API_BASE", "").strip().rstrip("/")
    model = os.environ.get("LLM_MODEL", "").strip()

    if not api_key or not api_base or not model:
        print(
            "Missing LLM settings in environment: "
            "LLM_API_KEY, LLM_API_BASE, LLM_MODEL",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key, api_base, model


def safe_resolve_path(relative_path: str) -> Path | None:
    candidate = (PROJECT_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError:
        return None
    return candidate


def list_files(path: str) -> str:
    target = safe_resolve_path(path)
    if target is None:
        return "Error: access outside project root is not allowed."
    if not target.exists():
        return f"Error: path does not exist: {path}"
    if not target.is_dir():
        return f"Error: not a directory: {path}"

    entries = sorted(p.name for p in target.iterdir())
    return "\n".join(entries)


def read_file(path: str) -> str:
    target = safe_resolve_path(path)
    if target is None:
        return "Error: access outside project root is not allowed."
    if not target.exists():
        return f"Error: file does not exist: {path}"
    if not target.is_file():
        return f"Error: not a file: {path}"

    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file {path}: {e}"


def get_tools_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": (
                    "List files and directories at a relative path inside the project. "
                    "Use this first to discover wiki files and folders."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from the project root, for example 'wiki'.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read a text file from the project using a relative path. "
                    "Use this to inspect wiki or source files after discovering them."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path from the project root, for example 'wiki/git-workflow.md'.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def execute_tool(name: str, args: dict) -> str:
    if name == "list_files":
        return list_files(args["path"])
    if name == "read_file":
        return read_file(args["path"])
    return f"Error: unknown tool {name}"


def call_llm(messages: list[dict], api_key: str, api_base: str, model: str) -> dict:
    url = f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "tools": get_tools_schema(),
        "tool_choice": "auto",
        "temperature": 0,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        print(f"Unexpected LLM response format: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "Your question"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1].strip()
    if not question:
        print("Question must not be empty", file=sys.stderr)
        sys.exit(1)

    api_key, api_base, model = load_settings()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a documentation agent for this repository. "
                "Use list_files to discover files, especially in the wiki directory. "
                "Use read_file to read relevant documentation and source files. "
                "When you answer, provide a concise answer and include a source reference "
                "as a relative file path with a section anchor when possible, like "
                "'wiki/git-workflow.md#resolving-merge-conflicts'. "
                "Do not invent sources. If you need information, use tools first."
            ),
        },
        {
            "role": "user",
            "content": question,
        },
    ]

    tool_calls_log: list[dict] = []
    final_answer = ""
    final_source = ""

    for _ in range(MAX_TOOL_CALLS):
        try:
            msg = call_llm(messages, api_key, api_base, model)
        except httpx.HTTPError as e:
            print(f"LLM request failed: {e}", file=sys.stderr)
            sys.exit(1)

        assistant_content = msg.get("content") or ""
        assistant_tool_calls = msg.get("tool_calls", [])

        if assistant_tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": assistant_tool_calls,
                }
            )

            for tc in assistant_tool_calls:
                tool_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                try:
                    tool_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    tool_args = {}

                tool_result = execute_tool(tool_name, tool_args)
                tool_calls_log.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": tool_result,
                    }
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    }
                )
            continue

        text = assistant_content.strip()
        if text:
            try:
                parsed = json.loads(text)
                final_answer = str(parsed.get("answer", "")).strip()
                final_source = str(parsed.get("source", "")).strip()
            except json.JSONDecodeError:
                final_answer = text
                final_source = ""
            break

    if not final_answer:
        final_answer = "I could not find a reliable answer within the tool call limit."

    result = {
        "answer": final_answer,
        "source": final_source,
        "tool_calls": tool_calls_log,
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()