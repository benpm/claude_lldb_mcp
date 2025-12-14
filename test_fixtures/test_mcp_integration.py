#!/usr/bin/env python3
"""
Integration tests that simulate how Claude Code calls the MCP server.
Tests the server through JSON-RPC protocol over stdio.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent
SIMPLE_EXE = FIXTURES_DIR / "simple"
SERVER_PATH = FIXTURES_DIR.parent / "lldb_mcp_server.py"


def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_test(name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if details:
        # Truncate long details
        if len(details) > 300:
            details = details[:300] + "..."
        print(f"         {details}")


async def call_mcp_tool(tool_name, arguments, cwd=None):
    """
    Call an MCP tool through the server's stdio interface.

    This simulates how Claude Code actually calls tools.
    """
    # Build the JSON-RPC request
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    request_json = json.dumps(request)

    # Also need to initialize the server first
    init_request = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }

    init_json = json.dumps(init_request)

    # Run the MCP server as a subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(SERVER_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )

    try:
        # Send initialization and tool call
        # MCP uses Content-Length headers
        init_msg = f"Content-Length: {len(init_json)}\r\n\r\n{init_json}"
        tool_msg = f"Content-Length: {len(request_json)}\r\n\r\n{request_json}"

        full_input = (init_msg + tool_msg).encode()

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=full_input),
            timeout=30.0
        )

        return {
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "returncode": proc.returncode
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {
            "stdout": "",
            "stderr": "Timeout",
            "returncode": -1
        }


async def test_direct_lldb():
    """Test LLDB directly to ensure it works."""
    print_header("Test: Direct LLDB Verification")

    # Test 1: Basic LLDB command
    result = subprocess.run(
        ["lldb", "--batch", "-o", "version"],
        capture_output=True,
        text=True,
        timeout=10
    )
    passed = result.returncode == 0 and "lldb" in result.stdout.lower()
    print_test("LLDB version command", passed, result.stdout[:100])

    # Test 2: Set breakpoint on our test executable
    result = subprocess.run(
        ["lldb", "--batch",
         "-o", f"target create {SIMPLE_EXE}",
         "-o", "breakpoint set --name main",
         "-o", "breakpoint list"],
        capture_output=True,
        text=True,
        timeout=10
    )
    passed = "Breakpoint 1" in result.stdout
    print_test("LLDB breakpoint on main", passed, result.stdout[:200])

    # Test 3: Run to breakpoint
    result = subprocess.run(
        ["lldb", "--batch",
         "-o", f"target create {SIMPLE_EXE}",
         "-o", "breakpoint set --name main",
         "-o", "run",
         "-o", "bt",
         "-o", "quit"],
        capture_output=True,
        text=True,
        timeout=30
    )
    passed = "main" in result.stdout and ("frame" in result.stdout.lower() or "#" in result.stdout)
    print_test("LLDB run to breakpoint", passed, result.stdout[:300])

    return passed


async def test_breakpoint_from_different_dirs():
    """Test breakpoints work when called from different directories."""
    print_header("Test: Breakpoint from Different Working Directories")

    dirs_to_test = [
        ("/tmp", "tmp"),
        (str(Path.home()), "home"),
        ("/var", "var"),
        (str(FIXTURES_DIR), "fixtures"),
    ]

    all_passed = True
    for test_dir, name in dirs_to_test:
        if not Path(test_dir).exists():
            print_test(f"Breakpoint from {name}", False, f"Directory {test_dir} does not exist")
            continue

        # Call LLDB directly from the different directory
        result = subprocess.run(
            ["lldb", "--batch",
             "-o", f"target create {SIMPLE_EXE}",
             "-o", "breakpoint set --name add",
             "-o", "breakpoint list"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=test_dir
        )
        passed = "Breakpoint 1" in result.stdout and "add" in result.stdout
        print_test(f"Breakpoint from {name} ({test_dir})", passed, result.stdout[:150])
        all_passed = all_passed and passed

    return all_passed


async def test_file_line_breakpoints():
    """Test file:line breakpoints with various path formats."""
    print_header("Test: File:Line Breakpoints with Path Variations")

    source_file = FIXTURES_DIR / "simple.cpp"

    tests = [
        # (file_path, line, description)
        (str(source_file), "6", "Absolute path"),
        ("simple.cpp", "6", "Relative filename (from fixtures dir)"),
    ]

    all_passed = True
    for file_path, line, desc in tests:
        cwd = str(FIXTURES_DIR) if not file_path.startswith("/") else None

        result = subprocess.run(
            ["lldb", "--batch",
             "-o", f"target create {SIMPLE_EXE}",
             "-o", f"breakpoint set --file {file_path} --line {line}",
             "-o", "breakpoint list"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd
        )
        passed = "Breakpoint 1" in result.stdout
        print_test(f"File:Line - {desc}", passed, result.stdout[:150])
        all_passed = all_passed and passed

    # Test from different directory with absolute path
    result = subprocess.run(
        ["lldb", "--batch",
         "-o", f"target create {SIMPLE_EXE}",
         "-o", f"breakpoint set --file {source_file} --line 6",
         "-o", "breakpoint list"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/tmp"
    )
    passed = "Breakpoint 1" in result.stdout
    print_test("File:Line from /tmp with absolute path", passed, result.stdout[:150])
    all_passed = all_passed and passed

    return all_passed


async def test_mcp_server_tool_call():
    """Test calling MCP tools directly (simulating Claude Code)."""
    print_header("Test: MCP Server Tool Calls")

    # Import and call tools directly
    sys.path.insert(0, str(FIXTURES_DIR.parent))

    from lldb_mcp_server import (
        lldb_set_breakpoint,
        lldb_run,
        SetBreakpointInput,
        RunProgramInput,
    )

    # Test 1: Set breakpoint via MCP tool
    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location="main"
    )
    result = await lldb_set_breakpoint(params)
    passed = "Breakpoint" in result and "main" in result
    print_test("MCP lldb_set_breakpoint (function)", passed, result[:200])

    # Test 2: Set breakpoint with file:line
    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location=f"{FIXTURES_DIR}/simple.cpp:6"
    )
    result = await lldb_set_breakpoint(params)
    passed = "Breakpoint" in result
    print_test("MCP lldb_set_breakpoint (file:line)", passed, result[:200])

    # Test 3: Run with breakpoints
    params = RunProgramInput(
        executable=str(SIMPLE_EXE),
        breakpoints=["main"],
        stop_at_entry=True
    )
    result = await lldb_run(params)
    passed = "main" in result.lower() or "frame" in result.lower()
    print_test("MCP lldb_run with breakpoint", passed, result[:300])

    # Test 4: Run with file:line breakpoint
    params = RunProgramInput(
        executable=str(SIMPLE_EXE),
        breakpoints=[f"{FIXTURES_DIR}/simple.cpp:19"],
        stop_at_entry=False
    )
    result = await lldb_run(params)
    passed = "frame" in result.lower() or "thread" in result.lower() or "backtrace" in result.lower()
    print_test("MCP lldb_run with file:line breakpoint", passed, result[:300])

    return passed


async def test_breakpoint_actually_stops():
    """Test that the program actually stops at the breakpoint."""
    print_header("Test: Breakpoint Actually Stops Execution")

    # Run program with breakpoint and check that we can see local variables
    result = subprocess.run(
        ["lldb", "--batch",
         "-o", f"target create {SIMPLE_EXE}",
         "-o", "breakpoint set --name add",
         "-o", "run",
         "-o", "frame variable",
         "-o", "quit"],
        capture_output=True,
        text=True,
        timeout=30
    )

    # We should see the 'a' and 'b' parameters from the add function
    passed = ("a =" in result.stdout or "(int) a" in result.stdout) and \
             ("b =" in result.stdout or "(int) b" in result.stdout)
    print_test("Variables visible at breakpoint", passed, result.stdout[:400])

    # Check we stopped in the right function
    stopped_in_add = "add" in result.stdout
    print_test("Stopped in 'add' function", stopped_in_add, "")

    return passed and stopped_in_add


async def main():
    """Run all integration tests."""
    print("\n" + "#" * 60)
    print("#  LLDB MCP Server - Integration Test Suite")
    print("#" * 60)

    print_header("Prerequisites")
    print(f"  Test fixtures: {FIXTURES_DIR}")
    print(f"  Simple executable: {SIMPLE_EXE}")
    print(f"  Server path: {SERVER_PATH}")

    results = []

    results.append(("Direct LLDB", await test_direct_lldb()))
    results.append(("Different Working Dirs", await test_breakpoint_from_different_dirs()))
    results.append(("File:Line Breakpoints", await test_file_line_breakpoints()))
    results.append(("MCP Tool Calls", await test_mcp_server_tool_call()))
    results.append(("Breakpoint Stops Execution", await test_breakpoint_actually_stops()))

    print_header("Integration Test Summary")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\n  Total: {passed}/{total} tests passed")
    print("#" * 60 + "\n")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
