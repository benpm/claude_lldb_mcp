# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an MCP (Model Context Protocol) server that provides structured debugging tools for LLDB. It exposes 17 specialized tools for debugging C/C++ programs, designed for use with Claude Code and other MCP clients.

## Architecture

### Core Components

**lldb_mcp_server.py** - Single-file MCP server implementation with three main sections:

1. **LLDB Command Execution Layer** (lines 65-166)
   - `_run_lldb_command()`: Execute single LLDB commands via subprocess
   - `_run_lldb_script()`: Execute multiple LLDB commands in batch mode
   - All LLDB interaction happens via command-line invocation, NOT Python bindings
   - Commands run in batch mode with `--batch` and `-o` flags

2. **Input Models** (lines 179-583)
   - Pydantic models for each tool's parameters
   - All models use `ConfigDict(str_strip_whitespace=True)`
   - Field validation with min/max lengths and ranges
   - `ResponseFormat` enum for markdown vs JSON output

3. **MCP Tools** (lines 636-1451)
   - 17 `@mcp.tool()` decorated async functions
   - Each tool builds a command list, executes via `_run_lldb_script()`, and formats output
   - Tools annotated with hints (readOnlyHint, destructiveHint, etc.)

### Server Execution Model

- Uses FastMCP from `mcp.server.fastmcp`
- Runs in stdio mode for Claude Code integration
- All LLDB commands run via subprocess (batch mode), no persistent debug sessions
- Entry point: `mcp.run()` at line 1458

### Global State

Lines 43-63 define `DebugSession` class and session storage (`_sessions`), but these are currently unused. The server is stateless - each tool invocation spawns a new LLDB process.

## Common Development Commands

### Running the Server

```bash
# Direct execution (for Claude Code)
python lldb_mcp_server.py

# With uvx
uvx --from . lldb-mcp

# Testing
python test_server.py
```

### Testing and Validation

```bash
# Run test suite
pytest tests/

# Type checking
mypy lldb_mcp_server.py

# Linting
ruff check lldb_mcp_server.py

# Format code
ruff format lldb_mcp_server.py
```

### Installation

```bash
# Install in development mode
pip install -e .

# Install dependencies only
pip install "mcp[cli]" pydantic httpx
```

## Key Implementation Patterns

### Adding New Tools

1. Create Pydantic input model inheriting from `BaseModel`
2. Add `@mcp.tool()` decorator with name and annotations
3. Build LLDB command list as strings
4. Execute with `_run_lldb_script(commands, target, working_dir, timeout)`
5. Format output (markdown or JSON based on `response_format` if applicable)
6. Return formatted string

### LLDB Command Construction

Tools follow a consistent pattern:
```python
commands = [f"target create {params.executable}"]
if params.breakpoint:
    commands.append(f"breakpoint set --name {params.breakpoint}")
    commands.append("run" + (" " + " ".join(params.args) if params.args else ""))
commands.append("quit")  # For non-crash analysis
result = _run_lldb_script(commands)
```

### Breakpoint Location Parsing

See `lldb_set_breakpoint` (lines 758-798):
- `file:line` format → `breakpoint set --file X --line Y`
- `0x...` format → `breakpoint set --address X`
- Other → `breakpoint set --name X` (function name)

## Configuration

**pyproject.toml** defines:
- Package metadata and entry point (`lldb-mcp`)
- Dependencies: mcp[cli]>=1.0.0, pydantic>=2.0.0, httpx>=0.25.0
- Dev dependencies: pytest, ruff, mypy
- Ruff config: line-length=100, Python 3.10+
- MyPy: strict mode enabled

**Claude Code MCP Configuration** - Users add to their Claude config:
```json
{
  "mcpServers": {
    "lldb": {
      "command": "python",
      "args": ["/path/to/lldb_mcp_server.py"]
    }
  }
}
```

## Important Notes

- LLDB must be installed and in PATH (`lldb` command)
- Server runs commands with 30-60 second timeouts (configurable)
- No persistent debug sessions - each tool call is independent
- Error handling returns structured responses with success/error/output fields
- All file paths in parameters should be absolute or relative to working_dir
