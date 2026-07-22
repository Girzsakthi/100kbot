#!/usr/bin/env bash
#
# setup.sh -- one-command setup for the 100K Launch Bot.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#
# What it does:
#   1. Checks for Python 3.9+
#   2. Creates a virtual environment in ./venv (skipped on Replit, which
#      manages its own environment)
#   3. Installs dependencies from requirements.txt
#   4. Copies .env.example to .env if .env doesn't exist yet
#
set -euo pipefail

echo "=== 100K Launch Bot Setup ==="

# --- 1. Check Python version -------------------------------------------------
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.9+ and try again."
    exit 1
fi

PY_VERSION=$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    echo "ERROR: Python 3.9+ required, found $PY_VERSION."
    exit 1
fi
echo "Found Python $PY_VERSION"

# --- 2. Virtual environment ---------------------------------------------------
if [ -n "${REPL_ID:-}" ]; then
    echo "Detected Replit environment -- skipping venv creation."
    PIP_BIN="pip"
else
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment in ./venv ..."
        "$PYTHON_BIN" -m venv venv
    else
        echo "Virtual environment already exists, reusing it."
    fi
    # shellcheck disable=SC1091
    source venv/bin/activate
    PIP_BIN="pip"
fi

# --- 3. Install dependencies ---------------------------------------------------
echo "Installing dependencies from requirements.txt ..."
"$PIP_BIN" install --upgrade pip >/dev/null
"$PIP_BIN" install -r requirements.txt

# --- 4. Environment file ---------------------------------------------------
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example -- fill in your API keys before running the bot."
else
    echo ".env already exists, leaving it untouched."
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit .env and add your TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY"
echo "  2. Run the bot:"
if [ -z "${REPL_ID:-}" ]; then
    echo "       source venv/bin/activate && python bot.py"
else
    echo "       python bot.py"
fi
