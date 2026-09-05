"""Write the final catalog summary to the journal."""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
from memory_writer import append_observations

print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)

obs = [
    {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "source_session": "extractor",
        "content": (
            "map=165 mansion switch-door catalog SUMMARY: "
            "165(2,5) and 214(2,11) are in the same toggle group: "
            "state B=(16,7)shut (24,13)open (20,17)/(21,17)shut; "
            "state A=(16,7)open (24,13)shut (20,17)/(21,17)unreachable. "
            "215(10,5) opens 165's stairs door (20,17)/(21,17) AND shuts 214's (9,4)/(9,5); "
            "the return route is the hole on 215 tile 0x11 at (16,13) dropping to 165(16,14). "
            "216's switches (18,25) and (20,3) control doors on 216 and also affect 165's pocket. "
            "SECRET KEY collected at 216(5,13); gym door 8(18,3) opens with the key."
        ),
    }
]
append_observations("pokedex/memory", obs, dedupe=True)
print("summary written", flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
