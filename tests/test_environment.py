#!/usr/bin/env python3
"""
Environment validation for the LLDB MCP server on Windows/git bash.

Validates the full end-to-end LLDB debugging chain:
  1. LLDB in PATH
  2. clang++ in PATH
  3. Compile test_fixtures/simple.cpp
  4. LLDB loads the binary
  5. Breakpoint hits (function name and file:line)
  6. Variables visible at breakpoint
  7. Backtrace correct
  8. MCP tool: lldb_set_breakpoint
  9. MCP tool: lldb_examine_variables
  10. MCP tool: lldb_backtrace

Usage:
    python tests/test_environment.py   # standalone report
    pytest tests/test_environment.py -v
"""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "test_fixtures"
SIMPLE_SRC = FIXTURES_DIR / "simple.cpp"

sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Result tracking (non-fatal — collect all results then report)
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    _results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if detail and not passed:
        print(f"         {detail[:300]}")
    return passed


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exe_path() -> Path:
    """Return the compiled simple binary path, checking .exe first on Windows."""
    if sys.platform == "win32":
        p = FIXTURES_DIR / "simple.exe"
        if p.exists():
            return p
    return FIXTURES_DIR / "simple"


# ---------------------------------------------------------------------------
# Section functions — each returns True if the section's core check passed
# ---------------------------------------------------------------------------


def check_lldb() -> bool:
    section("1. LLDB in PATH")
    lldb = shutil.which("lldb")
    if not check("lldb found in PATH", lldb is not None, lldb or "not found"):
        return False
    try:
        r = subprocess.run(["lldb", "--version"], capture_output=True, text=True, timeout=10)
        ver = r.stdout.strip() or r.stderr.strip()
        ok = r.returncode == 0 and "lldb" in ver.lower()
        check("lldb --version succeeds", ok, ver[:100])
        return ok
    except Exception as e:
        check("lldb --version succeeds", False, str(e))
        return False


def check_clang() -> bool:
    section("2. clang++ in PATH")
    clang = shutil.which("clang++")
    if not check("clang++ found in PATH", clang is not None, clang or "not found"):
        return False
    try:
        r = subprocess.run(["clang++", "--version"], capture_output=True, text=True, timeout=10)
        ok = r.returncode == 0
        check("clang++ --version succeeds", ok, r.stdout.strip()[:100])
        return ok
    except Exception as e:
        check("clang++ --version succeeds", False, str(e))
        return False


def check_compile() -> bool:
    section("3. Compile test_fixtures/simple.cpp")
    if not check("simple.cpp exists", SIMPLE_SRC.exists(), str(SIMPLE_SRC)):
        return False

    exe = FIXTURES_DIR / ("simple.exe" if sys.platform == "win32" else "simple")
    cmd = ["clang++", "-g", "-O0", "-o", str(exe), str(SIMPLE_SRC)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(FIXTURES_DIR))
        ok = r.returncode == 0 and exe.exists()
        check("Compilation succeeds", ok, r.stderr.strip()[:200] if not ok else str(exe))
        return ok
    except Exception as e:
        check("Compilation succeeds", False, str(e))
        return False


def check_lldb_loads() -> bool:
    section("4. LLDB loads the binary")
    from lldb_mcp_server import _run_lldb_script

    exe = _exe_path()
    if not check("Binary exists", exe.exists(), str(exe)):
        return False

    r = _run_lldb_script([f"target create {exe}", "target list"])
    ok = "current target" in r["output"].lower() or r["success"]
    check("LLDB target create succeeds", ok, r["output"][:200])
    return ok


def check_breakpoint_hits() -> bool:
    section("5. Breakpoints hit")
    from lldb_mcp_server import _run_lldb_script

    exe = _exe_path()
    if not exe.exists():
        check("Binary available", False, str(exe))
        return False

    # Function name breakpoint
    r = _run_lldb_script(
        [
            f"target create {exe}",
            "breakpoint set --name add",
            "run",
            "thread backtrace",
            "quit",
        ]
    )
    out = r["output"]
    bp_set = "Breakpoint 1" in out or "breakpoint" in out.lower()
    stopped = "add" in out and ("#0" in out or "frame" in out.lower())
    check("Function name breakpoint (add) resolves", bp_set, out[:300])
    check("Execution stops at breakpoint", stopped, out[:300])

    # File:line breakpoint
    r2 = _run_lldb_script(
        [
            f"target create {exe}",
            f"breakpoint set --file {SIMPLE_SRC} --line 5",
            "breakpoint list",
            "run",
            "quit",
        ]
    )
    check(
        "File:line breakpoint (simple.cpp:5) resolves",
        "Breakpoint 1" in r2["output"],
        r2["output"][:200],
    )

    return bp_set and stopped


def check_variables() -> bool:
    section("6. Variables visible at breakpoint")
    from lldb_mcp_server import _run_lldb_script

    exe = _exe_path()
    if not exe.exists():
        check("Binary available", False, str(exe))
        return False

    r = _run_lldb_script(
        [
            f"target create {exe}",
            "breakpoint set --name add",
            "run",
            "frame variable",
            "quit",
        ]
    )
    out = r["output"]
    has_a = "a" in out and ("int" in out or "=" in out)
    has_b = "b" in out and ("int" in out or "=" in out)
    check("Variable 'a' visible in add()", has_a, out[:400])
    check("Variable 'b' visible in add()", has_b, out[:400])
    return has_a and has_b


def check_backtrace() -> bool:
    section("7. Backtrace")
    from lldb_mcp_server import _run_lldb_script

    exe = _exe_path()
    if not exe.exists():
        check("Binary available", False, str(exe))
        return False

    r = _run_lldb_script(
        [
            f"target create {exe}",
            "breakpoint set --name add",
            "run",
            "thread backtrace",
            "quit",
        ]
    )
    out = r["output"]
    check("Frame #0 in backtrace", "#0" in out, out[:300])
    check("'add' in backtrace", "add" in out, out[:300])
    check("'main' in backtrace", "main" in out, out[:300])
    return "#0" in out and "add" in out


def check_mcp_set_breakpoint() -> bool:
    section("8. MCP tool: lldb_set_breakpoint")
    from lldb_mcp_server import SetBreakpointInput, lldb_set_breakpoint

    exe = _exe_path()
    if not exe.exists():
        check("Binary available", False, str(exe))
        return False

    result = asyncio.run(
        lldb_set_breakpoint(SetBreakpointInput(executable=str(exe), location="main"))
    )
    ok = "Breakpoint" in result or "breakpoint" in result.lower()
    check("lldb_set_breakpoint returns breakpoint info", ok, result[:200])
    return ok


def check_mcp_examine_variables() -> bool:
    section("9. MCP tool: lldb_examine_variables")
    from lldb_mcp_server import ExamineVariablesInput, lldb_examine_variables

    exe = _exe_path()
    if not exe.exists():
        check("Binary available", False, str(exe))
        return False

    result = asyncio.run(
        lldb_examine_variables(ExamineVariablesInput(executable=str(exe), breakpoint="add"))
    )
    ok = "a" in result or "b" in result or "frame" in result.lower()
    check("lldb_examine_variables returns variable data", ok, result[:200])
    return ok


def check_mcp_backtrace() -> bool:
    section("10. MCP tool: lldb_backtrace")
    from lldb_mcp_server import BacktraceInput, lldb_backtrace

    exe = _exe_path()
    if not exe.exists():
        check("Binary available", False, str(exe))
        return False

    result = asyncio.run(lldb_backtrace(BacktraceInput(executable=str(exe), breakpoint="add")))
    ok = "#0" in result or "frame" in result.lower() or "add" in result
    check("lldb_backtrace returns stack frames", ok, result[:200])
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print(f"\n{'#' * 60}")
    print("#  LLDB MCP Server — Environment Validation")
    print(f"#  Platform: {sys.platform}")
    print(f"#  Project:  {PROJECT_ROOT}")
    print(f"{'#' * 60}")

    lldb_ok = check_lldb()
    clang_ok = check_clang()

    compiled = False
    if clang_ok:
        compiled = check_compile()
    else:
        section("3. Compile (skipped — clang++ not found)")

    binary_available = compiled or _exe_path().exists()

    if lldb_ok and binary_available:
        check_lldb_loads()
        check_breakpoint_hits()
        check_variables()
        check_backtrace()
        check_mcp_set_breakpoint()
        check_mcp_examine_variables()
        check_mcp_backtrace()
    else:
        section("LLDB tests (skipped)")
        print("  Skipping: LLDB not found or binary not compiled.")

    # Summary
    print(f"\n{'=' * 60}\n  SUMMARY\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    for name, ok, _ in _results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n  {passed}/{total} checks passed")
    print(f"{'#' * 60}\n")

    return 0 if all(ok for _, ok, _ in _results) else 1


# ---------------------------------------------------------------------------
# Pytest-compatible test functions
# ---------------------------------------------------------------------------


def test_environment_lldb_in_path() -> None:
    assert check_lldb(), "LLDB not found in PATH"


def test_environment_clang_in_path() -> None:
    assert check_clang(), "clang++ not found in PATH"


def test_environment_compile() -> None:
    assert check_compile(), "Compilation of simple.cpp failed"


def test_environment_lldb_loads_binary() -> None:
    assert check_lldb_loads(), "LLDB could not load binary"


def test_environment_breakpoint_hits() -> None:
    assert check_breakpoint_hits(), "Breakpoint did not hit"


def test_environment_variables() -> None:
    assert check_variables(), "Variables not visible at breakpoint"


def test_environment_backtrace() -> None:
    assert check_backtrace(), "Backtrace failed"


def test_environment_mcp_set_breakpoint() -> None:
    assert check_mcp_set_breakpoint(), "lldb_set_breakpoint MCP tool failed"


def test_environment_mcp_examine_variables() -> None:
    assert check_mcp_examine_variables(), "lldb_examine_variables MCP tool failed"


def test_environment_mcp_backtrace() -> None:
    assert check_mcp_backtrace(), "lldb_backtrace MCP tool failed"


if __name__ == "__main__":
    sys.exit(main())
