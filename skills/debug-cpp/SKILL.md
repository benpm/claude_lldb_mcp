---
name: debug-cpp
description: Use this skill whenever the user wants to debug, step through, trace, or inspect a C/C++ program — even if they don't say "LLDB" or "debugger." Trigger on requests like "my program crashes," "help me find this bug," "why is this variable wrong," "set a breakpoint," "show me the call stack," "examine variables at line X," "run under the debugger," "disassemble this function," "read memory at this address," or "analyze this core dump." This skill provides a structured workflow for the LLDB MCP server tools (lldb_run, lldb_set_breakpoint, lldb_examine_variables, lldb_backtrace, etc.). Also trigger when the user mentions segfaults, assertion failures, undefined behavior, or wants to inspect program state at runtime.
---

# Debugging C/C++ with LLDB MCP Tools

This skill guides you through debugging compiled C/C++ programs using the LLDB MCP server. The server provides 17 specialized tools that wrap LLDB in batch mode — each tool call spawns a fresh LLDB process, so there's no persistent session state between calls. This means you need to replay setup (target + breakpoints) on each tool invocation, which the tools handle automatically via their parameters.

## Step 0: Gather what you need

Before touching any tool, ask the user (or infer from context) these three things:
- **Executable path** — the compiled binary (absolute path is most reliable)
- **What's wrong** — crash, wrong output, hang, assertion failure, unexpected variable value?
- **Arguments** — command-line args the program needs (can be empty)

If the user only has source files, go to **Build first** below. If they already have a binary, skip ahead.

## Build first (if no binary)

Compile with debug symbols and no optimization — without `-g -O0`, LLDB can't show source lines or variable names:

```bash
clang++ -g -O0 -o /abs/path/to/output /abs/path/to/source.cpp
# Multi-file:
clang++ -g -O0 -o output main.cpp helper.cpp
# CMake project:
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build
```

**Windows/git bash path note**: LLDB on Windows accepts both Unix-style git bash paths (`/c/Users/ben/proj/app`) and Windows-style paths (`C:\Users\ben\proj\app`). Pass whichever form the user gives you — both work. Use absolute paths to avoid working-directory ambiguity.

## Step 1: Confirm the environment

Call `lldb_version` (no parameters) to confirm LLDB is installed and reachable. If this fails, LLDB is not in PATH — on Windows, the LLVM installer must add `C:\Program Files\LLVM\bin` to the system PATH.

## Step 2: Choose your entry point

Decide where to stop execution first based on what you're investigating:

| Scenario | Breakpoint approach |
|---|---|
| Function crashes or has wrong output | `location = "function_name"` |
| Bug at a specific source line | `location = "/abs/path/file.cpp:42"` |
| Program crashes immediately | Use `lldb_analyze_crash` instead of breakpoints |
| Want to start from scratch | `location = "main"` |
| Address you found in a crash log | `location = "0x401234"` |

Verify the breakpoint resolves before running: call `lldb_set_breakpoint` with `executable` and `location`. If the output says "1 location" the binary loaded correctly; "0 locations" means the function name is wrong, the source path doesn't match, or the binary has no debug symbols.

## Step 3: Run and stop

`lldb_run` executes the binary and stops at the first breakpoint hit. Key parameters:
- `executable` — path to binary
- `breakpoints` — list of location strings (same format as `lldb_set_breakpoint`)
- `args` — list of CLI args for the program
- `stop_at_entry` — set `true` only if you want to stop before `main` runs
- `working_dir` — only needed if the program uses relative file paths

The output shows where execution stopped. If it runs to completion without stopping, the breakpoint location is never reached — try a broader location or trace from `main`.

## Step 4: Inspect at the stopped frame

With execution paused, use these tools to understand what's happening:

**Variables** — `lldb_examine_variables(executable, breakpoint="function_name")`
Shows local variables and function arguments. Use the optional `variables` list to focus on specific names. The `breakpoint` parameter here is a function name (not file:line), because the tool needs to re-stop at that function to read locals.

**Call stack** — `lldb_backtrace(executable, breakpoint="function_name")`
Shows all frames leading to where you stopped. Use `all_threads=true` for threading bugs. The `limit` parameter caps how many frames to show.

**Expression evaluation** — `lldb_evaluate(executable, expression="...", breakpoint="function_name")`
Evaluates any C/C++ expression in the stopped frame. Useful for: `ptr->field`, `sizeof(MyStruct)`, `vec[i]`, `(int)some_cast`. If the expression has side effects, be aware it actually executes.

**Registers** — `lldb_registers(executable, breakpoint="function_name", register_set="general")`
Useful after a crash or when debugging at the assembly level. `register_set` options: `"general"`, `"float"`, `"vector"`, `"all"`.

**Threads** — `lldb_threads(executable, breakpoint="function_name")`
Lists all threads and optionally shows their backtraces (`show_backtrace=true`). Useful for deadlock or race condition investigation.

## Step 5: Crash analysis

When the program crashes (segfault, assertion, abort) and you want to understand why:

`lldb_analyze_crash(executable)` — runs the binary, lets it crash, then captures the crash state: backtrace, registers, local variables at the crash frame, loaded modules. No breakpoints needed.

If you have a core dump file: `lldb_analyze_crash(executable, core_file="/path/to/core")`.

The output tells you the crash address, the faulting instruction, and what was in scope at that moment — usually enough to identify the cause.

## Advanced inspection tools

Use these when the initial inspection doesn't fully explain the problem:

**Source listing** — `lldb_source(executable, file="/abs/path/file.cpp", line=42, count=20)`
Shows source code around a specific line. Use `function="func_name"` to show an entire function. Helps when you want to correlate what LLDB reports with the actual code.

**Memory reading** — `lldb_read_memory(executable, address="0x7fff...", count=64, format="x", breakpoint="func_name")`
Reads raw memory. `format` options: `"x"` (hex), `"b"` (bytes), `"d"` (decimal), `"s"` (string), `"i"` (instructions). Useful for inspecting heap contents, buffer overflows, or pointer targets.

**Watchpoints** — `lldb_watchpoint(executable, variable="my_var", watch_type="write")`
Stops execution whenever a variable is written. Use `watch_type="read_write"` to catch both reads and writes. Effective for tracking down where a value gets corrupted.

**Disassembly** — `lldb_disassemble(executable, target="function_name")`
Shows assembly for a function. Use `target="0x401000-0x401100"` for an address range. `show_bytes=true` includes opcode bytes; `mixed=true` interleaves source lines.

**Symbol lookup** — `lldb_symbols(executable, query="MyClass", query_type="type")`
Looks up symbols. `query_type` options: `"name"`, `"regex"`, `"address"`, `"type"`. Useful for finding where a function or type is defined, or what's at a specific address.

**Loaded modules** — `lldb_images(executable)` lists all shared libraries loaded. Use `filter_pattern="libfoo"` to narrow results. Useful when debugging library interactions or checking which version of a library was loaded.

## Escape hatch

When none of the specialized tools fits, use `lldb_run_command(command="...", target="/path/to/exe")` to run any raw LLDB command. The `command` parameter accepts any LLDB command string. Examples:
- `"breakpoint set --name MyClass::method"`
- `"expr -l c++ -- (int)some_function(42)"`
- `"memory find -e 'deadbeef' -- 0x1000 0x2000"`

Use `lldb_help(topic="breakpoint")` to look up LLDB command syntax.

## Iteration pattern

Debugging is rarely one shot. After each inspection, decide:
- **Need to look at a different location?** Call `lldb_set_breakpoint` with the new location, then `lldb_run` again.
- **Variable looks wrong higher in the stack?** Call `lldb_backtrace` first to identify the frame, then `lldb_examine_variables` at the relevant function.
- **Narrowed it down to a specific write?** Switch to `lldb_watchpoint`.
- **Need to verify a hypothesis?** Use `lldb_evaluate` to test an expression without recompiling.
- **Hit a crash instead of a breakpoint?** Switch to `lldb_analyze_crash`.
