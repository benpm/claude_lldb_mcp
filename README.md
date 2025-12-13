# LLDB MCP Server

An MCP (Model Context Protocol) server that provides structured debugging tools for LLDB, designed for use with Claude Code and other MCP-compatible AI assistants.

## Features

This server exposes LLDB debugging capabilities through well-defined MCP tools:

### Execution Control
- **lldb_run** - Run a program with optional breakpoints and arguments
- **lldb_analyze_crash** - Analyze crash dumps and core files

### Breakpoints & Watchpoints
- **lldb_set_breakpoint** - Set breakpoints by function, file:line, or address
- **lldb_watchpoint** - Set watchpoints to break on variable access

### Inspection
- **lldb_examine_variables** - View local variables and arguments
- **lldb_backtrace** - Get stack traces for all threads
- **lldb_registers** - View CPU register values
- **lldb_read_memory** - Read and display memory contents
- **lldb_threads** - List all threads and their states

### Code Analysis
- **lldb_disassemble** - Disassemble functions or address ranges
- **lldb_source** - List source code with line numbers
- **lldb_symbols** - Look up symbols by name, regex, or address
- **lldb_images** - List loaded executables and shared libraries

### Expression Evaluation
- **lldb_evaluate** - Evaluate C/C++ expressions in debug context

### Utilities
- **lldb_run_command** - Run arbitrary LLDB commands
- **lldb_help** - Get help on LLDB commands
- **lldb_version** - Show LLDB version info

## Requirements

- Python 3.10+
- LLDB (with command-line tool in PATH)
- `mcp[cli]` Python package

### Installing LLDB

**Ubuntu/Debian:**
```bash
sudo apt install lldb
```

**macOS:**
```bash
# LLDB comes with Xcode Command Line Tools
xcode-select --install
```

**Windows:**
```bash
# Install via LLVM releases or Visual Studio
winget install LLVM.LLVM
```

## Installation

### Quick Start (Recommended)
380. 
381. We provide a setup script that installs all dependencies and verifies the installation.
382. 
383. ```bash
384. # Make the script executable
385. chmod +x setup_for_copilot.sh
386. 
387. # Run the setup script
388. ./setup_for_copilot.sh
389. ```
390. 
391. This script will:
392. 1. Check for Python 3 and pip
393. 2. Install required Python packages (`mcp[cli]`, `pydantic`, `httpx`)
394. 3. Verify the installation by running tests
395. 
396. ### Option 1: Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/lldb-mcp.git
cd lldb-mcp

# Install dependencies
pip install -e .
```

### Option 2: Install dependencies directly

```bash
pip install "mcp[cli]" pydantic httpx
```

## Configuration for Claude Code

### Automatic Configuration
397. 
398. You can easily add the server to Claude Code using the `mcp add` command:
399. 
400. ```bash
401. claude mcp add lldb python3 /path/to/lldb-mcp/lldb_mcp_server.py
402. ```
403. 
404. Replace `/path/to/lldb-mcp` with the actual path to the repository.
405. 
406. ### Manual Configuration
407. 
408. Add the following to your Claude Code MCP configuration file:

### Location of config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Configuration:

```json
{
  "mcpServers": {
    "lldb": {
      "command": "python",
      "args": ["/path/to/lldb-mcp/lldb_mcp_server.py"]
    }
  }
}
```

Or if installed as a package:

```json
{
  "mcpServers": {
    "lldb": {
      "command": "lldb-mcp"
    }
  }
}
```

### Using uvx (recommended for isolation):

```json
{
  "mcpServers": {
    "lldb": {
      "command": "uvx",
      "args": ["--from", "/path/to/lldb-mcp", "lldb-mcp"]
    }
  }
}
```

## Usage Examples

Once configured, you can ask Claude Code to help with debugging tasks:

### Analyze a Crash

> "Analyze the crash dump in ./core and the executable ./myprogram to find what caused the segfault"

### Set Breakpoints and Examine State

> "Set a breakpoint at the processData function in processor.cpp, run the program with argument 'test.txt', and show me the local variables when it stops"

### Disassemble Code

> "Show me the assembly for the main function in ./myprogram"

### Evaluate Expressions

> "Run ./myprogram until it hits parseConfig and evaluate the expression config->max_threads"

### Memory Inspection

> "Read 128 bytes of memory at address 0x7fff5fbff000 in hexadecimal format"

### Symbol Lookup

> "Find all symbols matching 'parse.*' regex in ./myprogram"

## Tool Reference

### lldb_run_command

Execute any LLDB command directly.

```python
{
    "command": "help breakpoint",  # Any LLDB command
    "target": "./myprogram",       # Optional: executable to load
    "working_dir": "/path/to/dir"  # Optional: working directory
}
```

### lldb_analyze_crash

Analyze crash dumps with full context.

```python
{
    "executable": "./myprogram",
    "core_file": "./core",              # Optional: core dump
    "response_format": "markdown"       # or "json"
}
```

### lldb_set_breakpoint

Set breakpoints with conditions.

```python
{
    "executable": "./myprogram",
    "location": "main.cpp:42",          # or "functionName" or "0x400500"
    "condition": "i > 100"              # Optional: break condition
}
```

### lldb_examine_variables

View variables at a breakpoint.

```python
{
    "executable": "./myprogram",
    "breakpoint": "processData",
    "variables": ["buffer", "size"],    # Optional: specific vars
    "args": ["input.txt"],              # Optional: program args
    "response_format": "markdown"
}
```

### lldb_disassemble

Disassemble code regions.

```python
{
    "executable": "./myprogram",
    "target": "main",                   # Function name, address range, or "current"
    "show_bytes": true,                 # Show opcode bytes
    "mixed": true                       # Interleave source
}
```

### lldb_read_memory

Read memory contents.

```python
{
    "executable": "./myprogram",
    "address": "0x7fff5fbff000",
    "count": 64,                        # Bytes to read
    "format": "x",                      # x=hex, b=binary, d=decimal, s=string
    "breakpoint": "main"                # Optional: stop here first
}
```

### lldb_evaluate

Evaluate C/C++ expressions.

```python
{
    "executable": "./myprogram",
    "expression": "ptr->data[5]",
    "breakpoint": "processBuffer",
    "args": ["test.dat"]
}
```

### lldb_backtrace

Get stack traces.

```python
{
    "executable": "./myprogram",
    "breakpoint": "handleError",        # or use core_file
    "core_file": "./core",              # For post-mortem
    "all_threads": true,
    "limit": 50,
    "response_format": "json"           # Structured output
}
```

### lldb_registers

View CPU registers.

```python
{
    "executable": "./myprogram",
    "breakpoint": "criticalSection",
    "register_set": "general",          # general, float, vector, all
    "specific_registers": ["rax", "rbx", "rsp"]  # Optional
}
```

### lldb_watchpoint

Set data watchpoints.

```python
{
    "executable": "./myprogram",
    "variable": "global_counter",
    "watch_type": "write",              # write, read, read_write
    "condition": "global_counter > 1000"
}
```

### lldb_symbols

Look up symbols.

```python
{
    "executable": "./myprogram",
    "query": "process.*",
    "query_type": "regex"               # name, regex, address, type
}
```

## Alternative: Using LLDB's Built-in MCP Server

LLDB 18+ has built-in MCP support. To use it instead:

1. Start LLDB and enable MCP:
   ```
   (lldb) protocol-server start MCP listen://localhost:59999
   ```

2. Configure Claude Code to connect via netcat:
   ```json
   {
     "mcpServers": {
       "lldb": {
         "command": "/usr/bin/nc",
         "args": ["localhost", "59999"]
       }
     }
   }
   ```

Note: LLDB's built-in MCP only exposes a single `lldb_command` tool, whereas this server provides structured, specialized tools for better AI integration.

## Development

### Running Tests

```bash
pytest tests/
```

### Type Checking

```bash
mypy lldb_mcp_server.py
```

### Linting

```bash
ruff check lldb_mcp_server.py
ruff format lldb_mcp_server.py
```

## Troubleshooting

### "LLDB executable not found"

Ensure LLDB is installed and in your PATH:
```bash
which lldb
lldb --version
```

### Permission denied on core files

On Linux, enable core dumps:
```bash
ulimit -c unlimited
sudo sysctl -w kernel.core_pattern=core.%p
```

### Debugger can't find symbols

Compile your programs with debug info:
```bash
g++ -g -O0 myprogram.cpp -o myprogram
clang++ -g -O0 myprogram.cpp -o myprogram
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.
