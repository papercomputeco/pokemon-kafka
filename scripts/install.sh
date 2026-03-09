#!/usr/bin/env bash
# Install dependencies for the Pokemon Agent skill.
# Works on macOS, Linux, and inside stereOS VMs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Pokemon Agent Setup ==="
echo "Skill directory: $SKILL_DIR"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Install PyBoy + deps
echo ""
echo "Installing PyBoy and dependencies..."
pip3 install --quiet --break-system-packages pyboy Pillow numpy 2>/dev/null \
    || pip3 install --quiet pyboy Pillow numpy

echo ""
echo "Verifying PyBoy installation..."
python3 -c "from pyboy import PyBoy; print('PyBoy OK')"

# Create frames directory for screenshots
mkdir -p "$SKILL_DIR/frames"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Place your ROM file (.gb or .gbc) in: $SKILL_DIR/"
echo "  2. Run: python3 $SCRIPT_DIR/agent.py <rom_path>"
echo ""
echo "For stereOS deployment:"
echo "  mb init pokemon-agent"
echo "  cp -r $SKILL_DIR/* <project>/"
echo "  mb up"
