# Task 3 Plan

## Goal
Extend the Task 2 documentation agent into a system agent that can also query the running backend API.

## New tool
I will add a new function-calling tool named `query_api`.

### Purpose
This tool will let the agent ask the deployed backend for live system facts and data-dependent answers, such as:
- item counts
- status codes
- analytics endpoint results

### Parameters
The tool schema will include:
- `method` — HTTP method such as `GET`
- `path` — API path such as `/items/`
- `body` — optional JSON string for request payloads

### Return format
The tool will return a JSON string with:
- `status_code`
- `body`

## Authentication
The backend requires `LMS_API_KEY`, which I will load from environment variables.
I will not hardcode it.
The LLM configuration will still use:
- `LLM_API_KEY`
- `LLM_API_BASE`
- `LLM_MODEL`

## API base URL
I will read `AGENT_API_BASE_URL` from environment variables.
If it is missing, I will default to `http://localhost:42002`.

## Agent behavior
The agentic loop stays the same as in Task 2.
The LLM will decide between:
- `list_files` for directory discovery
- `read_file` for wiki/source inspection
- `query_api` for live backend requests

## Prompt update
I will update the system prompt so the LLM knows:
- when to use wiki tools
- when to inspect source code
- when to call the running API
- how to combine API errors with source reading to diagnose bugs

## Benchmark plan
I will run the local benchmark with the command `uv run run_eval.py`.

Then I will record:
- my initial score
- the first failing questions
- what tool or prompt issue caused them
- how I will iterate until all 10 local questions pass

## Regression tests
I will add 2 more regression tests:
1. A source-code question that should use `read_file`
2. A live backend data question that should use `query_api`