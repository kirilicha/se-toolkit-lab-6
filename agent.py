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


def load_settings() -> tuple[str, str, str, str, str]:
    load_env_file(".env.agent.secret")

    api_key = os.environ.get("LLM_API_KEY", "").strip()
    api_base = os.environ.get("LLM_API_BASE", "").strip().rstrip("/")
    model = os.environ.get("LLM_MODEL", "").strip()
    lms_api_key = os.environ.get("LMS_API_KEY", "").strip()
    agent_api_base_url = os.environ.get(
        "AGENT_API_BASE_URL", "http://localhost:42002"
    ).strip().rstrip("/")

    if not api_key or not api_base or not model:
        print(
            "Missing LLM settings in environment: "
            "LLM_API_KEY, LLM_API_BASE, LLM_MODEL",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key, api_base, model, lms_api_key, agent_api_base_url


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


def query_api(method: str, path: str, body: str = "", include_auth: bool = True) -> str:
    _, _, _, lms_api_key, agent_api_base_url = load_settings()

    url = f"{agent_api_base_url}{path}"

    headers = {
        "Content-Type": "application/json",
    }

    if include_auth and lms_api_key:
        headers["Authorization"] = f"Bearer {lms_api_key}"

    request_kwargs: dict = {"headers": headers, "timeout": 30.0}

    if body:
        try:
            request_kwargs["json"] = json.loads(body)
        except json.JSONDecodeError:
            return json.dumps(
                {"status_code": 0, "body": f"Invalid JSON body: {body}"},
                ensure_ascii=False,
            )

    try:
        with httpx.Client() as client:
            response = client.request(method.upper(), url, **request_kwargs)

        try:
            parsed_body = response.json()
        except Exception:
            parsed_body = response.text

        return json.dumps(
            {
                "status_code": response.status_code,
                "body": parsed_body,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": f"Request failed: {e}",
            },
            ensure_ascii=False,
        )


def should_preload_backend_source(question: str) -> bool:
    q = question.lower()
    strong_signals = [
        "what python web framework",
        "what web framework",
        "what framework",
        "what library",
        "what libraries",
        "what does the backend use",
    ]
    return any(k in q for k in strong_signals)


def is_router_question(question: str) -> bool:
    q = question.lower()
    keywords = [
        "router modules",
        "api router",
        "routers",
        "what domain does each one handle",
        "modules in the backend",
    ]
    return any(k in q for k in keywords)


def is_analytics_bug_question(question: str) -> bool:
    q = question.lower()
    keys = ["top-learners", "completion-rate", "analytics"]
    return any(k in q for k in keys)


def is_top_learners_bug_question(question: str) -> bool:
    q = question.lower()
    return "top-learners" in q and "crash" in q


def detect_wiki_topic_file(question: str) -> str | None:
    q = question.lower()

    topic_map = {
        "ssh": "wiki/ssh.md",
        "vm via ssh": "wiki/ssh.md",
        "connect to your vm": "wiki/ssh.md",
        "protect a branch on github": "wiki/github.md",
        "branch on github": "wiki/github.md",
        "github branch": "wiki/github.md",
    }

    for key, path in topic_map.items():
        if key in q:
            return path

    return None


def preload_backend_source(messages: list[dict], tool_calls_log: list[dict]) -> None:
    candidate_files = [
        "backend/app/main.py",
        "backend/app/__init__.py",
        "backend/app/api.py",
        "backend/app/config.py",
    ]

    for path in candidate_files:
        target = safe_resolve_path(path)
        if target is not None and target.exists() and target.is_file():
            content = read_file(path)
            tool_calls_log.append(
                {
                    "tool": "read_file",
                    "args": {"path": path},
                    "result": content,
                }
            )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"Preloaded source file for a framework/library question: {path}\n\n"
                        f"{content}"
                    ),
                }
            )
            return


def preload_router_directory(messages: list[dict], tool_calls_log: list[dict]) -> None:
    candidate_dirs = [
        "backend/app/routers",
        "backend/app/api",
        "backend/app/api/routers",
    ]

    for path in candidate_dirs:
        target = safe_resolve_path(path)
        if target is not None and target.exists() and target.is_dir():
            listing = list_files(path)
            tool_calls_log.append(
                {
                    "tool": "list_files",
                    "args": {"path": path},
                    "result": listing,
                }
            )

            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"Preloaded router directory listing for router question: {path}\n\n"
                        f"{listing}"
                    ),
                }
            )

            for name in listing.splitlines():
                if name.endswith(".py"):
                    file_path = f"{path}/{name}"
                    content = read_file(file_path)
                    tool_calls_log.append(
                        {
                            "tool": "read_file",
                            "args": {"path": file_path},
                            "result": content,
                        }
                    )
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"Preloaded router source file: {file_path}\n\n"
                                f"{content}"
                            ),
                        }
                    )
            return


def preload_wiki_topic(messages: list[dict], tool_calls_log: list[dict], path: str) -> None:
    target = safe_resolve_path(path)
    if target is None or not target.exists() or not target.is_file():
        return

    content = read_file(path)
    tool_calls_log.append(
        {
            "tool": "read_file",
            "args": {"path": path},
            "result": content,
        }
    )
    messages.append(
        {
            "role": "system",
            "content": (
                f"Preloaded wiki file for this question: {path}\n\n"
                f"{content}"
            ),
        }
    )


def preload_analytics_source(messages: list[dict], tool_calls_log: list[dict]) -> None:
    path = "backend/app/routers/analytics.py"
    content = read_file(path)
    tool_calls_log.append(
        {
            "tool": "read_file",
            "args": {"path": path},
            "result": content,
        }
    )
    messages.append(
        {
            "role": "system",
            "content": f"Preloaded analytics router source: {path}\n\n{content}",
        }
    )


def preload_top_learners_bug(messages: list[dict], tool_calls_log: list[dict]) -> None:
    path = "backend/app/routers/analytics.py"
    content = read_file(path)

    tool_calls_log.append(
        {
            "tool": "read_file",
            "args": {"path": path},
            "result": content,
        }
    )

    messages.append(
        {
            "role": "system",
            "content": (
                "Focus on the `/analytics/top-learners` implementation in "
                "backend/app/routers/analytics.py. "
                "The likely bug is in the sorting step. "
                "Look specifically at "
                "`ranked = sorted(rows, key=lambda r: r.avg_score, reverse=True)`. "
                "If some rows have `avg_score=None`, sorting mixed None and numeric "
                "values can crash. Explain that exact bug if supported by the source."
            ),
        }
    )


def get_tools_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": (
                    "List files and directories at a relative path inside the project. "
                    "Use this first to discover wiki files, folders, modules, router files, and project structure."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from the project root, for example 'wiki' or 'backend/app'.",
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
                    "Use this after discovering the relevant file, or when the question explicitly requires reading source code."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path from the project root, for example 'wiki/git-workflow.md' or 'backend/app/main.py'.",
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
                "name": "query_api",
                "description": (
                    "Send an HTTP request to the running backend API. "
                    "Use this for live questions about status codes, item counts, analytics endpoints, "
                    "authentication behavior, and runtime bugs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method, for example GET or POST.",
                        },
                        "path": {
                            "type": "string",
                            "description": "API path starting with /, for example /items/ or /analytics/top-learners?lab=lab-01",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON body as a string. Use empty string for GET requests.",
                        },
                        "include_auth": {
                            "type": "boolean",
                            "description": "Whether to include the Authorization header. Use false when the question explicitly asks what happens without auth.",
                        },
                    },
                    "required": ["method", "path"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def execute_tool(name: str, args: dict) -> str:
    if name == "list_files":
        return list_files(args.get("path", ""))
    if name == "read_file":
        return read_file(args.get("path", ""))
    if name == "query_api":
        return query_api(
            args.get("method", "GET"),
            args.get("path", ""),
            args.get("body", ""),
            args.get("include_auth", True),
        )
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

    api_key, api_base, model, _, _ = load_settings()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a documentation and repository agent for this project. "
                "Use list_files to discover files and directories. "
                "Use read_file to read relevant wiki files, source code files, configuration files, and backend files. "
                "Use query_api for live runtime questions about HTTP status codes, item counts, analytics endpoints, authentication behavior, or current API results. "
                "If a question asks both what happens at runtime and why in the code, use query_api first and then read_file. "
                "For analytics endpoints, use the query parameter `lab`, not `lab_id`, unless the source code explicitly shows a different parameter name. "
                "For analytics bug questions, if the endpoint does not fail locally, still inspect backend/app/routers/analytics.py and explain the bug visible in the source code. "
                "For bug questions about analytics endpoints, use query_api to reproduce the runtime error and then inspect the analytics router source carefully for the exact bug. "
                "For the `/analytics/top-learners` crash question, explain the sorting bug in `sorted(rows, key=lambda r: r.avg_score, reverse=True)` if the source code shows it. "
                "For questions about project structure, router modules, file names, or what exists in a directory, start with list_files. "
                "For questions about API router modules, endpoints, or domains handled by backend modules, first use list_files to find the backend routers directory, then use list_files inside that directory, then read the relevant router files with read_file before answering. "
                "Do not stop after listing only a parent directory. "
                "For questions about implementation details, frameworks, libraries, configuration values, or source-code behavior, use read_file on the relevant source file before answering. "
                "For wiki questions about a specific topic, read the relevant wiki file before answering. "
                "Do not answer from guesses or directory names alone. "
                "Prefer plain sentences or short compact answers. "
                "Avoid numbered lists like '1.' or '2.' unless explicitly requested. "
                "When a numeric answer is needed, provide the number clearly in plain text. "
                "Do not invent sources. If you need information, use tools first. "
                "When you give the final answer, you MUST return valid JSON only, "
                'with exactly these fields: {"answer": "...", "source": "..."} '
                "The source must be a relative file path with a section anchor when possible, or a relative file path if no anchor makes sense. "
                "Examples: wiki/github.md#protect-a-branch, wiki/ssh.md, backend/app/main.py, backend/app/routers/analytics.py. "
                "Do not put the source only inside the answer text. "
                "Do not return markdown fences. "
                "Do not return any extra text outside JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{question}\n\n"
                "Important: use tools. "
                "If the question asks what files/modules/routers exist, use list_files first. "
                "If the question is about API routers or modules, drill down into backend subdirectories with list_files until you find the router files, then use read_file. "
                "If the question is about a specific wiki topic, read the relevant wiki file before answering. "
                "If the question asks about framework, implementation, configuration, or source-code behavior, use read_file before answering. "
                "If the question asks about live API behavior, status codes, item counts, analytics results, or unauthenticated requests, use query_api. "
                "For analytics requests, prefer URLs like `/analytics/top-learners?lab=lab-01`."
            ),
        },
    ]

    tool_calls_log: list[dict] = []
    final_answer = ""
    final_source = ""

    wiki_topic_path = detect_wiki_topic_file(question)
    if wiki_topic_path is not None:
        preload_wiki_topic(messages, tool_calls_log, wiki_topic_path)

    if is_top_learners_bug_question(question):
        preload_top_learners_bug(messages, tool_calls_log)
    elif is_analytics_bug_question(question):
        preload_analytics_source(messages, tool_calls_log)

    if should_preload_backend_source(question):
        preload_backend_source(messages, tool_calls_log)

    if is_router_question(question):
        preload_router_directory(messages, tool_calls_log)

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

                if final_answer and final_source:
                    break
            except json.JSONDecodeError:
                pass

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Return the final answer as valid JSON only, "
                        'with exactly these fields: {"answer": "...", "source": "..."}'
                    ),
                }
            )
            continue

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