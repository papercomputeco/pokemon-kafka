"""Loop supervisor — force continuation and strategy switches, harness-side.

Mission text is measured exhausted: six early exits across three models (five Haiku, one Sonnet)
were each told in-mission not to, and did. The supervisor moves those levers out of the mission:

- **exit classification** (`classify-exit`): the expedition runner calls this when an operator
  process ends. Harness death -> resume from the newest baton (bounded); a baton -> next leg;
  budget left -> a continuation relaunch with the pending evidence in the prompt (bounded);
  budget exhausted without a baton -> the attempt is charged against the run's dominant wall
  fingerprint, and at ``escalate_after`` attempts on the same fingerprint the decision becomes
  ``escalate`` (the Opus fix-source tier).
- **wall fingerprints** (`observe`): map-pair springs (A->B->A transitions, the door-mat class
  that is 3-for-3 as the wall) and stalls (no new position across a poll window), parsed from
  lane logs' ``MAP CHANGE`` lines. Springs survive load (they are real transitions); the stall
  nudge is suppressed when the box is loaded, per the Brock-day rule — starvation looks like a
  wall and must never be reported as one.
- **nudges**: one per fingerprint per run (the ``MTMOON-MISS`` once-per-map pattern), emitted
  into the continuation prompt so a relaunched operator starts with "you have hit <wall> N
  times; change dimension (code vs genome vs route)" instead of rediscovering it.

State is a JSON file owned by scripts/expedition_run.sh, carried across resumes and legs.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

MAP_CHANGE = re.compile(r"MAP CHANGE \| (\d+) -> (\d+)")

SPRING_MIN = 6  # A->B->A round trips before a map pair is a fingerprint, not a heal trip
DEFAULT_MAX_CONTINUATIONS = 3
DEFAULT_MAX_RESUMES = 5
DEFAULT_ESCALATE_AFTER = 3
CONTINUE_BELOW = 0.8  # exit with < this fraction of budget used -> continuation


def spring_counts(text: str) -> Counter:
    """Count A<->B round trips from a lane log's MAP CHANGE lines. A round trip is a transition
    immediately undone (58->2 then 2->58): the door-mat spring signature, hundreds per second
    when live (Sonnet's probe13: 232+ on one pair)."""
    pairs = MAP_CHANGE.findall(text)
    springs: Counter = Counter()
    i = 0
    while i < len(pairs) - 1:
        (a, b), (c, d) = pairs[i], pairs[i + 1]
        if b == c and d == a:  # the second transition undoes the first: one bounce
            springs[f"{min(int(a), int(b))}<->{max(int(a), int(b))}"] += 1
            i += 2
        else:
            i += 1
    return springs


class Supervisor:
    def __init__(
        self,
        *,
        max_continuations: int = DEFAULT_MAX_CONTINUATIONS,
        max_resumes: int = DEFAULT_MAX_RESUMES,
        escalate_after: int = DEFAULT_ESCALATE_AFTER,
    ) -> None:
        self.max_continuations = max_continuations
        self.max_resumes = max_resumes
        self.escalate_after = escalate_after
        self.continuations = 0
        self.resumes = 0
        self.fingerprints: Counter = Counter()  # wall id -> leg-attempts charged against it
        self.springs: Counter = Counter()  # wall id -> observed round trips (evidence, not attempts)
        self.nudged: set[str] = set()
        self.last_positions: str | None = None  # progress signature from the previous poll

    # ---- observation ----------------------------------------------------------------------

    def observe(self, lane_logs: list[str], *, positions: str | None = None, load_ok: bool = True) -> list[str]:
        """Fold lane-log text into fingerprints; return new nudges (one per fingerprint, ever)."""
        nudges = []
        for text in lane_logs:
            for wall, n in spring_counts(text).items():
                if n >= SPRING_MIN:
                    self.springs[wall] += n
                    if wall not in self.nudged:
                        self.nudged.add(wall)
                        nudges.append(
                            f"WALL {wall}: a door/edge spring measured {n}x this leg. No genome knob has ever "
                            f"moved one (0 for ~2000 applied patches); it is code or route. Consult "
                            f"`uv run python scripts/rom_truth.py route <here> <goal>` before another attempt."
                        )
        if positions is not None:
            if positions == self.last_positions and load_ok:
                if "stall" not in self.nudged:
                    self.nudged.add("stall")
                    nudges.append(
                        "STALL: no new position since the last poll. State the furthest coordinate reached "
                        "and change dimension (code vs genome vs route) before repeating the approach."
                    )
            self.last_positions = positions
        return nudges

    # ---- exit classification --------------------------------------------------------------

    def classify_exit(self, *, budget_s: float, used_s: float, baton: bool, harness_death: bool) -> dict:
        """The expedition runner's one call per operator exit. Returns {action, reason, prompt?}."""
        if harness_death:
            if self.resumes >= self.max_resumes:
                return {"action": "stop_alert", "reason": f"harness death #{self.resumes + 1} exceeds resume budget"}
            self.resumes += 1
            return {"action": "resume", "reason": f"harness death; resume {self.resumes}/{self.max_resumes}"}
        if baton:
            return {"action": "next_leg", "reason": "baton written — the leg is cleared"}
        if used_s < CONTINUE_BELOW * budget_s and self.continuations < self.max_continuations:
            self.continuations += 1
            left = int((budget_s - used_s) / 60)
            walls = ", ".join(f"{w} (x{n})" for w, n in self.springs.most_common(3)) or "none fingerprinted"
            return {
                "action": "continue",
                "reason": f"early exit with ~{left}m left; continuation {self.continuations}/{self.max_continuations}",
                "prompt": (
                    f"The run is not over: ~{left} minutes of budget remain and no baton is written. "
                    f"Walls fingerprinted so far: {walls}. Continue from where you stopped; do not re-verify "
                    f"what is already committed."
                ),
            }
        # Budget spent (or continuations exhausted) without a baton: charge the attempt.
        wall = self.springs.most_common(1)[0][0] if self.springs else "no-fingerprint"
        self.fingerprints[wall] += 1
        if self.fingerprints[wall] >= self.escalate_after:
            return {
                "action": "escalate",
                "reason": f"wall {wall} has taken {self.fingerprints[wall]} attempts",
                "wall": wall,
            }
        return {
            "action": "retry_leg",
            "reason": f"attempt {self.fingerprints[wall]}/{self.escalate_after} on wall {wall}",
            "wall": wall,
        }

    # ---- persistence ----------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "max_continuations": self.max_continuations,
            "max_resumes": self.max_resumes,
            "escalate_after": self.escalate_after,
            "continuations": self.continuations,
            "resumes": self.resumes,
            "fingerprints": dict(self.fingerprints),
            "springs": dict(self.springs),
            "nudged": sorted(self.nudged),
            "last_positions": self.last_positions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Supervisor:
        sup = cls(
            max_continuations=d.get("max_continuations", DEFAULT_MAX_CONTINUATIONS),
            max_resumes=d.get("max_resumes", DEFAULT_MAX_RESUMES),
            escalate_after=d.get("escalate_after", DEFAULT_ESCALATE_AFTER),
        )
        sup.continuations = d.get("continuations", 0)
        sup.resumes = d.get("resumes", 0)
        sup.fingerprints = Counter(d.get("fingerprints", {}))
        sup.springs = Counter(d.get("springs", {}))
        sup.nudged = set(d.get("nudged", []))
        sup.last_positions = d.get("last_positions")
        return sup

    @classmethod
    def load(cls, path: Path) -> Supervisor:
        if path.exists():
            return cls.from_dict(json.loads(path.read_text()))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ce = sub.add_parser("classify-exit", help="decide resume/continue/next/retry/escalate after an operator exit")
    ce.add_argument("--state", type=Path, required=True)
    ce.add_argument("--budget", type=float, required=True)
    ce.add_argument("--used", type=float, required=True)
    ce.add_argument("--baton", type=int, default=0)
    ce.add_argument("--harness-death", type=int, default=0)
    ce.add_argument("--load-ok", type=int, default=1)
    ce.add_argument("--lane-log", type=Path, action="append", default=[])
    rp = sub.add_parser("replay", help="what the supervisor would have said, from a run's lane logs")
    rp.add_argument("logs", type=Path, nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "replay":
        springs: Counter = Counter()
        for p in args.logs:
            springs.update(spring_counts(p.read_text(errors="replace")))
        for wall, n in springs.most_common():
            if n >= SPRING_MIN:
                print(f"WALL {wall}: {n} round trips")
        return 0
    sup = Supervisor.load(args.state)
    texts = [p.read_text(errors="replace") for p in args.lane_log if p.exists()]
    nudges = sup.observe(texts, load_ok=bool(args.load_ok))
    decision = sup.classify_exit(
        budget_s=args.budget, used_s=args.used, baton=bool(args.baton), harness_death=bool(args.harness_death)
    )
    if nudges and decision.get("prompt"):
        decision["prompt"] += "\n" + "\n".join(nudges)
    decision["nudges"] = nudges
    sup.save(args.state)
    print(json.dumps(decision))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
