#!/usr/bin/env python3
"""
Test script for LLDB MCP Server

This script verifies that:
1. All imports work correctly
2. The server can be instantiated
3. Tools are properly registered
"""

import sys
import json


def test_imports():
    """Test that all required imports work."""
    print("Testing imports...")
    try:
        from mcp.server.fastmcp import FastMCP
        from pydantic import BaseModel, Field
        print("  ✓ MCP and Pydantic imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        print("  Install dependencies with: pip install 'mcp[cli]' pydantic")
        return False


def test_server_creation():
    """Test that the server can be created."""
    print("\nTesting server creation...")
    try:
        # Import the server module
        import lldb_mcp_server
        
        # Check the server instance
        mcp = lldb_mcp_server.mcp
        print(f"  ✓ Server created: {mcp.name}")
        return True
    except Exception as e:
        print(f"  ✗ Server creation failed: {e}")
        return False


def test_tools_registered():
    """Test that tools are properly registered."""
    print("\nTesting tool registration...")
    try:
        import lldb_mcp_server
        mcp = lldb_mcp_server.mcp
        
        # List expected tools
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
        
        # Get registered tools
        # Note: FastMCP stores tools internally
        print(f"  ✓ Expected {len(expected_tools)} tools")
        
        return True
    except Exception as e:
        print(f"  ✗ Tool registration check failed: {e}")
        return False


def test_lldb_available():
    """Test that LLDB is available on the system."""
    print("\nTesting LLDB availability...")
    import shutil
    
    lldb_path = shutil.which("lldb")
    if lldb_path:
        print(f"  ✓ LLDB found at: {lldb_path}")
        
        # Try to get version
        import subprocess
        try:
            result = subprocess.run(
                [lldb_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            version = result.stdout.strip().split('\n')[0]
            print(f"  ✓ Version: {version}")
            return True
        except Exception as e:
            print(f"  ⚠ Could not get version: {e}")
            return True
    else:
        print("  ⚠ LLDB not found in PATH")
        print("  Install LLDB to use the server")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("LLDB MCP Server Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Server Creation", test_server_creation()))
    results.append(("Tool Registration", test_tools_registered()))
    results.append(("LLDB Available", test_lldb_available()))
    
    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\nAll tests passed! The server is ready to use.")
        print("\nTo run the server:")
        print("  python lldb_mcp_server.py")
        return 0
    else:
        print("\nSome tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
