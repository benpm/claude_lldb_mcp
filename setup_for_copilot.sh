#!/bin/bash
set -e

echo "=== Setting up LLDB MCP Server for Copilot CLI ==="

# Ensure Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Check for pip
if ! python3 -m pip --version &> /dev/null; then
    echo "pip not found. Attempting to install..."
    
    # Try ensurepip first
    if python3 -m ensurepip --user &> /dev/null; then
        echo "Installed pip via ensurepip"
    else
        # Try get-pip.py
        if command -v curl &> /dev/null; then
            echo "Downloading get-pip.py..."
            curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
            python3 get-pip.py --user
            rm get-pip.py
            echo "Installed pip via get-pip.py"
        else
            echo "Error: Could not install pip (no curl)"
            exit 1
        fi
    fi
fi

# Add user bin to PATH for this session
export PATH="$HOME/.local/bin:$PATH"

echo "Installing dependencies..."
python3 -m pip install --user "mcp[cli]" pydantic httpx

echo "Verifying installation..."
python3 -c "import mcp; import pydantic; import httpx; print('Dependencies imported successfully')"

echo "Running server tests..."
python3 test_server.py

echo "=== Setup Complete ==="
