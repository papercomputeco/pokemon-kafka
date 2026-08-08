#!/usr/bin/env bash
# Re-arm the HEAL demo (beat 8: select a Stuck anomaly → HEAL → accepted).
#
# The healer race is deterministic: the variant seed is the hash of the run's
# summary.json and the control is the current notes.md genome. From the
# pre-heal baseline (no genome, defaults) the beat-8 race ACCEPTS with a huge
# margin (score 885→9005), so resetting to that baseline makes the live demo
# reproduce it every time. Running HEAL consumes the baseline (the accepted
# genome becomes the new control) — re-run this script before each demo.
#
# Safe to run repeatedly. Keeps a backup of the current notes.md.
set -euo pipefail
cd "$(dirname "$0")/.."

cp notes.md notes.md.bak
uv run python - <<'EOF'
import re
from pathlib import Path

p = Path("notes.md")
text = re.sub(r"\n[^\n]*\n<!-- autotune:genome\n.*?\n-->\n", "", p.read_text(), flags=re.DOTALL)
p.write_text(text)
print(f"notes.md: {text.count('autotune:genome')} genome blocks remain (backup in notes.md.bak)")
EOF
rm -f data/healer_state.json
echo "healer state cleared — HEAL demo re-armed"
