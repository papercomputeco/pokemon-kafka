"""The Rig — one booted cartridge, wired for a supervised leg.

This is the scratchpad harness that won badges 4 and 5 (``data/local_runs/roster-bench/
expedition.py``), promoted into ``scripts/`` because the doctrine says so: *fix the engine, do
not fork the scratchpad*. A leg that lives in ``data/`` teaches the repo nothing, and six of
them in a day is how 2026-08-30 went.

What the Rig owns, and nothing else:

* **Boot.** A baton ``.state`` loaded into ``PokemonAgent``'s PyBoy, plus the extracted truth
  and its tile pairs. The agent supplies the battle turn (catch hook, potions, forced switch,
  evolution guard) that ``road`` delegates to.
* **Recording.** With ``live_label=`` every button press is a turn, every turn a frame, and the
  ``runs/<id>/`` folder grows while we play — the viewer reads it live (no ``summary.json`` yet
  means "running"). ``EmuIO.press`` and ``GameController.press`` have different signatures, so
  the wrapper passes ``*a, **kw`` through; a wrapper that does not is the measured way to break
  ``road``'s ``press(dir, hold=8, release=8)``.
* **Telemetry.** Every leg emits to ``data/telemetry/game/<UTC-date>.jsonl`` under a stable
  ``run_id``. A run that does not emit is unminable, which is the whole reason the sink exists.
* **Reads.** Position, party, badges, dialogue — measured from RAM, never assumed.

A battle that will not end is a ``BattleWedge``, not a ``sys.exit``: the supervisor owns what
happens after a failure, and a harness that kills the process denies it that.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:  # the Rig is imported from repo root and from scripts/ alike
    sys.path.insert(0, str(SCRIPT_DIR))

import quartermaster as qm  # noqa: E402
import road  # noqa: E402
import rom_truth as rt  # noqa: E402

ROM_DEFAULT = WORKSPACE / "rom" / "pokemon_red.gb"
BATON_DIR = WORKSPACE / "data" / "local_runs" / "roster-bench"
TELEMETRY_DIR = WORKSPACE / "data" / "telemetry" / "game"
RUNS_DIR = WORKSPACE / "runs"
VIEWER_WS = "ws://127.0.0.1:8201"

ADDR_BADGES = 0xD356  # game_profile.RED_BLUE.addr_badges
ADDR_FACING = 0xC109  # the player's facing — part of the state key on any tile-driven floor
ADDR_PARTY_COUNT, ADDR_PARTY_STRUCTS, PARTY_STRUCT_SIZE = 0xD163, 0xD16B, 44
ADDR_BAG_COUNT, ADDR_BAG_ITEMS = 0xD31D, 0xD31E  # quartermaster's, verified live in the mart probe
BAG_SLOTS = 20  # a full bag refuses pickups silently (measured in the Rocket Hideout)
ADDR_LIST_SCROLL = 0xCC36  # item-list scroll offset; 0xCC26 is the cursor WITHIN the 3-row window
BATTLE_TURN_CAP = 200  # a battle past this is wedged, not long


class BattleWedge(RuntimeError):
    """A battle that would not end. The state is banked; the supervisor decides what next."""


def telemetry_path(now: datetime | None = None, root: Path | None = None) -> Path:
    """The sink line for today. One file per UTC date — the shape the benchmarks glob."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return (root or TELEMETRY_DIR) / f"{stamp}.jsonl"


def emit_event(run_id: str, event: str, fields: dict | None = None, *, root: Path | None = None) -> dict:
    """Append one expedition event to the game sink and return the record written."""
    import expedition_crew as crew

    record = crew.telemetry_record(run_id, event, fields)
    path = telemetry_path(root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


class Rig:
    """A loaded cartridge plus the road engine, recording and emitting as it plays."""

    def __init__(
        self,
        state: str | Path,
        *,
        live_label: str | None = None,
        frame_interval: int = 1,
        viewer_ws: str = VIEWER_WS,
        rom: str | Path = ROM_DEFAULT,
        run_id: str | None = None,
        telemetry_root: Path | None = None,
        settle_on_boot: bool = True,
    ) -> None:
        from agent import PokemonAgent

        self.ag = PokemonAgent(str(rom))
        with open(state, "rb") as fh:
            self.ag.pyboy.load_state(fh)
        self.pb = self.ag.pyboy
        self.mem = self.pb.memory
        self.ctl = self.ag.controller
        self.mr = self.ag.memory
        self.io = qm.EmuIO(self.pb)
        self.truth = rt.load_truth()
        self.pairs = rt.loaded_pairs(self.truth)
        self.ag.catch_wanted = set()  # a leg is travel, not a hunt; the quartermaster arms catching
        self.turn = 0
        self.recorder = None
        self.telemetry_root = telemetry_root
        self.run_id = run_id or uuid.uuid4().hex[:12]
        if live_label:
            self._go_live(live_label, frame_interval, viewer_ws)
        if settle_on_boot and not self.settle():
            print("  WARNING: the baton would not settle — a textbox is still parking movement", flush=True)

    # ---- wiring ---------------------------------------------------------------------------

    def _go_live(self, label: str, frame_interval: int, viewer_ws: str) -> None:
        from game_events import GameEventCollector
        from live_producer import LiveProducer
        from PIL import Image
        from recorder import RunRecorder

        run_id = RunRecorder.new_run_id(datetime.now(timezone.utc), uuid.uuid4().hex[:4])
        self.run_id = run_id
        producer = LiveProducer(f"{viewer_ws}/ws/produce/{run_id}", run_id)
        self.recorder = RunRecorder(
            run_id,
            RUNS_DIR,
            frame_grabber=lambda: Image.fromarray(self.pb.screen.ndarray),
            frame_interval=frame_interval,
            live=producer.send,
        )
        self.ag.collector = GameEventCollector(recorder=self.recorder, game=self.ag.profile.name, run_id=run_id)
        self.recorder.start({"label": label, "rom": str(ROM_DEFAULT)})

        def wrap(press_fn):
            def press(button, *a, **kw):  # EmuIO.press and GameController.press differ — pass through
                press_fn(button, *a, **kw)
                self.turn += 1
                self.ag.turn_count = self.turn  # events and frames share one clock
                self.recorder.tick(self.turn)

            return press

        self.ctl.press = wrap(self.ctl.press)
        self.io.press = wrap(self.io.press)
        print(f"LIVE RUN {run_id} -> http://127.0.0.1:8201/run/{run_id}", flush=True)

    def emit(self, event: str, **fields) -> dict:
        return emit_event(self.run_id, event, fields, root=self.telemetry_root)

    def finish(self, **summary) -> None:
        if self.recorder is not None:
            summary.setdefault("turns", self.turn)
            summary.setdefault("party", str(self.party()))
            summary.setdefault("pos", str(self.pos()))
            self.recorder.finish(summary)

    # ---- measured reads -------------------------------------------------------------------

    def pos(self) -> tuple[int, int, int]:
        return self.mem[0xD35E], self.mem[0xD362], self.mem[0xD361]

    def settled_pos(self, tries: int = 8) -> tuple[int, int, int]:
        """A position the world agrees with: stable across ticks, and inside the map's own bounds.

        A map transition writes the new map id before the coordinates catch up, so a raw read
        taken inside that window names a tile that cannot exist. Measured twice: a leg announced
        arrival at (234, 17, 11) on a map 16 tiles wide and then banked back on the floor below,
        and a baton banked at (7, 5, 28) booted as (157, 5, 27).
        """
        last = self.pos()
        for _ in range(tries):
            m = self.truth["maps"].get(str(last[0]))
            inside = m is None or (last[1] < m["width"] and last[2] < m["height"])
            self.io.wait(20)
            now = self.pos()
            if now == last and inside:
                return now
            last = now
        return last

    def badges(self) -> int:
        return self.mem[ADDR_BADGES]

    def bag(self) -> list[tuple[int, int]]:
        """The bag as (item id, quantity) pairs — the only honest proof a pickup happened."""
        count = self.mem[ADDR_BAG_COUNT]
        return [(self.mem[ADDR_BAG_ITEMS + 2 * i], self.mem[ADDR_BAG_ITEMS + 2 * i + 1]) for i in range(count)]

    def bag_full(self) -> bool:
        """The bag caps at 20 slots, and a full bag silently refuses pickups.

        Measured in the Rocket Hideout: tossing a whole stack frees a slot, a quantity-1 toss
        does not. A sweep that does not check this reports "collected nothing" and looks like a
        map problem.
        """
        return self.mem[ADDR_BAG_COUNT] >= BAG_SLOTS

    def item_name(self, item_id: int) -> str:
        """What the cartridge calls this id. TMs/HMs live past the name list and keep their id."""
        return self.truth.get("items", {}).get(str(item_id), f"#{item_id}")

    def bag_named(self) -> list[tuple[str, int]]:
        return [(self.item_name(item), qty) for item, qty in self.bag()]

    def toss_stack(self, item_id: int) -> bool:
        """Free a slot by tossing a whole stack: START -> ITEM -> the slot -> TOSS -> all of it.

        Measured in the Rocket Hideout: tossing a *whole stack* frees the slot, a quantity-1 toss
        does not — so callers pick a stack, not an item. Every phase is confirmed from RAM, never
        from timing: the verdict is the bag's slot count dropping.
        """
        before = len(self.bag())
        found = next(((i, q) for i, (item, q) in enumerate(self.bag()) if item == item_id), None)
        if found is None:
            return False
        slot, qty = found
        self.ctl.press("start")
        self.ctl.wait(40)
        for _ in range(8):  # ITEM sits below POKeMON in the field menu; walk the cursor onto it
            if self.mem[qm.ADDR_MENU_CUR] == 2:
                break
            self.ctl.press("down" if self.mem[qm.ADDR_MENU_CUR] < 2 else "up")
            self.ctl.wait(15)
        self.ctl.press("a")
        self.ctl.wait(50)
        # The item list shows three rows at a time: 0xCC26 is the cursor *within that window* and
        # caps at 2, while 0xCC36 is the scroll offset. The slot we want is their sum. Comparing
        # the cursor alone to the slot index silently stops on slot 2 and tosses the wrong thing —
        # or, here, nothing at all.
        for _ in range(2 * (slot + len(self.bag()) + 4)):
            here = self.mem[ADDR_LIST_SCROLL] + self.mem[qm.ADDR_MENU_CUR]
            if here == slot:
                break
            self.ctl.press("down" if here < slot else "up")
            self.ctl.wait(15)
        if self.mem[ADDR_LIST_SCROLL] + self.mem[qm.ADDR_MENU_CUR] != slot:
            for _ in range(6):
                self.ctl.press("b")
                self.ctl.wait(25)
            return False
        self.ctl.press("a")
        self.ctl.wait(50)
        for _ in range(6):  # the item submenu: USE / TOSS — TOSS is the lower row
            if self.mem[qm.ADDR_MENU_CUR] == 1:
                break
            self.ctl.press("down")
            self.ctl.wait(15)
        self.ctl.press("a")
        self.ctl.wait(50)
        # The quantity picker starts at 1 and WRAPS. Holding up a fixed number of times is how
        # you ask for the whole stack and get one unit instead: twelve presses on a six-stack
        # lands back on 1, and a quantity-1 toss frees no slot — the very thing this method
        # exists to avoid. Press exactly what the stack holds.
        for _ in range(max(0, qty - 1)):
            self.ctl.press("up")
            self.ctl.wait(12)
        for _ in range(3):  # confirm the count, answer the "Is it OK to toss?" box, dismiss it
            self.ctl.press("a")
            self.ctl.wait(45)
        for _ in range(6):
            self.ctl.press("b")
            self.ctl.wait(30)
        return len(self.bag()) < before

    def make_room(self) -> bool:
        """Toss the largest stack so a pickup can land. Returns True if a slot came free.

        Which items are safe to lose is not a judgement this makes from lore: quantity is the
        measured signal. Key items are single-copy, consumables come in stacks, so the biggest
        stack is both the most expendable and the one whose loss costs the least.
        """
        stacks = [(qty, item) for item, qty in self.bag() if qty > 1]
        if not stacks:
            print("  bag is full and holds no stack to toss — every slot is a single item", flush=True)
            return False
        qty, item = max(stacks)
        print(f"  bag full: tossing {qty}x {self.item_name(item)} to free a slot", flush=True)
        freed = self.toss_stack(item)
        # Backing out of the ITEM menu is not the same as the world accepting input again, and a
        # pickup that starts inside a half-closed menu sends its A presses to the menu. Measured:
        # a slot was freed on Silph 2F and the very next collect_item still came back empty.
        self.settle()
        self.emit("supervisor.tossed", item=self.item_name(item), qty=qty, freed=freed)
        return freed

    def item_balls(self, map_id: int) -> list[tuple[int, int]]:
        """Where this cartridge says the item balls are on a map — extracted, never recalled."""
        sprites = self.truth["maps"].get(str(map_id), {}).get("sprites", [])
        return [(s["x"], s["y"]) for s in sprites if s.get("kind") == "item"]

    def collect_item(self, bx: int, by: int) -> bool:
        """Pick up one item ball: stand beside it, face it, press A. Bag growth is the verdict.

        Item-ball sprites can be invisible and walk-through-able — the Rocket Hideout's LIFT KEY
        was listed in the live sprite table the whole time while the engine let us walk over its
        tile. So the approach is a cell *beside* the ball, never the ball itself, and the pickup
        is confirmed from the bag rather than from anything on screen.
        """
        mp, x, y = self.pos()
        if self.bag_full() and not self.make_room():
            print(f"  bag is full ({BAG_SLOTS} slots) and no slot could be freed", flush=True)
            return False
        adjacent = {(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)}
        if (x, y) not in adjacent:
            near = road.reachable(self.truth, self.pairs, mp, (x, y), self.bodies() - {(bx, by)}) & adjacent
            if not near:
                return False
            self.walk(mp, near, cap=400)
            mp, x, y = self.pos()
            if (x, y) not in adjacent:
                return False
        before = self.bag()
        self.ctl.press("right" if bx > x else "left" if bx < x else "down" if by > y else "up")
        self.ctl.wait(25)
        for _ in range(4):
            self.ctl.press("a")
            self.ctl.wait(45)
        for _ in range(3):
            self.ctl.press("b")
            self.ctl.wait(25)
        return self.bag() != before

    def party(self) -> list[tuple[str, int, int]]:
        from memory_reader import SPECIES_ID_MAP

        base = ADDR_PARTY_STRUCTS
        return [
            (
                SPECIES_ID_MAP.get(self.mem[base + PARTY_STRUCT_SIZE * i], "?"),
                self.mem[base + PARTY_STRUCT_SIZE * i + 33],
                (self.mem[base + PARTY_STRUCT_SIZE * i + 1] << 8) | self.mem[base + PARTY_STRUCT_SIZE * i + 2],
            )
            for i in range(self.mem[ADDR_PARTY_COUNT])
        ]

    def dialogue(self) -> str:
        try:
            return self.mr.read_dialogue().strip()
        except Exception:  # a text buffer mid-redraw is not a leg failure
            return ""

    # ---- moving ---------------------------------------------------------------------------

    def warp_tiles(self, map_id: int) -> set[tuple[int, int]]:
        return {(w[0], w[1]) for w in self.truth["maps"].get(str(map_id), {}).get("warps", [])}

    def probe_step(self) -> bool:
        """One step and its undo — the only honest proof the world is accepting input.

        A textbox does not always leave text in the buffer (the buffer stays *stale* after boxes
        close, measured), so "is there dialogue" cannot answer "can we move". Actually moving can.

        A door is not a floor. The badge-6 leg booted a baton standing one tile below Fuchsia
        gym's mat, probed *up* onto it, and warped straight back into the gym it had just left —
        the same doctrine ``road.walk(avoid_warps=True)`` already follows, missing here. Warp
        neighbours are the last resort, and only because a state wedged in a doorway still has to
        be able to prove it accepts input.
        """
        mp, x, y = self.pos()
        warps = self.warp_tiles(mp)
        deltas = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
        order = [("down", "up"), ("up", "down"), ("left", "right"), ("right", "left")]
        floors = [(d, b) for d, b in order if (x + deltas[d][0], y + deltas[d][1]) not in warps]
        for direction, back in floors + [p for p in order if p not in floors]:
            before = self.pos()
            self.io.press(direction, hold=8, release=8)
            self.io.wait(30)
            after = self.pos()
            if after != before:
                if after[0] == before[0]:  # a map change is a warp we could not avoid: leave it be
                    self.io.press(back, hold=8, release=8)
                    self.io.wait(30)
                return True
        return False

    def settle(self, max_rounds: int = 16) -> bool:
        """Flush a parked textbox so a baton can move.

        A state banked mid-dialogue cannot walk: every direction is swallowed while the box is
        up. Measured on ``BADGE5.state`` — banked on Koga's TM line ("Make space for this,
        child!"), it refused all four steps, and a leg booted from it fingerprinted a wall that
        was never in the world. The recovery is the measured one: A advances the pages, B closes
        whatever A opened, and a probe step is the proof.
        """
        for _ in range(max_rounds):
            if self.mem[qm.ADDR_IN_BATTLE]:
                self.battle()
                continue
            if self.probe_step():
                return True
            self.ctl.press("a")
            self.ctl.wait(40)
            self.ctl.press("b")
            self.ctl.wait(30)
        return self.probe_step()

    def battle(self, io=None) -> None:
        """The agent's full battle turn until the fight ends; a stuck fight is a wedge."""
        self.ag._catch_enemy = None
        self.ag._catch_throws = 0
        turns = 0
        while self.mem[qm.ADDR_IN_BATTLE] and turns < BATTLE_TURN_CAP:
            self.ag.run_battle_turn()
            turns += 1
            if turns in (60, 110, 160):
                self.ag._recover_battle_wedge()
        if self.mem[qm.ADDR_IN_BATTLE]:
            self.bank("wedge")
            self.emit("battle.wedge", pos=list(self.pos()), turns=turns)
            raise BattleWedge(f"battle did not end in {turns} turns; banked wedge.state")

    def walk(self, map_id: int, targets, **kw):
        kw.setdefault("battle", self.battle)
        return road.walk(self.io, self.truth, self.pairs, map_id, targets, **kw)

    def drive(self, dst: int, **kw):
        kw.setdefault("battle", self.battle)
        kw.setdefault("log", lambda msg: print("  " + msg, flush=True))
        return road.drive_to(self.io, self.truth, self.pairs, dst, **kw)

    def warp(self, map_id: int, wx: int, wy: int, **kw):
        kw.setdefault("battle", self.battle)
        return road.through_warp(self.io, self.truth, self.pairs, map_id, wx, wy, **kw)

    def cross(self, cur: int, nxt: int, **kw):
        kw.setdefault("battle", self.battle)
        return road.cross_edge(self.io, self.truth, self.pairs, cur, nxt, **kw)

    def traverse(self, interior: int, **kw):
        """Leave a swallowed-hop interior by the mats on another side (a gate room, a house)."""
        kw.setdefault("battle", self.battle)
        return road.traverse_interior(self.io, self.truth, self.pairs, interior, **kw)

    def gate(self, cur: int, goal_cells, **kw):
        """Cross a route severed by its own gate building, validating each candidate door."""
        kw.setdefault("battle", self.battle)
        return road.pass_gate(self.io, self.truth, self.pairs, cur, goal_cells, **kw)

    def bodies(self) -> set[tuple[int, int]]:
        return road.live_bodies(self.io)

    def talk(self, face: str) -> str:
        """Face and read: the pages a body gives up. What the game says IS the instruction stream."""
        self.ctl.press(face)
        self.ctl.wait(25)
        self.ctl.press("a")
        pages: list[str] = []
        for _ in range(80):
            self.pb.tick()
            text = self.dialogue()
            if text and (not pages or text != pages[-1]):
                pages.append(text)
        for _ in range(3):
            self.ctl.press("a")
            self.ctl.wait(45)
            text = self.dialogue()
            if text and (not pages or text != pages[-1]):
                pages.append(text)
            if self.mem[qm.ADDR_IN_BATTLE]:
                self.battle()
                break
        for _ in range(4):
            self.ctl.press("b")
            self.ctl.wait(25)
        return " | ".join(pages[-4:])

    # ---- the oracle -------------------------------------------------------------------------

    def oracle_goto(self, goal_test, max_states: int = 500) -> bool:
        """BFS over press-and-settle transitions, using the game itself as the oracle.

        The mover for floors where planned walking is a category error: spin tiles, teleport
        pads, ice — anywhere the tile decides where you end up. Rocket Hideout B4 stood against
        an 880-state position-keyed oracle for weeks and fell in 721 states once **facing**
        entered the state key, because spin-tile movement reads 0xC109 and a position-only key
        prunes exactly the hold-arrivals the maze is made of.

        ``goal_test(pos) -> bool`` decides arrival. A failed search never strands the run at a
        random explored state — the origin is restored.
        """
        import io as _io
        from collections import deque

        def snap():
            buf = _io.BytesIO()
            self.pb.save_state(buf)
            return buf

        def load(buf):
            buf.seek(0)
            self.pb.load_state(buf)

        def key():
            return (*self.pos(), self.mem[ADDR_FACING])

        def press_settle(direction):
            self.pb.button(direction, delay=8)
            for _ in range(8):
                self.pb.tick()
            last, stable = self.pos(), 0
            for _ in range(40):
                for _ in range(10):
                    self.pb.tick()
                now = self.pos()
                if now == last:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable, last = 0, now
            return self.pos()

        if goal_test(self.pos()):
            return True
        origin = snap()
        seen = {key()}
        queue = deque([(key(), origin)])
        states = 0
        while queue and states < max_states:
            _state, snapshot = queue.popleft()
            for direction in ("down", "left", "right", "up"):
                load(snapshot)
                landed = press_settle(direction)
                if self.mem[qm.ADDR_IN_BATTLE]:
                    self.battle()
                    landed = self.pos()
                if goal_test(landed):
                    # Let the world finish. A warp fired by the settling step changes the map id
                    # before the coordinates catch up, and returning inside that window reports a
                    # position that cannot exist — the badge-6 leg announced arrival at
                    # (234, 17, 11) on a map only 16 tiles wide, then banked back on 209.
                    self.io.wait(90)
                    return True
                states += 1
                if key() not in seen:
                    seen.add(key())
                    queue.append((key(), snap()))
        load(origin)
        self.emit("oracle.exhausted", states=states, keys=len(seen), pos=list(self.pos()))
        return False

    # ---- banking --------------------------------------------------------------------------

    def bank(self, name: str, *, directory: Path | None = None) -> Path:
        """Bank a baton the next leg can actually boot.

        Two states are worthless as batons and both were paid for: one banked mid-dialogue (every
        step swallowed) and one banked standing ON a warp mat, which boots back through the door
        it just came out of. Settle first, step off the door if we are on it, then save.
        """
        self.settle()
        mp, x, y = self.pos()
        if (x, y) in self.warp_tiles(mp):
            self.probe_step()  # step off the mat; the undo is skipped when the step warps
            if self.pos()[:1] == (mp,) and self.pos()[1:] != (x, y):
                print(f"  stepped off the {mp} warp mat at ({x}, {y}) before banking", flush=True)
        path = (directory or BATON_DIR) / f"{name}.state"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            self.pb.save_state(fh)
        print(f"  banked {path.name} at {self.pos()}", flush=True)
        return path

    def shot(self, path: str | Path) -> Path:
        from PIL import Image

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(self.pb.screen.ndarray).save(out)
        return out
