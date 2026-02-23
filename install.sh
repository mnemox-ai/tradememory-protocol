#!/usr/bin/env bash
# TradeMemory Protocol — One-Click Install Script
# Usage: curl -sSL https://raw.githubusercontent.com/mnemox-ai/tradememory-protocol/main/install.sh | bash
# Or:    bash install.sh

set -e

REPO="https://github.com/mnemox-ai/tradememory-protocol.git"
DIR="tradememory-protocol"
MIN_PYTHON="3.10"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "  TradeMemory Protocol — Installer"
echo "  https://mnemox.ai"
echo "========================================"
echo ""

# Step 1: Check Python
echo -n "[1/6] Checking Python version... "
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo -e "${RED}FAILED${NC}"
    echo "  Python not found. Install Python ${MIN_PYTHON}+ from https://python.org"
    exit 1
fi

PY_VERSION=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_OK=$($PY -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)")
if [ "$PY_OK" = "0" ]; then
    echo -e "${RED}FAILED${NC}"
    echo "  Found Python ${PY_VERSION}, need ${MIN_PYTHON}+."
    exit 1
fi
echo -e "${GREEN}OK${NC} (Python ${PY_VERSION})"

# Step 2: Clone or update repo
echo -n "[2/6] Getting repository... "
if [ -d "$DIR" ]; then
    cd "$DIR"
    git pull --quiet 2>/dev/null || true
    echo -e "${GREEN}OK${NC} (updated existing)"
else
    git clone --quiet "$REPO" "$DIR"
    cd "$DIR"
    echo -e "${GREEN}OK${NC} (cloned)"
fi

# Step 3: Create virtual environment
echo -n "[3/6] Creating virtual environment... "
if [ ! -d "venv" ]; then
    $PY -m venv venv
    echo -e "${GREEN}OK${NC} (created)"
else
    echo -e "${GREEN}OK${NC} (exists)"
fi

# Activate venv
if [ -f "venv/Scripts/activate" ]; then
    # Windows Git Bash
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    # Linux/Mac
    source venv/bin/activate
fi

# Step 4: Install dependencies
echo -n "[4/6] Installing dependencies... "
pip install -q -r requirements.txt 2>/dev/null
echo -e "${GREEN}OK${NC}"

# Step 5: Set up .env
echo -n "[5/6] Setting up environment... "
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}OK${NC} (created .env from template)"
else
    echo -e "${GREEN}OK${NC} (.env already exists)"
fi

# Step 6: Run tests
echo -n "[6/6] Running tests... "
TEST_RESULT=$($PY -m pytest tests/ -q --tb=no 2>&1 | tail -1)
if echo "$TEST_RESULT" | grep -q "passed"; then
    echo -e "${GREEN}OK${NC} (${TEST_RESULT})"
else
    echo -e "${YELLOW}WARNING${NC} (${TEST_RESULT})"
    echo "  Some tests may have failed. Check with: python -m pytest tests/ -v"
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Installation complete!${NC}"
echo "========================================"
echo ""
echo "  Quick start:"
echo "    python demo.py              # Run interactive demo (no API key needed)"
echo "    python -m src.tradememory.server  # Start MCP server"
echo ""
echo "  For full setup, edit .env with your credentials."
echo "  Docs: https://github.com/mnemox-ai/tradememory-protocol"
echo ""
