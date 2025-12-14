#!/usr/bin/env python3
"""
Comprehensive tests for LLDB MCP server breakpoint functionality.
Tests breakpoints from various working directories and with different location formats.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# Add parent dir to path so we can import the server module
sys.path.insert(0, str(Path(__file__).parent.parent))

from lldb_mcp_server import (
    lldb_set_breakpoint,
    lldb_run,
    lldb_examine_variables,
    lldb_backtrace,
    lldb_run_command,
    SetBreakpointInput,
    RunProgramInput,
    ExamineVariablesInput,
    BacktraceInput,
    RunCommandInput,
    _run_lldb_script,
    _run_lldb_command,
)

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent
SIMPLE_EXE = FIXTURES_DIR / "simple"
MULTIFILE_EXE = FIXTURES_DIR / "multifile"
VARIABLES_EXE = FIXTURES_DIR / "variables"


def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_test(name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if details and not passed:
        print(f"         Details: {details[:200]}")


async def test_function_breakpoint():
    """Test setting breakpoint by function name."""
    print_header("Test: Function Name Breakpoint")

    # Test 1: Breakpoint on 'add' function
    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location="add"
    )
    result = await lldb_set_breakpoint(params)
    has_breakpoint = "Breakpoint" in result and ("add" in result or "1 location" in result.lower())
    print_test("Set breakpoint on 'add' function", has_breakpoint, result)

    # Test 2: Breakpoint on 'main' function
    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location="main"
    )
    result = await lldb_set_breakpoint(params)
    has_breakpoint = "Breakpoint" in result and ("main" in result or "1 location" in result.lower())
    print_test("Set breakpoint on 'main' function", has_breakpoint, result)

    return has_breakpoint


async def test_file_line_breakpoint():
    """Test setting breakpoint by file:line."""
    print_header("Test: File:Line Breakpoint")

    # Test with absolute path
    abs_path = str(FIXTURES_DIR / "simple.cpp")
    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location=f"{abs_path}:6"  # Line 6 in add() function
    )
    result = await lldb_set_breakpoint(params)
    has_breakpoint = "Breakpoint" in result
    print_test("Set breakpoint with absolute file:line", has_breakpoint, result)

    # Test with relative filename
    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location="simple.cpp:16",  # Line 16 in main()
        working_dir=str(FIXTURES_DIR)
    )
    result = await lldb_set_breakpoint(params)
    has_breakpoint = "Breakpoint" in result
    print_test("Set breakpoint with relative file:line", has_breakpoint, result)

    # Test multifile - breakpoint in helper file
    abs_helper = str(FIXTURES_DIR / "multifile_helper.cpp")
    params = SetBreakpointInput(
        executable=str(MULTIFILE_EXE),
        location=f"{abs_helper}:5"  # Line 5 in helper_double()
    )
    result = await lldb_set_breakpoint(params)
    has_breakpoint = "Breakpoint" in result
    print_test("Set breakpoint in helper file", has_breakpoint, result)

    return has_breakpoint


async def test_breakpoint_from_different_dirs():
    """Test breakpoints work from different working directories."""
    print_header("Test: Breakpoints from Different Working Directories")

    original_cwd = os.getcwd()

    try:
        # Test 1: From /tmp
        os.chdir("/tmp")
        params = SetBreakpointInput(
            executable=str(SIMPLE_EXE),
            location="main"
        )
        result = await lldb_set_breakpoint(params)
        passed_tmp = "Breakpoint" in result and "main" in result
        print_test("Breakpoint from /tmp", passed_tmp, result)

        # Test 2: From home directory
        os.chdir(os.path.expanduser("~"))
        params = SetBreakpointInput(
            executable=str(SIMPLE_EXE),
            location="add"
        )
        result = await lldb_set_breakpoint(params)
        passed_home = "Breakpoint" in result
        print_test("Breakpoint from home dir", passed_home, result)

        # Test 3: File:line from different directory
        os.chdir("/tmp")
        abs_path = str(FIXTURES_DIR / "simple.cpp")
        params = SetBreakpointInput(
            executable=str(SIMPLE_EXE),
            location=f"{abs_path}:6"
        )
        result = await lldb_set_breakpoint(params)
        passed_fileline = "Breakpoint" in result
        print_test("File:line breakpoint from /tmp", passed_fileline, result)

    finally:
        os.chdir(original_cwd)

    return passed_tmp and passed_home and passed_fileline


async def test_run_with_breakpoints():
    """Test running program with breakpoints."""
    print_header("Test: Run Program with Breakpoints")

    # Test 1: Run with function breakpoint
    params = RunProgramInput(
        executable=str(SIMPLE_EXE),
        breakpoints=["main"],
        stop_at_entry=True
    )
    result = await lldb_run(params)
    stopped_at_main = "main" in result.lower() or "frame" in result.lower()
    print_test("Run with breakpoint at main", stopped_at_main, result)

    # Test 2: Run with file:line breakpoint
    abs_path = str(FIXTURES_DIR / "simple.cpp")
    params = RunProgramInput(
        executable=str(SIMPLE_EXE),
        breakpoints=[f"{abs_path}:19"],  # Line with add() call
        stop_at_entry=False
    )
    result = await lldb_run(params)
    has_output = "frame" in result.lower() or "backtrace" in result.lower() or "thread" in result.lower()
    print_test("Run with file:line breakpoint", has_output, result)

    return stopped_at_main


async def test_examine_variables_at_breakpoint():
    """Test examining variables at a breakpoint."""
    print_header("Test: Examine Variables at Breakpoint")

    params = ExamineVariablesInput(
        executable=str(SIMPLE_EXE),
        breakpoint="main"
    )
    result = await lldb_examine_variables(params)
    has_vars = "x" in result or "y" in result or "argc" in result or "frame variable" in result.lower()
    print_test("Examine variables at main", has_vars, result)

    return has_vars


async def test_backtrace_at_breakpoint():
    """Test getting backtrace at a breakpoint."""
    print_header("Test: Backtrace at Breakpoint")

    params = BacktraceInput(
        executable=str(SIMPLE_EXE),
        breakpoint="add"
    )
    result = await lldb_backtrace(params)
    has_backtrace = "frame" in result.lower() or "add" in result or "#0" in result
    print_test("Backtrace at 'add' function", has_backtrace, result)

    return has_backtrace


async def test_raw_lldb_breakpoint():
    """Test raw LLDB commands to diagnose issues."""
    print_header("Test: Raw LLDB Breakpoint Commands (Diagnostic)")

    # Test direct LLDB command
    commands = [
        f"target create {SIMPLE_EXE}",
        "breakpoint set --name main",
        "breakpoint list",
    ]
    result = _run_lldb_script(commands)
    print(f"  Raw LLDB output:\n{result['output'][:500]}")

    has_breakpoint = "Breakpoint 1" in result["output"]
    print_test("Raw LLDB breakpoint set --name main", has_breakpoint, result["output"])

    # Test file:line with raw LLDB
    abs_path = str(FIXTURES_DIR / "simple.cpp")
    commands = [
        f"target create {SIMPLE_EXE}",
        f"breakpoint set --file {abs_path} --line 6",
        "breakpoint list",
    ]
    result = _run_lldb_script(commands)
    print(f"  Raw LLDB file:line output:\n{result['output'][:500]}")

    has_breakpoint = "Breakpoint 1" in result["output"] or "1 location" in result["output"]
    print_test("Raw LLDB breakpoint set --file --line", has_breakpoint, result["output"])

    return has_breakpoint


async def test_conditional_breakpoint():
    """Test conditional breakpoint."""
    print_header("Test: Conditional Breakpoint")

    params = SetBreakpointInput(
        executable=str(SIMPLE_EXE),
        location="add",
        condition="a > 5"
    )
    result = await lldb_set_breakpoint(params)
    has_breakpoint = "Breakpoint" in result
    has_condition = "condition" in result.lower() or "a > 5" in result
    print_test("Set conditional breakpoint", has_breakpoint, result)
    print_test("Condition appears in output", has_condition, result)

    return has_breakpoint


async def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("#  LLDB MCP Server - Breakpoint Test Suite")
    print("#" * 60)

    # Check prerequisites
    print_header("Prerequisites Check")
    print(f"  Test fixtures dir: {FIXTURES_DIR}")
    print(f"  Simple executable: {SIMPLE_EXE} (exists: {SIMPLE_EXE.exists()})")
    print(f"  Multifile executable: {MULTIFILE_EXE} (exists: {MULTIFILE_EXE.exists()})")
    print(f"  Variables executable: {VARIABLES_EXE} (exists: {VARIABLES_EXE.exists()})")

    # Check LLDB
    lldb_check = subprocess.run(["which", "lldb"], capture_output=True, text=True)
    print(f"  LLDB path: {lldb_check.stdout.strip()}")

    results = []

    # Run tests
    results.append(("Raw LLDB Diagnostic", await test_raw_lldb_breakpoint()))
    results.append(("Function Breakpoint", await test_function_breakpoint()))
    results.append(("File:Line Breakpoint", await test_file_line_breakpoint()))
    results.append(("Different Working Dirs", await test_breakpoint_from_different_dirs()))
    results.append(("Run with Breakpoints", await test_run_with_breakpoints()))
    results.append(("Examine Variables", await test_examine_variables_at_breakpoint()))
    results.append(("Backtrace", await test_backtrace_at_breakpoint()))
    results.append(("Conditional Breakpoint", await test_conditional_breakpoint()))

    # Summary
    print_header("Test Summary")
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
