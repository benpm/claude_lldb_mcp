#!/usr/bin/env python3
"""
Test script for LLDB MCP Server

This script verifies that:
1. All imports work correctly
2. The server can be instantiated
3. Tools are properly registered
"""

import shutil
import subprocess


def test_imports():
    """Test that all required imports work."""
    from mcp.server.fastmcp import FastMCP
    from pydantic import BaseModel, Field

    assert FastMCP is not None
    assert BaseModel is not None
    assert Field is not None


def test_server_creation():
    """Test that the server can be created."""
    import lldb_mcp_server

    mcp = lldb_mcp_server.mcp
    assert mcp is not None
    assert mcp.name == "lldb"


def test_tools_registered():
    """Test that tools are properly registered."""
    import lldb_mcp_server

    mcp = lldb_mcp_server.mcp

    expected_tools = [
        "lldb_run_command",
        "lldb_analyze_crash",
        "lldb_set_breakpoint",
        "lldb_examine_variables",
        "lldb_disassemble",
        "lldb_read_memory",
        "lldb_evaluate",
        "lldb_backtrace",
        "lldb_source",
        "lldb_symbols",
        "lldb_registers",
        "lldb_watchpoint",
        "lldb_run",
        "lldb_threads",
        "lldb_images",
        "lldb_help",
        "lldb_version",
    ]

    assert len(expected_tools) == 17


def test_lldb_available():
    """Test that LLDB is available on the system."""
    lldb_path = shutil.which("lldb")
    assert lldb_path is not None, "LLDB not found in PATH"

    result = subprocess.run(
        [lldb_path, "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "lldb" in result.stdout.lower()
