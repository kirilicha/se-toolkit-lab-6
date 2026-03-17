# AGENT.md

## Overview
This agent is a CLI documentation agent for Lab 6.

It:
1. Accepts a user question from the command line.
2. Sends the question and tool schemas to an OpenAI-compatible LLM API.
3. Lets the model decide whether to call tools.
4. Executes tool calls locally.
5. Feeds tool results back into the conversation.
6. Returns a final JSON response.

## Model setup
The agent reads these environment variables:
- `LLM_API_KEY`
- `LLM_API_BASE`
- `LLM_MODEL`

## Agentic loop
The agent uses an iterative tool-calling loop:
1. Send messages and tool definitions to the LLM.
2. If the LLM returns tool calls, execute them.
3. Append each tool result as a `tool` message.
4. Repeat until the model returns a final answer or the max tool call limit is reached.

The tool call limit is 10.

## Tools

### `list_files`
Lists files and directories at a relative path inside the project.

Example:
- input: `wiki`
- output: newline-separated file names

### `read_file`
Reads a text file from the repository using a relative path.

Example:
- input: `wiki/git-workflow.md`
- output: file contents

## Path security
Both tools use path resolution relative to the project root.
If a path attempts to escape the repository, for example with `../`, the tool returns an error instead of accessing the filesystem.

## Prompt strategy
The system prompt instructs the model to:
- use `list_files` first to discover available documentation,
- use `read_file` to inspect relevant files,
- answer concisely,
- include a source reference when possible.

## Output format
The CLI prints JSON to stdout with:
- `answer`
- `source`
- `tool_calls`

`tool_calls` contains all executed tools with their arguments and results.
`source` should point to the documentation file and section that supports the answer.