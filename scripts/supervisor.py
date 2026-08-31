"""Loop supervisor — the leg's loop body, and the cross-run loop that keeps relaunching it.

Two halves, both here on purpose.

**The loop body** (``run``) is the one the expedition skill promises: deterministic Python boots
a baton, looks the topology up in the extracted truth, and walks it hop by hop. When a hop
fails, the supervisor does not guess and does not hand the wheel to a model — it measures the
failure, builds a *bounded menu* of actions the road engine can actually execute, and asks the
seated crew member (`scripts/expedition_crew.py`: navigation, then puzzle, never Anthropic) to
pick exactly one. A wrong answer costs one attempt. When the ladder is exhausted the run writes
``docs/learnings/`` and emits ``supervisor.exhausted`` for the operator, and stops.

    uv run python scripts/supervisor.py run --state <baton> --goal <map> --budget 7200

**The cross-run loop** (``classify-exit``/``observe``/``replay``) is the older, outer half, owned
by ``scripts/expedition_run.sh``: it decides what happens when a whole operator process exits.
Mission text is measured exhausted — six early exits across three models (five Haiku, one
Sonnet) were each told in-mission not to, and did — so those levers live out here:

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
import sys
import time
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

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


# ============================================================================================
# The loop body: drive a leg, consult the crew on a failed hop, execute one bounded action.
# ============================================================================================

LEARNINGS_DIR = WORKSPACE / "docs" / "learnings"

NAV_ATTEMPTS = 2  # attempts 1..2 are navigation-class; past that the wall is a puzzle
LADDER_ATTEMPTS = 4  # 2 navigation + 2 puzzle, then the ladder is written down and stops
BODY_WAIT_FRAMES = 240  # wanderers clear; a trainer in a corridor never will (PR #113)
DEFAULT_MAX_HOPS = 80
DEFAULT_ENGAGE_ROUNDS = 14

# Every action below is something the road engine can actually perform. A menu item the engine
# cannot execute is a way to log a decision and change nothing, which reads as progress and is
# not — so the menus are built from `road`'s verbs, not from what sounds reasonable.
ACTIONS = (
    "RETRY_SAME",  # the hop again: stalls and wanderers are often one attempt deep
    "TRY_FAR_EDGE_CELL",  # aim at the far end of the open edge, not the nearest cell
    "USE_GATE_WARP",  # the route is severed by its own gate building — go through it
    "BACK_OUT_AND_REENTER",  # leave by the nearest warp and come back; reloads bodies/scripts
    "WAIT_FOR_BODIES",  # bodies are not walls: wanderers move if you wait
    "TALK_TO_BLOCKER",  # what the blocker SAYS is the finding (guards, story gates)
    "GIVE_UP",  # end the leg now; the operator gets the written record
)

MENUS: dict[str, tuple[str, ...]] = {
    "no-route": ("BACK_OUT_AND_REENTER", "TALK_TO_BLOCKER", "USE_GATE_WARP", "GIVE_UP"),
    "no-path": ("USE_GATE_WARP", "TRY_FAR_EDGE_CELL", "WAIT_FOR_BODIES", "BACK_OUT_AND_REENTER", "GIVE_UP"),
    "body-blocked": ("WAIT_FOR_BODIES", "TALK_TO_BLOCKER", "TRY_FAR_EDGE_CELL", "RETRY_SAME", "GIVE_UP"),
    "refused": ("TALK_TO_BLOCKER", "BACK_OUT_AND_REENTER", "TRY_FAR_EDGE_CELL", "RETRY_SAME", "GIVE_UP"),
    "stuck-on-edge": ("TRY_FAR_EDGE_CELL", "USE_GATE_WARP", "RETRY_SAME", "BACK_OUT_AND_REENTER", "GIVE_UP"),
}
DEFAULT_MENU = ("RETRY_SAME", "TRY_FAR_EDGE_CELL", "USE_GATE_WARP", "BACK_OUT_AND_REENTER", "GIVE_UP")


def menu_for(failure: str, *, edge_hop: bool = True) -> list[str]:
    """The bounded menu for a measured failure, minus what this hop cannot do."""
    menu = list(MENUS.get(failure, DEFAULT_MENU))
    if not edge_hop:  # a warp hop has no edge cells to aim at
        menu = [m for m in menu if m != "TRY_FAR_EDGE_CELL"]
    return menu


def describe(rig, goal: int, hop: dict | None, failure: str, notes: list[str] | None = None) -> str:
    """The measured facts handed to a seat. Everything here was read from RAM or the cartridge."""
    import road
    import rom_truth as rt

    mp, x, y = rig.pos()
    m = rig.truth["maps"].get(str(mp), {})
    lines = [
        f"GOAL: reach map {goal}. You are on map {mp} at ({x}, {y}).",
        f"MAP {mp}: {m.get('width', '?')}x{m.get('height', '?')}, tileset {m.get('tileset', '?')} "
        "(tile-id meanings are per-tileset and may not be reused across tilesets).",
        f"ROUTED CHAIN (extracted from this cartridge): {rt.describe_route(rt.route(rig.truth, mp, goal) or [])}"
        or "ROUTED CHAIN: none",
    ]
    if hop:
        lines.append(f"FAILED HOP: {mp} --{hop['via']}--> {hop['to']}; the engine returned {failure!r}.")
        if hop["via"] == "edge":
            try:
                cells, direction = road.edge_cells(rig.truth, mp, hop["to"])
                shown = sorted(cells)[:14]
                lines.append(
                    f"OPEN EDGE CELLS toward {hop['to']} (step {direction}): {shown}"
                    + (" ..." if len(cells) > 14 else "")
                )
            except (StopIteration, KeyError):
                lines.append(f"OPEN EDGE CELLS toward {hop['to']}: the connection table has no side for this pair.")
        else:
            lines.append(f"WARP TILE: ({hop.get('x')}, {hop.get('y')}) on this map.")
    else:
        lines.append(f"NO ROUTE: the extracted connection graph has no chain from map {mp} to map {goal}.")
    bodies = sorted(rig.bodies())
    lines.append(f"LIVE BODIES (sprites on screen right now): {bodies[:12]}" + (" ..." if len(bodies) > 12 else ""))
    lines.append("Bodies are not walls — wanderers move if you wait, but trainers never move.")
    lines.append(f"PARTY: {rig.party()}   BADGES byte: 0b{rig.badges():08b}")
    text = rig.dialogue()
    if text:
        lines.append(f"TEXT ON SCREEN: {text!r}")
    for note in notes or []:
        lines.append(f"OBSERVED: {note}")
    return "\n".join(lines)


class TapesConsult:
    """Ask the seated crew member through the tapes proxy; an unparsed reply is a non-answer.

    Every model call goes to :42345 (``expedition_crew.TAPES_CHAT_URL``). A call straight to
    ollama on :11434 is an uncaptured session, which the doctrine forbids — so the URL is not a
    parameter a caller can casually redirect, it is the crew module's constant.
    """

    def __init__(self, *, timeout: float = 120.0, log=print) -> None:
        self.timeout = timeout
        self.log = log

    def __call__(self, tier: str, facts: str, menu: list[str]) -> tuple[str | None, str, str]:
        import urllib.error
        import urllib.request

        import expedition_crew as crew

        seat = crew.seat_for(tier)
        prompt = crew.build_prompt(facts, menu)
        body = json.dumps(crew.chat_body(seat["model"], prompt)).encode()
        req = urllib.request.Request(
            crew.TAPES_CHAT_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            self.log(f"  consult FAILED ({seat['title']}, {seat['model']}): {exc}")
            return None, f"consult failed: {exc}", seat["model"]
        action, why = crew.parse_decision(crew.extract_text(payload), menu)
        self.log(f"  {seat['title']} ({seat['model']}) -> {action or 'NO-ANSWER'}: {why[:120]}")
        return action, why, seat["model"]


class LegRunner:
    """One leg: boot to goal, supervised. Deterministic Python moves; the crew only chooses."""

    def __init__(
        self,
        rig,
        *,
        goal: int,
        budget_s: float = 7200,
        consult=None,
        clock=time.monotonic,
        log=print,
        max_hops: int = DEFAULT_MAX_HOPS,
        engage: bool = False,
        engage_rounds: int = DEFAULT_ENGAGE_ROUNDS,
        learnings_dir: Path | None = None,
    ) -> None:
        self.rig = rig
        self.goal = goal
        self.budget_s = budget_s
        self.consult = consult if consult is not None else TapesConsult(log=log)
        self.clock = clock
        self.log = log
        self.max_hops = max_hops
        self.engage = engage
        self.engage_rounds = engage_rounds
        self.learnings_dir = learnings_dir or LEARNINGS_DIR
        self.attempts: Counter = Counter()  # wall id -> attempts spent on it
        self.tried: list[str] = []  # every action executed, for the exhaustion record
        self.notes: list[str] = []  # measured observations that feed the next consult
        self.consults: list[dict] = []

    # ---- one hop ---------------------------------------------------------------------------

    def _hop(self, hop: dict) -> str | None:
        """Attempt one routed hop. Returns None on progress, else the measured failure code."""
        cur = self.rig.pos()[0]
        result = self.rig.cross(cur, hop["to"]) if hop["via"] == "edge" else self.rig.warp(cur, hop["x"], hop["y"])
        now = self.rig.pos()[0]
        if now == hop["to"]:
            return None
        if now != cur:  # an interior swallowed the hop — a gate room, not a failure
            self.log(f"  interior {now} swallowed the hop")
            inner = self.rig.traverse(now)
            if self.rig.pos()[0] != now:
                return None
            return f"interior-{inner}"
        return str(result)

    # ---- the bounded actions ----------------------------------------------------------------

    def _act(self, action: str, hop: dict | None) -> None:
        import road
        import rom_truth as rt

        cur, x, y = self.rig.pos()
        self.tried.append(f"{action} on map {cur} at ({x}, {y})")
        if action == "RETRY_SAME":
            return  # the loop re-attempts the hop; a stall is often one attempt deep
        if action == "WAIT_FOR_BODIES":
            self.rig.io.wait(BODY_WAIT_FRAMES)
            return
        if action == "TRY_FAR_EDGE_CELL" and hop and hop["via"] == "edge":
            cells, _direction = road.edge_cells(self.rig.truth, cur, hop["to"])
            if cells:
                far = max(cells, key=lambda c: abs(c[0] - x) + abs(c[1] - y))
                self.log(f"  aiming at far edge cell {far}")
                self.rig.walk(cur, {far}, cap=200)
                self.rig.cross(cur, hop["to"])
            return
        if action == "USE_GATE_WARP":
            targets = set()
            if hop and hop["via"] == "edge":
                try:
                    targets, _d = road.edge_cells(self.rig.truth, cur, hop["to"])
                except (StopIteration, KeyError):
                    targets = set()
            if not targets:
                targets = {(w[0], w[1]) for w in self.rig.truth["maps"][str(cur)]["warps"]}
            self.rig.gate(cur, targets)
            return
        if action == "BACK_OUT_AND_REENTER":
            warps = self.rig.truth["maps"].get(str(cur), {}).get("warps", [])
            if not warps:
                self.notes.append(f"map {cur} has no warps to back out through")
                return
            wx, wy, _dst, _wid = min(warps, key=lambda w: abs(w[0] - x) + abs(w[1] - y))
            self.rig.warp(cur, wx, wy)
            inside = self.rig.pos()[0]
            if inside != cur:
                self.rig.traverse(inside, exclude_entry=False)
            return
        if action == "TALK_TO_BLOCKER":
            bodies = self.rig.bodies()
            if not bodies:
                self.notes.append("no live body to talk to — the block is terrain or a script, not a sprite")
                return
            bx, by = min(bodies, key=lambda b: abs(b[0] - x) + abs(b[1] - y))
            adjacent = {(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)}
            if (x, y) not in adjacent:
                self.rig.walk(cur, adjacent, cap=120)
                _, x, y = self.rig.pos()
            face = "right" if bx > x else "left" if bx < x else "down" if by > y else "up"
            said = self.rig.talk(face)
            self.log(f"  blocker at ({bx}, {by}) says: {said[:160]}")
            self.notes.append(f"the body at ({bx}, {by}) says: {said[:300]}")
            return
        if action == "TRY_FAR_EDGE_CELL":  # warp hop: the menu should not have offered it
            self.notes.append("TRY_FAR_EDGE_CELL is meaningless on a warp hop")
            return
        # An action outside the menu is a parser bug, not a move: say so rather than acting.
        self.notes.append(f"unknown action {action!r} — nothing executed")
        _ = rt  # imported for symmetry with describe(); the actions above use `road`

    # ---- the gym engage ---------------------------------------------------------------------

    def _engage_until_badge(self) -> bool:
        """On the goal map, talk bodies down until the BADGES byte changes.

        The badge byte is watched for *change*, not for a remembered bit: which bit belongs to
        which leader is exactly the kind of recalled fact this project has been burned by. A
        changed byte is measurement; a named bit would be recall.
        """
        before = self.rig.badges()
        spoken: set[tuple[int, int]] = set()
        for _ in range(self.engage_rounds):
            if self.rig.badges() != before:
                return True
            mp, x, y = self.rig.pos()
            fresh = [b for b in self.rig.bodies() if b not in spoken]
            if not fresh:
                return self.rig.badges() != before
            bx, by = min(fresh, key=lambda b: abs(b[0] - x) + abs(b[1] - y))
            spoken.add((bx, by))
            adjacent = {(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)}
            if (x, y) not in adjacent:
                self.rig.walk(mp, adjacent, cap=160)
                _, x, y = self.rig.pos()
                if self.rig.pos()[0] != mp:  # a fight or a warp moved us; re-read next round
                    continue
            if (x, y) not in adjacent:
                continue
            face = "right" if bx > x else "left" if bx < x else "down" if by > y else "up"
            said = self.rig.talk(face)
            self.log(f"  engaged ({bx}, {by}): {said[:140]}")
            self.rig.emit("supervisor.engaged", pos=[bx, by], said=said[:300], badges=self.rig.badges())
        return self.rig.badges() != before

    # ---- the exhaustion record ---------------------------------------------------------------

    def write_exhaustion(self, failure: str, hop: dict | None) -> Path:
        import expedition_crew as crew

        mp, x, y = self.rig.pos()
        where = f"map {mp} ({x}, {y}) -> goal {self.goal}"
        doc = crew.failure_doc(
            self.rig.run_id,
            f"reach map {self.goal}",
            where,
            describe(self.rig, self.goal, hop, failure, self.notes),
            self.tried,
        )
        self.learnings_dir.mkdir(parents=True, exist_ok=True)
        path = self.learnings_dir / f"map{mp}-to-{self.goal}-stuck-{self.rig.run_id}.md"
        path.write_text(doc)
        self.rig.emit(
            "supervisor.exhausted", goal=self.goal, pos=[mp, x, y], failure=failure, doc=str(path), tried=self.tried
        )
        self.log(f"EXHAUSTED — record written to {path}")
        return path

    # ---- the leg -----------------------------------------------------------------------------

    def run(self) -> dict:
        import rom_truth as rt

        started = self.clock()
        self.rig.emit("supervisor.leg_start", goal=self.goal, pos=list(self.rig.pos()), budget_s=self.budget_s)
        for _ in range(self.max_hops):
            elapsed = self.clock() - started
            if elapsed >= self.budget_s:
                return self._finish("budget", f"budget of {self.budget_s:.0f}s spent")
            cur = self.rig.pos()[0]
            if cur == self.goal:
                if self.engage and not self._engage_until_badge():
                    return self._finish("engaged-no-badge", "arrived, engaged every body, badge byte unchanged")
                return self._finish("arrived", f"reached map {self.goal}")
            chain = rt.route(self.rig.truth, cur, self.goal)
            hop = chain[0] if chain else None
            if hop is None:
                failure = "no-route"
            else:
                self.log(f"hop: {cur} --{hop['via']}--> {hop['to']}")
                failure = self._hop(hop)
                if failure is None:
                    continue  # progress: the wall counter for the next hop starts clean
            wall = f"{cur}->{hop['to'] if hop else self.goal}"
            self.attempts[wall] += 1
            attempt = self.attempts[wall]
            self.log(f"hop failed: {failure} (attempt {attempt}/{LADDER_ATTEMPTS} on {wall})")
            self.rig.emit("supervisor.hop_failed", wall=wall, failure=failure, attempt=attempt)
            if attempt > LADDER_ATTEMPTS:
                self.write_exhaustion(failure, hop)
                return self._finish("exhausted", f"the ladder ended on {wall} ({failure})")
            tier = "navigation" if attempt <= NAV_ATTEMPTS else "puzzle"
            menu = menu_for(failure, edge_hop=bool(hop and hop["via"] == "edge"))
            action, why, model = self.consult(tier, describe(self.rig, self.goal, hop, failure, self.notes), menu)
            self.consults.append({"wall": wall, "tier": tier, "model": model, "action": action, "why": why})
            self.rig.emit("supervisor.consult", wall=wall, tier=tier, model=model, action=action or "", why=why[:300])
            if action is None:
                self.notes.append(f"the {tier} seat returned no menu action; retrying the hop unchanged")
                continue  # a non-answer costs the attempt it already cost, and nothing else
            if action == "GIVE_UP":
                self.write_exhaustion(failure, hop)
                return self._finish("gave-up", f"the {tier} seat chose GIVE_UP on {wall}")
            self._act(action, hop)
        return self._finish("max-hops", f"{self.max_hops} hops without arriving")

    def _finish(self, outcome: str, reason: str) -> dict:
        mp, x, y = self.rig.pos()
        result = {
            "ok": outcome == "arrived",
            "outcome": outcome,
            "reason": reason,
            "goal": self.goal,
            "pos": [mp, x, y],
            "badges": self.rig.badges(),
            "consults": self.consults,
            "run_id": self.rig.run_id,
        }
        self.rig.emit("supervisor.leg_end", **{k: v for k, v in result.items() if k != "consults"})
        self.log(f"LEG {outcome}: {reason} — at {(mp, x, y)}, badges 0b{self.rig.badges():08b}")
        return result


def parse_goals(text: str) -> list[int]:
    """``--goal 10,181,178`` — one booted cartridge, a chain of legs, banked between each."""
    return [int(part) for part in str(text).replace(" ", "").split(",") if part]


def cmd_run(args) -> int:
    """Boot a baton and drive the supervised leg chain. This is the loop body the skill promises.

    One boot, N goals: the campaign shape. Each goal gets its share of the remaining budget, the
    state is banked after every cleared goal (so a failure never costs the legs that worked), and
    the chain stops at the first leg that does not arrive — the record for that wall is already
    written by then.
    """
    from expedition_rig import BattleWedge, Rig

    goals = parse_goals(args.goal)
    rig = Rig(args.state, live_label=args.live_label)
    print(f"start {rig.pos()} badges 0b{rig.badges():08b} {rig.party()}", flush=True)
    consult = (lambda tier, facts, menu: (None, "consults disabled", "none")) if args.no_consult else None
    started, results = time.monotonic(), []
    for index, goal in enumerate(goals, start=1):
        left = args.budget - (time.monotonic() - started)
        if left <= 0:
            print(f"budget spent before leg {index}/{len(goals)} (goal {goal})", flush=True)
            break
        share = left if index == len(goals) else left / (len(goals) - index + 1)
        print(f"\n=== leg {index}/{len(goals)}: goal map {goal}, {share / 60:.0f}m ===", flush=True)
        runner = LegRunner(
            rig,
            goal=goal,
            budget_s=share,
            # Engaging is what turns arrival into a badge, so it belongs to the last goal only:
            # a mid-chain city is a waypoint, and talking to every body in it is not the leg.
            engage=args.engage and index == len(goals),
            consult=consult,
        )
        try:
            result = runner.run()
        except BattleWedge as exc:
            result = {"ok": False, "outcome": "battle-wedge", "reason": str(exc), "pos": list(rig.pos())}
        results.append({k: v for k, v in result.items() if k != "consults"})
        if args.bank:
            rig.bank(args.bank if len(goals) == 1 else f"{args.bank}-{goal}")
        if not result.get("ok"):
            break
    if args.bank and results and results[-1].get("ok"):
        rig.bank(args.bank)
    rig.finish(outcome=results[-1]["outcome"] if results else "no-legs", goals=str(goals))
    print(json.dumps({"legs": results, "badges": rig.badges(), "pos": list(rig.pos()), "run_id": rig.run_id}))
    return 0 if results and all(r["ok"] for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rn = sub.add_parser("run", help="drive one supervised leg from a baton to a goal map")
    rn.add_argument("--state", required=True, help="baton .state to boot from")
    rn.add_argument("--goal", required=True, help="goal map id, or a comma-separated chain (10,181,178)")
    rn.add_argument("--budget", type=float, default=7200.0, help="seconds for the whole chain")
    rn.add_argument("--bank", default=None, help="bank the end state under this name")
    rn.add_argument("--live-label", default=None, help="stream to the viewer under this label")
    rn.add_argument("--engage", action="store_true", help="on arrival, engage bodies until the BADGES byte changes")
    rn.add_argument("--no-consult", action="store_true", help="deterministic only — never call a model")
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
    if args.cmd == "run":
        return cmd_run(args)
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
