Model: Opus 4.6

# Log 1: stereOS Setup for Pokemon Agent

**Model:** GPT-5 Codex

## Directory Restructure

Files were flat in the repo root. Reorganized to match `jcard.toml` expectations:

```
pokemon-agent/
├── jcard.toml
├── SKILL.md
├── rom/                     # User-provided ROM
├── scripts/
│   ├── agent.py
│   ├── install.sh
│   └── memory_reader.py
└── references/
    ├── routes.json
    └── type_chart.json
```

## jcard.toml Rewrite

The original `jcard.toml` used a custom schema (runtime, entrypoint, network.policy). The `mb` CLI expects a different format. Key changes:

- Added `mixtape = "opencode-mixtape:latest"` (top-level field required by mb)
- Changed `[resources]` fields: `cpu` to `cpus`, added `GiB` suffix to memory/disk
- Changed `[network]` from `policy = "deny-all"` to `mode = "nat"` (needed for nix package downloads)
- Replaced custom `[agent]` config with mb-compatible format: `harness = "claude-code"`, `workdir`, `prompt`
- Replaced `[mounts]` with `[[shared]]` syntax: `host = "./"`, `guest = "/workspace"`
- Bumped memory from 2GiB to 4GiB and disk to 20GiB to match working sandbox configs

## Mixtape Selection

- `base:latest` was listed locally at 0 bytes (corrupt/incomplete) and not found on the registry
- `coder:latest` and `coder-mixtape:latest` not found on the registry
- Used `opencode-mixtape:latest` (4.4 GiB, already cached locally)

## Blockers and Fixes

### 1. File permissions denied in sandbox

Host files had `600` permissions (owner-only). The sandbox runs as `admin` (different UID), so all reads failed.

**Fix:** `chmod -R a+r` on the project directory, `chmod a+x` on `install.sh`.

### 2. Python not installed

The `opencode-mixtape` is NixOS-based and ships without Python.

**Fix:** `nix profile install nixpkgs#python312`

### 3. pip writes to read-only nix store

Running `pip install` tried to write to `/nix/store/...` which is immutable.

**Fix:** Created a venv in the admin home directory: `python3 -m venv ~/venv`, then installed packages into it.

### 4. Missing libstdc++.so.6

NumPy (required by PyBoy) needs `libstdc++` which wasn't in the NixOS image.

**Fix:** `nix profile install nixpkgs#gcc-unwrapped.lib`

### 5. Missing libz.so.1

After fixing libstdc++, numpy still failed on missing zlib.

**Fix:** `nix profile install nixpkgs#zlib`

### 6. LD_LIBRARY_PATH not set

Even after installing the nix packages, the shared libraries weren't found at runtime.

**Fix:** Export `LD_LIBRARY_PATH=$HOME/.nix-profile/lib:$LD_LIBRARY_PATH` before running python.

### 7. PyBoy save file permission error (minor)

On shutdown, PyBoy tries to write a `.ram` file next to the ROM. The ROM directory is mounted from the host and the file permissions block writes by the sandbox user. The agent runs fine — this only affects save state on exit.

## Final Working Command

```bash
ssh into sandbox, then:
export LD_LIBRARY_PATH=$HOME/.nix-profile/lib:$LD_LIBRARY_PATH
cd /workspace
~/venv/bin/python3 scripts/agent.py "rom/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb" --max-turns 100
```

## Packages Installed in Sandbox (via nix)

- `nixpkgs#python312` — Python 3.12.12
- `nixpkgs#python312Packages.pip` — pip 25.3
- `nixpkgs#gcc-unwrapped.lib` — libstdc++.so.6
- `nixpkgs#zlib` — libz.so.1

## Packages Installed in Sandbox (via pip in ~/venv)

- `pyboy` 2.7.0 — Game Boy emulator with Python API
- `Pillow` 12.1.1 — image processing for screenshot capture
- `numpy` 2.4.2 — required by PyBoy for screen buffer
- `pysdl2` 0.9.17 — SDL2 bindings (PyBoy dependency)
- `pysdl2-dll` 2.32.0 — bundled SDL2 shared libraries

## Result

Agent ran 100 turns headlessly. Started on Map 38 (player's room, Pallet Town), 0 badges, 0 party members (still in intro sequence). Needs more turns to advance past Oak's lab.
