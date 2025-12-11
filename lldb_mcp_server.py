#!/usr/bin/env python3
"""
LLDB MCP Server - A Model Context Protocol server for LLDB debugger integration.

This server provides structured tools for debugging C/C++ programs via LLDB,
designed for use with Claude Code and other MCP clients.

Usage:
    # As stdio server (for Claude Code)
    python lldb_mcp_server.py

    # Or with uvx
    uvx --from . lldb-mcp

Requirements:
    - LLDB with Python bindings (lldb module)
    - mcp[cli] (pip install mcp[cli])
    - pydantic
"""

import json
import subprocess
import os
import re
import shutil
from typing import Optional, List, Dict, Any
from enum import Enum
from pathlib import Path
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict, field_validator


# =============================================================================
# Server Configuration
# =============================================================================

SERVER_NAME = "lldb_mcp"
LLDB_EXECUTABLE = shutil.which("lldb") or "lldb"

# Global state for managing debug sessions
class DebugSession:
    """Represents an active LLDB debug session."""
    def __init__(self, session_id: str, target_path: Optional[str] = None):
        self.session_id = session_id
        self.target_path = target_path
        self.process = None
        self.breakpoints: Dict[int, Dict[str, Any]] = {}
        self.is_running = False
        self.last_output = ""

# Session storage
_sessions: Dict[str, DebugSession] = {}
_session_counter = 0


def _get_next_session_id() -> str:
    """Generate a unique session ID."""
    global _session_counter
    _session_counter += 1
    return f"lldb_{_session_counter}"


def _run_lldb_command(command: str, target: Optional[str] = None, 
                       args: Optional[List[str]] = None,
                       timeout: int = 30) -> Dict[str, Any]:
    """
    Execute an LLDB command and return the output.
    
    This runs LLDB in batch mode for simple commands.
    """
    cmd = [LLDB_EXECUTABLE]
    
    if target:
        cmd.extend(["--file", target])
    
    # Add batch commands
    cmd.extend(["--batch", "-o", command])
    
    if args:
        cmd.append("--")
        cmd.extend(args)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "return_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Command timed out after {timeout} seconds",
            "return_code": -1
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": "",
            "error": f"LLDB executable not found at '{LLDB_EXECUTABLE}'. Please ensure LLDB is installed and in PATH.",
            "return_code": -1
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1
        }


def _run_lldb_script(commands: List[str], target: Optional[str] = None,
                     working_dir: Optional[str] = None,
                     timeout: int = 60) -> Dict[str, Any]:
    """
    Execute multiple LLDB commands in sequence.
    """
    cmd = [LLDB_EXECUTABLE]
    
    if target:
        cmd.extend(["--file", target])
    
    cmd.append("--batch")
    
    for command in commands:
        cmd.extend(["-o", command])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir or os.getcwd()
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "return_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Commands timed out after {timeout} seconds",
            "return_code": -1
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "return_code": -1
        }


# =============================================================================
# Initialize MCP Server
# =============================================================================

mcp = FastMCP(SERVER_NAME)


# =============================================================================
# Input Models
# =============================================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


class RunCommandInput(BaseModel):
    """Input for running arbitrary LLDB commands."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    command: str = Field(
        ...,
        description="The LLDB command to execute (e.g., 'help', 'version', 'breakpoint list')",
        min_length=1,
        max_length=2000
    )
    target: Optional[str] = Field(
        default=None,
        description="Path to the executable to debug (optional)"
    )
    working_dir: Optional[str] = Field(
        default=None,
        description="Working directory for the command"
    )


class AnalyzeCrashInput(BaseModel):
    """Input for analyzing a crashed program."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable that crashed",
        min_length=1
    )
    core_file: Optional[str] = Field(
        default=None,
        description="Path to the core dump file (optional)"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for structured data"
    )


class SetBreakpointInput(BaseModel):
    """Input for setting breakpoints."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    location: str = Field(
        ...,
        description="Breakpoint location: function name (e.g., 'main'), file:line (e.g., 'main.cpp:42'), or address (e.g., '0x1234')",
        min_length=1
    )
    condition: Optional[str] = Field(
        default=None,
        description="Conditional expression for the breakpoint (e.g., 'i > 10')"
    )


class ExamineVariablesInput(BaseModel):
    """Input for examining variables."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    breakpoint: str = Field(
        ...,
        description="Breakpoint location to stop at",
        min_length=1
    )
    variables: Optional[List[str]] = Field(
        default=None,
        description="Specific variable names to examine (if None, shows all locals)"
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Command-line arguments to pass to the program"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format"
    )


class DisassembleInput(BaseModel):
    """Input for disassembling code."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    target: str = Field(
        ...,
        description="What to disassemble: function name, address range (e.g., '0x1000-0x1100'), or 'current' for current frame",
        min_length=1
    )
    show_bytes: bool = Field(
        default=False,
        description="Show opcode bytes alongside instructions"
    )
    mixed: bool = Field(
        default=False,
        description="Show mixed source and assembly"
    )


class ReadMemoryInput(BaseModel):
    """Input for reading memory."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    address: str = Field(
        ...,
        description="Memory address to read from (hex, e.g., '0x7fff5fbff000')",
        min_length=1
    )
    count: int = Field(
        default=64,
        description="Number of bytes to read",
        ge=1,
        le=4096
    )
    format: str = Field(
        default="x",
        description="Output format: 'x' (hex), 'b' (binary), 'd' (decimal), 's' (string), 'i' (instructions)"
    )
    breakpoint: Optional[str] = Field(
        default=None,
        description="Breakpoint location to stop at before reading memory"
    )


class EvaluateExpressionInput(BaseModel):
    """Input for evaluating expressions."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    expression: str = Field(
        ...,
        description="C/C++ expression to evaluate (e.g., 'sizeof(int)', 'ptr->member', 'array[5]')",
        min_length=1
    )
    breakpoint: str = Field(
        ...,
        description="Breakpoint location for evaluation context",
        min_length=1
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Command-line arguments to pass to the program"
    )


class BacktraceInput(BaseModel):
    """Input for getting a backtrace."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    breakpoint: Optional[str] = Field(
        default=None,
        description="Breakpoint location to stop at (or use with core file)"
    )
    core_file: Optional[str] = Field(
        default=None,
        description="Path to core dump file for post-mortem analysis"
    )
    all_threads: bool = Field(
        default=False,
        description="Show backtraces for all threads"
    )
    limit: int = Field(
        default=50,
        description="Maximum number of frames to show",
        ge=1,
        le=1000
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Command-line arguments to pass to the program"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format"
    )


class ListSourceInput(BaseModel):
    """Input for listing source code."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    file: Optional[str] = Field(
        default=None,
        description="Source file to list (if None, lists around current location)"
    )
    line: Optional[int] = Field(
        default=None,
        description="Line number to center on",
        ge=1
    )
    count: int = Field(
        default=20,
        description="Number of lines to show",
        ge=1,
        le=500
    )
    function: Optional[str] = Field(
        default=None,
        description="Show source for a specific function"
    )


class SymbolLookupInput(BaseModel):
    """Input for looking up symbols."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    query: str = Field(
        ...,
        description="Symbol name or pattern to search for",
        min_length=1
    )
    query_type: str = Field(
        default="name",
        description="Type of lookup: 'name' (exact), 'regex' (pattern), 'address' (hex address), 'type' (type name)"
    )


class RegistersInput(BaseModel):
    """Input for viewing registers."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    breakpoint: str = Field(
        ...,
        description="Breakpoint location to stop at",
        min_length=1
    )
    register_set: str = Field(
        default="general",
        description="Register set to display: 'general', 'float', 'vector', 'all'"
    )
    specific_registers: Optional[List[str]] = Field(
        default=None,
        description="Specific register names to show (e.g., ['rax', 'rbx', 'rsp'])"
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Command-line arguments to pass to the program"
    )


class WatchpointInput(BaseModel):
    """Input for setting watchpoints."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    variable: str = Field(
        ...,
        description="Variable name or memory address to watch",
        min_length=1
    )
    watch_type: str = Field(
        default="write",
        description="Type of access to watch: 'write', 'read', 'read_write'"
    )
    condition: Optional[str] = Field(
        default=None,
        description="Conditional expression for the watchpoint"
    )


class RunProgramInput(BaseModel):
    """Input for running a program with debugging."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable to run",
        min_length=1
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Command-line arguments to pass to the program"
    )
    breakpoints: Optional[List[str]] = Field(
        default=None,
        description="List of breakpoint locations to set before running"
    )
    environment: Optional[Dict[str, str]] = Field(
        default=None,
        description="Environment variables to set"
    )
    stop_at_entry: bool = Field(
        default=True,
        description="Stop at the entry point (main function)"
    )
    working_dir: Optional[str] = Field(
        default=None,
        description="Working directory for the program"
    )


class AttachProcessInput(BaseModel):
    """Input for attaching to a running process."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    pid: Optional[int] = Field(
        default=None,
        description="Process ID to attach to",
        ge=1
    )
    name: Optional[str] = Field(
        default=None,
        description="Process name to attach to"
    )
    wait_for: bool = Field(
        default=False,
        description="Wait for the process to launch if using name"
    )
    
    @field_validator('name')
    @classmethod
    def validate_pid_or_name(cls, v, info):
        if v is None and info.data.get('pid') is None:
            raise ValueError("Either 'pid' or 'name' must be provided")
        return v


class ThreadsInput(BaseModel):
    """Input for examining threads."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    breakpoint: Optional[str] = Field(
        default=None,
        description="Breakpoint location to stop at"
    )
    core_file: Optional[str] = Field(
        default=None,
        description="Path to core dump file"
    )
    show_backtrace: bool = Field(
        default=False,
        description="Show backtrace for each thread"
    )


class ImageListInput(BaseModel):
    """Input for listing loaded images/modules."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    executable: str = Field(
        ...,
        description="Path to the executable",
        min_length=1
    )
    filter_pattern: Optional[str] = Field(
        default=None,
        description="Filter images by name pattern"
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _format_output(data: Dict[str, Any], format_type: ResponseFormat) -> str:
    """Format output based on requested format."""
    if format_type == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    
    # Markdown format
    lines = []
    
    if data.get("success"):
        if data.get("output"):
            lines.append("```")
            lines.append(data["output"].strip())
            lines.append("```")
    else:
        lines.append("**Error:**")
        lines.append(f"```\n{data.get('error', 'Unknown error')}\n```")
    
    return "\n".join(lines)


def _parse_backtrace(output: str) -> List[Dict[str, Any]]:
    """Parse LLDB backtrace output into structured data."""
    frames = []
    frame_pattern = re.compile(
        r'frame #(\d+): (0x[0-9a-fA-F]+) (.+?)(?:`(.+?))?(?:\s+\+\s+(\d+))?(?:\s+at\s+(.+):(\d+))?'
    )
    
    for line in output.split('\n'):
        match = frame_pattern.search(line)
        if match:
            frames.append({
                "frame_number": int(match.group(1)),
                "address": match.group(2),
                "module": match.group(3).strip() if match.group(3) else None,
                "function": match.group(4).strip() if match.group(4) else None,
                "offset": int(match.group(5)) if match.group(5) else None,
                "file": match.group(6) if match.group(6) else None,
                "line": int(match.group(7)) if match.group(7) else None
            })
    
    return frames


# =============================================================================
# MCP Tools
# =============================================================================

@mcp.tool(
    name="lldb_run_command",
    annotations={
        "title": "Run LLDB Command",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def lldb_run_command(params: RunCommandInput) -> str:
    """Execute an arbitrary LLDB command and return the output.
    
    This is a flexible tool for running any LLDB command. Use this when
    other specialized tools don't cover your specific need.
    
    Common commands:
    - 'help' - Show help for commands
    - 'version' - Show LLDB version
    - 'settings list' - Show all settings
    - 'type summary list' - List type summaries
    - 'platform list' - List available platforms
    
    Args:
        params: RunCommandInput containing the command and optional target
    
    Returns:
        str: Command output or error message
    """
    result = _run_lldb_command(
        params.command,
        target=params.target
    )
    
    if result["success"]:
        return f"```\n{result['output']}\n```"
    else:
        return f"**Error:** {result['error']}\n\n**Output:**\n```\n{result['output']}\n```"


@mcp.tool(
    name="lldb_analyze_crash",
    annotations={
        "title": "Analyze Crash Dump",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_analyze_crash(params: AnalyzeCrashInput) -> str:
    """Analyze a crashed program or core dump to determine the cause.
    
    This tool loads a core dump or crashed executable and provides:
    - Backtrace showing the crash location
    - Register state at crash time
    - Local variables in the crash frame
    - Loaded modules information
    
    Args:
        params: AnalyzeCrashInput with executable path and optional core file
    
    Returns:
        str: Crash analysis including backtrace, registers, and variables
    """
    commands = []
    
    if params.core_file:
        commands.append(f"target create {params.executable} --core {params.core_file}")
    else:
        commands.append(f"target create {params.executable}")
    
    commands.extend([
        "bt all",
        "register read",
        "frame variable",
        "image list"
    ])
    
    result = _run_lldb_script(commands)
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": result["success"],
            "executable": params.executable,
            "core_file": params.core_file,
            "output": result["output"],
            "error": result.get("error")
        }, indent=2)
    
    # Markdown format
    lines = [
        f"# Crash Analysis: {Path(params.executable).name}",
        ""
    ]
    
    if params.core_file:
        lines.append(f"**Core file:** {params.core_file}")
        lines.append("")
    
    if result["success"]:
        lines.append("## Analysis Output")
        lines.append("```")
        lines.append(result["output"].strip())
        lines.append("```")
    else:
        lines.append("## Error")
        lines.append(f"```\n{result.get('error', 'Unknown error')}\n```")
    
    return "\n".join(lines)


@mcp.tool(
    name="lldb_set_breakpoint",
    annotations={
        "title": "Set Breakpoint",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def lldb_set_breakpoint(params: SetBreakpointInput) -> str:
    """Set a breakpoint in a program.
    
    Breakpoints can be set by:
    - Function name: 'main', 'MyClass::method'
    - File and line: 'main.cpp:42'
    - Address: '0x400500'
    - Regex: Use 'breakpoint set -r pattern'
    
    Args:
        params: SetBreakpointInput with location and optional condition
    
    Returns:
        str: Confirmation of breakpoint creation with details
    """
    commands = [f"target create {params.executable}"]
    
    # Determine breakpoint type from location format
    if ':' in params.location and not params.location.startswith('0x'):
        # File:line format
        parts = params.location.rsplit(':', 1)
        bp_cmd = f"breakpoint set --file {parts[0]} --line {parts[1]}"
    elif params.location.startswith('0x'):
        # Address
        bp_cmd = f"breakpoint set --address {params.location}"
    else:
        # Function name
        bp_cmd = f"breakpoint set --name {params.location}"
    
    if params.condition:
        bp_cmd += f" --condition '{params.condition}'"
    
    commands.append(bp_cmd)
    commands.append("breakpoint list")
    
    result = _run_lldb_script(commands)
    
    if result["success"]:
        return f"**Breakpoint set successfully**\n\n```\n{result['output']}\n```"
    else:
        return f"**Error setting breakpoint:** {result.get('error')}\n\n```\n{result['output']}\n```"


@mcp.tool(
    name="lldb_examine_variables",
    annotations={
        "title": "Examine Variables",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_examine_variables(params: ExamineVariablesInput) -> str:
    """Examine local variables and arguments at a breakpoint.
    
    Runs the program until the specified breakpoint, then displays
    the values of local variables and function arguments.
    
    Args:
        params: ExamineVariablesInput with executable, breakpoint, and optional variable names
    
    Returns:
        str: Variable values at the breakpoint
    """
    commands = [
        f"target create {params.executable}",
        f"breakpoint set --name {params.breakpoint}",
        "run" + (" " + " ".join(params.args) if params.args else "")
    ]
    
    if params.variables:
        for var in params.variables:
            commands.append(f"frame variable {var}")
    else:
        commands.append("frame variable")
    
    commands.append("quit")
    
    result = _run_lldb_script(commands)
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "success": result["success"],
            "breakpoint": params.breakpoint,
            "output": result["output"],
            "error": result.get("error")
        }, indent=2)
    
    lines = [
        f"## Variables at `{params.breakpoint}`",
        "",
        "```",
        result["output"].strip() if result["success"] else result.get("error", "Unknown error"),
        "```"
    ]
    
    return "\n".join(lines)


@mcp.tool(
    name="lldb_disassemble",
    annotations={
        "title": "Disassemble Code",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_disassemble(params: DisassembleInput) -> str:
    """Disassemble machine code to view assembly instructions.
    
    Can disassemble:
    - A named function: 'main', 'MyClass::method'
    - An address range: '0x1000-0x1100' or '0x1000 0x1100'
    - Current frame (when stopped at breakpoint)
    
    Options:
    - show_bytes: Include raw opcode bytes
    - mixed: Interleave source code with assembly
    
    Args:
        params: DisassembleInput with target and display options
    
    Returns:
        str: Assembly listing
    """
    commands = [f"target create {params.executable}"]
    
    dis_cmd = "disassemble"
    
    if '-' in params.target and params.target.startswith('0x'):
        # Address range
        parts = params.target.split('-')
        dis_cmd += f" --start-address {parts[0]} --end-address {parts[1]}"
    elif params.target.startswith('0x'):
        # Single address
        dis_cmd += f" --start-address {params.target} --count 50"
    elif params.target.lower() == 'current':
        dis_cmd += " --frame"
    else:
        # Function name
        dis_cmd += f" --name {params.target}"
    
    if params.show_bytes:
        dis_cmd += " --bytes"
    if params.mixed:
        dis_cmd += " --mixed"
    
    commands.append(dis_cmd)
    
    result = _run_lldb_script(commands)
    
    return f"## Disassembly: `{params.target}`\n\n```asm\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_read_memory",
    annotations={
        "title": "Read Memory",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_read_memory(params: ReadMemoryInput) -> str:
    """Read and display memory contents at a specified address.
    
    Memory can be displayed in various formats:
    - 'x': Hexadecimal (default)
    - 'b': Binary
    - 'd': Decimal
    - 's': String (null-terminated)
    - 'i': Instructions (disassembly)
    
    Args:
        params: ReadMemoryInput with address, count, and format
    
    Returns:
        str: Memory contents in requested format
    """
    commands = [f"target create {params.executable}"]
    
    if params.breakpoint:
        commands.extend([
            f"breakpoint set --name {params.breakpoint}",
            "run",
        ])
    
    mem_cmd = f"memory read --format {params.format} --count {params.count} {params.address}"
    commands.append(mem_cmd)
    
    if params.breakpoint:
        commands.append("quit")
    
    result = _run_lldb_script(commands)
    
    return f"## Memory at `{params.address}`\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_evaluate",
    annotations={
        "title": "Evaluate Expression",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_evaluate(params: EvaluateExpressionInput) -> str:
    """Evaluate a C/C++ expression in the debugger context.
    
    Expressions can include:
    - Variable access: 'my_var', 'ptr->member'
    - Array indexing: 'array[5]'
    - Function calls: 'strlen(str)'
    - Casts: '(int*)ptr'
    - Arithmetic: 'x + y * 2'
    - sizeof: 'sizeof(MyStruct)'
    
    Args:
        params: EvaluateExpressionInput with expression and context
    
    Returns:
        str: Expression result with type information
    """
    commands = [
        f"target create {params.executable}",
        f"breakpoint set --name {params.breakpoint}",
        "run" + (" " + " ".join(params.args) if params.args else ""),
        f"expression {params.expression}",
        "quit"
    ]
    
    result = _run_lldb_script(commands)
    
    return f"## Expression: `{params.expression}`\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_backtrace",
    annotations={
        "title": "Get Backtrace",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_backtrace(params: BacktraceInput) -> str:
    """Get a stack backtrace showing the call chain.
    
    The backtrace shows:
    - Frame numbers (0 is current frame)
    - Function names and addresses
    - Source file and line numbers (if available)
    - Module/library names
    
    Args:
        params: BacktraceInput with executable and stopping point
    
    Returns:
        str: Stack backtrace with frame information
    """
    commands = []
    
    if params.core_file:
        commands.append(f"target create {params.executable} --core {params.core_file}")
    else:
        commands.append(f"target create {params.executable}")
        if params.breakpoint:
            commands.append(f"breakpoint set --name {params.breakpoint}")
            commands.append("run" + (" " + " ".join(params.args) if params.args else ""))
    
    bt_cmd = "thread backtrace"
    if params.all_threads:
        bt_cmd = "thread backtrace all"
    bt_cmd += f" -c {params.limit}"
    
    commands.append(bt_cmd)
    
    if not params.core_file:
        commands.append("quit")
    
    result = _run_lldb_script(commands)
    
    if params.response_format == ResponseFormat.JSON:
        frames = _parse_backtrace(result["output"])
        return json.dumps({
            "success": result["success"],
            "frames": frames,
            "raw_output": result["output"]
        }, indent=2)
    
    lines = [
        "## Stack Backtrace",
        "",
        "```",
        result["output"].strip(),
        "```"
    ]
    
    return "\n".join(lines)


@mcp.tool(
    name="lldb_source",
    annotations={
        "title": "List Source Code",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_source(params: ListSourceInput) -> str:
    """List source code for a file, function, or current location.
    
    Can display:
    - Source around a specific line
    - Source for a named function
    - Source at the current debug position
    
    Args:
        params: ListSourceInput specifying what source to show
    
    Returns:
        str: Source code listing with line numbers
    """
    commands = [f"target create {params.executable}"]
    
    if params.function:
        commands.append(f"source list --name {params.function} --count {params.count}")
    elif params.file and params.line:
        commands.append(f"source list --file {params.file} --line {params.line} --count {params.count}")
    elif params.file:
        commands.append(f"source list --file {params.file} --count {params.count}")
    else:
        commands.append(f"source list --count {params.count}")
    
    result = _run_lldb_script(commands)
    
    title = params.function or params.file or "Source"
    return f"## {title}\n\n```cpp\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_symbols",
    annotations={
        "title": "Lookup Symbols",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_symbols(params: SymbolLookupInput) -> str:
    """Look up symbols (functions, variables, types) in an executable.
    
    Search types:
    - 'name': Exact symbol name lookup
    - 'regex': Regular expression pattern matching
    - 'address': Find symbol at a specific address
    - 'type': Look up a type definition
    
    Args:
        params: SymbolLookupInput with query and search type
    
    Returns:
        str: Symbol information including address and source location
    """
    commands = [f"target create {params.executable}"]
    
    if params.query_type == "name":
        commands.append(f"image lookup --name {params.query}")
    elif params.query_type == "regex":
        commands.append(f"image lookup --regex --name {params.query}")
    elif params.query_type == "address":
        commands.append(f"image lookup --address {params.query}")
    elif params.query_type == "type":
        commands.append(f"image lookup --type {params.query}")
    else:
        commands.append(f"image lookup --name {params.query}")
    
    result = _run_lldb_script(commands)
    
    return f"## Symbol Lookup: `{params.query}`\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_registers",
    annotations={
        "title": "View Registers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_registers(params: RegistersInput) -> str:
    """View CPU register values at a breakpoint.
    
    Register sets:
    - 'general': General purpose registers (rax, rbx, rsp, etc.)
    - 'float': Floating point registers
    - 'vector': SIMD/vector registers (xmm, ymm)
    - 'all': All register sets
    
    Args:
        params: RegistersInput with breakpoint and register selection
    
    Returns:
        str: Register values in hexadecimal format
    """
    commands = [
        f"target create {params.executable}",
        f"breakpoint set --name {params.breakpoint}",
        "run" + (" " + " ".join(params.args) if params.args else "")
    ]
    
    if params.specific_registers:
        reg_cmd = f"register read {' '.join(params.specific_registers)}"
    elif params.register_set == "all":
        reg_cmd = "register read --all"
    elif params.register_set == "float":
        reg_cmd = "register read --set 1"  # Usually FPU
    elif params.register_set == "vector":
        reg_cmd = "register read --set 2"  # Usually SSE/AVX
    else:
        reg_cmd = "register read"
    
    commands.append(reg_cmd)
    commands.append("quit")
    
    result = _run_lldb_script(commands)
    
    return f"## Registers at `{params.breakpoint}`\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_watchpoint",
    annotations={
        "title": "Set Watchpoint",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def lldb_watchpoint(params: WatchpointInput) -> str:
    """Set a watchpoint to break when a variable is accessed.
    
    Watch types:
    - 'write': Break when value is written (modified)
    - 'read': Break when value is read
    - 'read_write': Break on any access
    
    Args:
        params: WatchpointInput with variable and access type
    
    Returns:
        str: Confirmation of watchpoint creation
    """
    commands = [f"target create {params.executable}"]
    
    wp_cmd = f"watchpoint set variable {params.variable}"
    
    if params.watch_type == "read":
        wp_cmd += " --watch read"
    elif params.watch_type == "read_write":
        wp_cmd += " --watch read_write"
    # Default is write
    
    commands.append(wp_cmd)
    
    if params.condition:
        commands.append(f"watchpoint modify --condition '{params.condition}'")
    
    commands.append("watchpoint list")
    
    result = _run_lldb_script(commands)
    
    return f"## Watchpoint on `{params.variable}`\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_run",
    annotations={
        "title": "Run Program",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def lldb_run(params: RunProgramInput) -> str:
    """Run a program under the debugger with optional breakpoints.
    
    This tool:
    1. Loads the executable
    2. Sets any specified breakpoints
    3. Runs the program (optionally stopping at entry)
    4. Returns the state when stopped
    
    Args:
        params: RunProgramInput with executable, args, and breakpoints
    
    Returns:
        str: Program state after stopping (backtrace, variables)
    """
    commands = [f"target create {params.executable}"]
    
    # Set environment variables
    if params.environment:
        for key, value in params.environment.items():
            commands.append(f"settings set target.env-vars {key}={value}")
    
    # Set breakpoints
    if params.breakpoints:
        for bp in params.breakpoints:
            if ':' in bp and not bp.startswith('0x'):
                parts = bp.rsplit(':', 1)
                commands.append(f"breakpoint set --file {parts[0]} --line {parts[1]}")
            else:
                commands.append(f"breakpoint set --name {bp}")
    elif params.stop_at_entry:
        commands.append("breakpoint set --name main")
    
    # Prepare run command
    run_cmd = "run"
    if params.args:
        run_cmd += " " + " ".join(params.args)
    
    commands.extend([
        run_cmd,
        "thread backtrace",
        "frame variable",
        "quit"
    ])
    
    result = _run_lldb_script(commands, working_dir=params.working_dir)
    
    return f"## Program Run: `{Path(params.executable).name}`\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_threads",
    annotations={
        "title": "Examine Threads",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_threads(params: ThreadsInput) -> str:
    """List all threads and their current state.
    
    Shows:
    - Thread IDs and names
    - Current execution point for each thread
    - Stop reason (if stopped)
    - Optionally: backtrace for each thread
    
    Args:
        params: ThreadsInput with executable and optional core file
    
    Returns:
        str: Thread listing with state information
    """
    commands = []
    
    if params.core_file:
        commands.append(f"target create {params.executable} --core {params.core_file}")
    else:
        commands.append(f"target create {params.executable}")
        if params.breakpoint:
            commands.append(f"breakpoint set --name {params.breakpoint}")
            commands.append("run")
    
    commands.append("thread list")
    
    if params.show_backtrace:
        commands.append("thread backtrace all")
    
    if not params.core_file:
        commands.append("quit")
    
    result = _run_lldb_script(commands)
    
    return f"## Threads\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_images",
    annotations={
        "title": "List Loaded Images",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_images(params: ImageListInput) -> str:
    """List loaded executable images and shared libraries.
    
    Shows:
    - Main executable
    - Shared libraries (.so, .dylib, .dll)
    - Load addresses
    - File paths
    
    Args:
        params: ImageListInput with executable and optional filter
    
    Returns:
        str: List of loaded images with addresses
    """
    commands = [
        f"target create {params.executable}",
        "image list"
    ]
    
    result = _run_lldb_script(commands)
    
    output = result['output']
    
    # Apply filter if specified
    if params.filter_pattern and result["success"]:
        filtered_lines = [
            line for line in output.split('\n')
            if params.filter_pattern.lower() in line.lower()
        ]
        output = '\n'.join(filtered_lines) if filtered_lines else "No images matching filter"
    
    return f"## Loaded Images\n\n```\n{output.strip()}\n```"


@mcp.tool(
    name="lldb_help",
    annotations={
        "title": "LLDB Help",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_help(topic: str = "") -> str:
    """Get help on LLDB commands and usage.
    
    Provides:
    - General LLDB usage (empty topic)
    - Help on specific commands (e.g., 'breakpoint', 'memory')
    - Command syntax and options
    
    Args:
        topic: Command or topic to get help on (empty for general help)
    
    Returns:
        str: Help text for the specified topic
    """
    cmd = "help"
    if topic:
        cmd += f" {topic}"
    
    result = _run_lldb_command(cmd)
    
    return f"## LLDB Help{': ' + topic if topic else ''}\n\n```\n{result['output'].strip()}\n```"


@mcp.tool(
    name="lldb_version",
    annotations={
        "title": "LLDB Version",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def lldb_version() -> str:
    """Get LLDB version information.
    
    Returns:
        str: LLDB version and build information
    """
    result = _run_lldb_command("version")
    
    return f"## LLDB Version\n\n```\n{result['output'].strip()}\n```"


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    mcp.run()
