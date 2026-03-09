#!/usr/bin/env bash
# Install dependencies for the Pokemon Agent skill.
# Works on macOS, Linux, and inside stereOS VMs (NixOS).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Pokemon Agent Setup ==="
echo "Skill directory: $SKILL_DIR"

# ---------------------------------------------------------------------------
# Detect NixOS (stereOS VMs use NixOS)
# ---------------------------------------------------------------------------
IS_NIXOS=false
if [ -f /etc/NIXOS ] || [ -d /nix/store ]; then
    IS_NIXOS=true
    echo "Detected NixOS environment"
fi

# ---------------------------------------------------------------------------
# Fix DNS inside stereOS VMs (systemd-resolved stub often broken)
# ---------------------------------------------------------------------------
if $IS_NIXOS; then
    if ! nslookup google.com &>/dev/null 2>&1; then
        echo "Fixing DNS (systemd-resolved not forwarding)..."
        sudo bash -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'
    fi
fi

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
if ! command -v python3 &>/dev/null; then
    if $IS_NIXOS; then
        echo "Installing Python via nix..."
        nix profile install nixpkgs#python312
    else
        echo "ERROR: python3 not found. Install Python 3.10+ first."
        exit 1
    fi
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# ---------------------------------------------------------------------------
# PyBoy + deps (NixOS needs a venv + native libs)
# ---------------------------------------------------------------------------
if $IS_NIXOS; then
    # Native libraries PyBoy/numpy need
    for pkg in gcc-unwrapped.lib zlib; do
        if ! nix profile list 2>/dev/null | grep -q "$pkg"; then
            echo "Installing nix package: $pkg"
            nix profile install "nixpkgs#$pkg"
        fi
    done
    export LD_LIBRARY_PATH="$HOME/.nix-profile/lib:${LD_LIBRARY_PATH:-}"

    # Use a venv so pip doesn't try to write to /nix/store
    if [ ! -d "$HOME/venv" ]; then
        echo "Creating Python venv..."
        python3 -m venv "$HOME/venv"
    fi
    echo "Installing PyBoy into venv..."
    "$HOME/venv/bin/pip" install --quiet pyboy Pillow numpy
    echo "Verifying PyBoy..."
    "$HOME/venv/bin/python3" -c "from pyboy import PyBoy; print('PyBoy OK')"
else
    echo ""
    echo "Installing PyBoy and dependencies..."
    pip3 install --quiet --break-system-packages pyboy Pillow numpy 2>/dev/null \
        || pip3 install --quiet pyboy Pillow numpy
    echo "Verifying PyBoy..."
    python3 -c "from pyboy import PyBoy; print('PyBoy OK')"
fi

# ---------------------------------------------------------------------------
# Writable directories (shared mount permissions)
# ---------------------------------------------------------------------------
# The stereOS shared mount preserves host file ownership (UID 501 on macOS).
# The VM runs as admin (UID 1000), so host-created directories are read-only
# unless we open permissions. These directories hold runtime output that the
# agent writes during a session.
for dir in frames pokedex .tapes; do
    mkdir -p "$SKILL_DIR/$dir"
    chmod a+rwx "$SKILL_DIR/$dir" 2>/dev/null || true
done

# ---------------------------------------------------------------------------
# Tapes CLI
# ---------------------------------------------------------------------------
if ! command -v tapes &>/dev/null && [ ! -f /usr/local/bin/tapes ]; then
    echo ""
    echo "Installing Tapes CLI..."
    sudo mkdir -p /usr/local/bin
    curl -fsSL https://download.tapes.dev/install | bash

    # NixOS: patch the dynamically linked binary for the nix linker
    if $IS_NIXOS && [ -f /usr/local/bin/tapes ]; then
        INTERP=$(find /nix/store -name "ld-linux-*.so.1" 2>/dev/null | head -1)
        if [ -n "$INTERP" ]; then
            if ! command -v patchelf &>/dev/null; then
                nix profile install nixpkgs#patchelf
            fi
            echo "Patching tapes binary for NixOS..."
            patchelf --set-interpreter "$INTERP" /usr/local/bin/tapes
        fi
    fi
fi

# Verify tapes
if command -v tapes &>/dev/null; then
    tapes version
elif [ -f /usr/local/bin/tapes ]; then
    /usr/local/bin/tapes version
fi

# Initialize Tapes in the project if not already done
if [ ! -f "$SKILL_DIR/.tapes/config.toml" ]; then
    echo "Initializing Tapes..."
    mkdir -p "$SKILL_DIR/.tapes"
    cd "$SKILL_DIR" && tapes init --preset anthropic 2>/dev/null \
        || /usr/local/bin/tapes init --preset anthropic
fi

echo ""
echo "=== Setup complete ==="
