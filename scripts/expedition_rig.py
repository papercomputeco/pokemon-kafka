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
if str(SCRIPT_DIR) not in sys.path:  # pragma: no cover - the Rig is imported from repo root and scripts/ alike
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
    ) -> None:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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
        self.unlock_gates()
        if live_label:
            self._go_live(live_label, frame_interval, viewer_ws)
        if settle_on_boot and not self.settle():
            print("  WARNING: the baton would not settle — a textbox is still parking movement", flush=True)

    # ---- wiring ---------------------------------------------------------------------------

    def _go_live(
        self, label: str, frame_interval: int, viewer_ws: str
    ) -> None:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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

    def finish(self, **summary) -> None:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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

    def toss_stack(
        self, item_id: int
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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
        for _ in range(6):  # never press START onto an already-open menu: close first, then open
            self.ctl.press("b")
            self.ctl.wait(25)
        self.ctl.press("start")
        self.ctl.wait(50)
        for _ in range(8):  # ITEM sits below POKeMON in the field menu; walk the cursor onto it
            if self.mem[qm.ADDR_MENU_CUR] == 2:
                break
            self.ctl.press("down" if self.mem[qm.ADDR_MENU_CUR] < 2 else "up")
            self.ctl.wait(20)
        self.ctl.press("a")
        self.ctl.wait(60)
        # The item list shows three rows at a time: 0xCC26 is the cursor *within that window* and
        # caps at 2, while 0xCC36 is the scroll offset. The slot we want is their sum. Comparing
        # the cursor alone to the slot index silently stops on slot 2 and tosses the wrong thing —
        # or, here, nothing at all.
        for _ in range(2 * (slot + len(self.bag()) + 4)):
            here = self.mem[ADDR_LIST_SCROLL] + self.mem[qm.ADDR_MENU_CUR]
            if here == slot:
                break
            self.ctl.press("down" if here < slot else "up")
            self.ctl.wait(20)
        if self.mem[ADDR_LIST_SCROLL] + self.mem[qm.ADDR_MENU_CUR] != slot:
            for _ in range(6):
                self.ctl.press("b")
                self.ctl.wait(25)
            return False
        self.ctl.press("a")
        self.ctl.wait(60)
        for _ in range(6):  # the item submenu: USE / TOSS — TOSS is the lower row
            if self.mem[qm.ADDR_MENU_CUR] == 1:
                break
            self.ctl.press("down")
            self.ctl.wait(20)
        self.ctl.press("a")
        self.ctl.wait(60)
        # The quantity picker starts at 1 and WRAPS. Holding up a fixed number of times is how
        # you ask for the whole stack and get one unit instead: twelve presses on a six-stack
        # lands back on 1, and a quantity-1 toss frees no slot — the very thing this method
        # exists to avoid. Press exactly what the stack holds.
        for _ in range(max(0, qty - 1)):
            self.ctl.press("up")
            self.ctl.wait(20)
        # The confirm phase is predicate-driven, not timed. `quartermaster` learned this on the
        # mart counter — "the shop dialog cadence swallowing fixed-timing scripts", a purchase
        # that looked confirmed two A-presses before the money moved — and this method ignored
        # it. The identical sequence tossed a stack at 60-frame waits and silently did nothing at
        # 45, which reads as "the game would not part with it" and is really "we stopped asking".
        # The bag is the predicate: press A until a slot frees or the strikes run out.
        for _ in range(8):
            if len(self.bag()) < before:
                break
            self.ctl.press("a")
            self.ctl.wait(60)
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
        candidates = [max(stacks)] if stacks else []
        if not candidates:
            # Every slot holds a single item. Rather than guess which are expendable, ask the
            # cartridge: TMs are named TM<n> in the extracted item table, we are carrying eight,
            # and they are the most redundant thing in the bag. The game itself is the backstop —
            # it refuses to toss a key item, so a slot that does not come free tells us to move
            # on to the next candidate instead of losing something irreplaceable.
            candidates = [(1, item) for item, _q in self.bag() if self.item_name(item).startswith("TM")]
        if not candidates:
            print("  bag is full and nothing in it is expendable", flush=True)
            return False
        freed = False
        for qty, item in candidates:
            print(f"  bag full: tossing {qty}x {self.item_name(item)} to free a slot", flush=True)
            freed = self.toss_stack(item)
            if freed:
                break
            print(f"  the game would not part with {self.item_name(item)}", flush=True)
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

    def ball_contents(self, map_id: int) -> dict[tuple[int, int], str]:
        """``(x, y) -> item name`` for this map's balls, from the object data's item byte.

        A ball's contents are in the cartridge, so "where is the CARD KEY" is a lookup rather
        than a building-wide sweep — the hunt that cost two sessions. Cross-checked against the
        Rocket Hideout, whose two balls extract as SILPH SCOPE and LIFT KEY, both of which this
        run picked up live.
        """
        sprites = self.truth["maps"].get(str(map_id), {}).get("sprites", [])
        items = self.truth.get("items", {})
        return {
            (s["x"], s["y"]): items.get(str(s.get("item")), f"item {s.get('item')}")
            for s in sprites
            if s.get("kind") == "item"
        }

    def collect_item(
        self, bx: int, by: int
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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
            near = road.walkable(self.truth, self.pairs, mp, (x, y), self.bodies() - {(bx, by)}) & adjacent
            if not near or not self.approach(near):
                return False
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
        if self.bag() == before:
            return False
        self.unlock_gates()  # a key just picked up unlocks its doors for the rest of this leg
        return True

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

    def text_from(self, action) -> str:
        """Run ``action`` and return only text that appeared *because of it*.

        Every screen-derived signal here is sticky — the dialogue buffer, the window tilemap and
        the text-id register all keep their last contents until something overwrites them, and
        none is cleared when a box closes. Reading one raw is how 54 ordinary walls came to be
        labelled doors, all quoting a battle three minutes old. Routing every read through this
        makes "what did that do?" the only question anyone can ask of the screen.
        """
        baseline = self.dialogue()
        action()
        said = self.dialogue()
        return "" if said == baseline else said

    def flush_text(self, tries: int = 6) -> bool:
        """Close whatever box is on screen, so the next message is unambiguously the next message.

        .. warning::
           Every screen-derived signal on this cartridge is sticky. The dialogue buffer, the
           window tilemap and the text-id register at 0xD125 all keep their last contents until
           something overwrites them, and none of them is cleared when a box closes. A baton was
           diagnosed as "banked with the START menu open" on the strength of 0xD125 == 13 and a
           window layer still showing POKeDEX/ITEM/SAVE — and then a plain step moved the player
           one tile, proving no menu was open at all. Trust position, bag and badges; treat
           anything read off the screen as a hint that needs corroborating.

        Comparing the buffer before and after a step is not enough on its own: a snapshot taken
        while a box was up *contains* that box, so loading it restores the stale line and the
        comparison sees no change. That is how a survey of map 208 came back with zero doors on a
        floor whose very first westward step prints "Darn! It needs a CARD KEY!". Clear, then read.
        """
        for _ in range(tries):
            if not self.dialogue():
                return True
            self.ctl.press("b")
            self.ctl.wait(30)
        return not self.dialogue()

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
            # B before A. A *commits*, and on the field menu committing opens a submenu — a
            # settle that leads with A can open the very thing it is trying to clear, which is
            # how a baton came to be banked with the START menu up and the cursor sitting on
            # ITEM, breaking every menu flow that booted from it. B closes; A is only for
            # advancing a box that B will not dismiss.
            self.ctl.press("b")
            self.ctl.wait(30)
            if self.probe_step():
                return True
            self.ctl.press("a")
            self.ctl.wait(40)
        return self.probe_step()

    def battle(self, io=None) -> None:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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

    def approach(self, cells) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Get onto one of ``cells`` on this map. Walk first; on a facility floor, use the oracle.

        Silph's top floor refused every planned step: `walk` reported "refused" from (10,9) to a
        cell four tiles away that the grid says is plainly connected, because tileset 22's tiles
        decide where you end up. Planning a path there is the same category error that held
        Rocket Hideout B4 — so the fallback is the facing-keyed oracle, which is the engine's own
        answer for these floors and is already what gets legs *onto* them.
        """
        cells = set(cells)
        mp, x, y = self.pos()
        if (x, y) in cells:
            return True
        self.walk(mp, cells, cap=400)
        here = self.pos()
        if here[0] == mp and here[1:] in cells:
            return True
        # A region whose only door is a pad is invisible to both the walk and the oracle, because
        # both plan over tiles and a pad is a tile you cannot stand on by planning. Ride it.
        # Measured on Silph 5F: the card-key corridor is unreachable on foot from every cell on
        # the floor and one step from the pad at (27,3), and three legs died on that difference.
        # Only on a facility floor. A "warp" on a city map is a building's front door, not a
        # teleport pad: riding Saffron's Silph entrance walks into the lobby and back out, and a
        # leg trying to reach the gym past its guard did that eighty times before the hop cap
        # stopped it.
        facility = self.truth["maps"].get(str(mp), {}).get("tileset") == road.FACILITY_TILESET
        if facility and road.ride_pad(self.io, self.truth, self.pairs, mp, cells, battle=self.battle):
            return True
        here = self.settled_pos()
        if here[0] == mp and here[1:] in cells:
            return True
        if here[0] != mp:  # a ride left us on another floor; the caller's map is no longer ours
            return False
        if facility:
            self.oracle_goto(lambda p: p[0] == mp and (p[1], p[2]) in cells)
        here = self.pos()
        return here[0] == mp and here[1:] in cells

    def traverse(self, interior: int, **kw):
        """Leave a swallowed-hop interior by the mats on another side (a gate room, a house)."""
        kw.setdefault("battle", self.battle)
        return road.traverse_interior(self.io, self.truth, self.pairs, interior, **kw)

    def gate(self, cur: int, goal_cells, **kw):
        """Cross a route severed by its own gate building, validating each candidate door."""
        kw.setdefault("battle", self.battle)
        return road.pass_gate(self.io, self.truth, self.pairs, cur, goal_cells, **kw)

    def bodies(self) -> set[tuple[int, int]]:
        """Live sprites, clipped to this map. Unused sprite slots decode to off-map coordinates,
        and an off-map "blocker" is one a leg will walk across the floor to argue with."""
        m = self.truth["maps"].get(str(self.pos()[0]))
        return road.live_bodies(self.io, (m["width"], m["height"]) if m else None)

    def talk(self, face: str) -> str:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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

    # ---- the lift ---------------------------------------------------------------------------

    def window_row(self, row: int) -> str:
        """One decoded row of the window layer — where menus render (the background stays blank)."""
        from text_decoder import decode_row

        tm = self.pb.tilemap_window
        return decode_row([tm.tile_identifier(x, row) for x in range(20)]).strip()

    def elevator_floors(self) -> list[str]:
        """The floor labels the panel is currently showing, top to bottom."""
        return [self.window_row(4 + 2 * i) for i in range(3)]

    def ride_elevator(
        self, floor: str
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Ride a lift car to a named floor, choosing from the panel's own list.

        The car is a small room on tileset 18 whose control panel is a **sign, not an NPC** —
        measured in the Rocket Hideout (panel at (1,1)) and again in Silph Co (panel at (3,0)),
        which is why talking to bodies never found it. The floor list scrolls exactly like the
        ITEM list: ``0xCC26`` is the cursor inside a three-row window and ``0xCC36`` the scroll
        offset. The label under the cursor is *read off the screen* rather than an index being
        assumed — which floor sits at which index is precisely the kind of fact this project has
        been burned by recalling.

        Returns True when the car has left for another map.
        """
        mp, _x, _y = self.pos()
        m = self.truth["maps"].get(str(mp), {})
        signs = m.get("signs") or []
        if not signs:
            print(f"  map {mp} has no sign to use as a lift panel", flush=True)
            return False
        sx, sy = signs[0]
        if not self.approach({(sx, sy + 1)}):
            return False
        self.ctl.press("up")
        self.ctl.wait(25)
        for _ in range(2):  # A opens the panel, A again brings up the floor list
            self.ctl.press("a")
            self.ctl.wait(70)
        target = floor.strip().upper()
        for _ in range(24):
            cursor = self.mem[qm.ADDR_MENU_CUR]
            if self.window_row(4 + 2 * cursor).upper() == target:
                break
            if target in [f.upper() for f in self.elevator_floors()]:
                self.ctl.press("down" if self.window_row(4).upper() != target else "up")
            else:
                self.ctl.press("down")
            self.ctl.wait(20)
        else:
            for _ in range(6):
                self.ctl.press("b")
                self.ctl.wait(25)
            print(f"  the lift panel never showed a floor called {floor!r}", flush=True)
            return False
        for _ in range(3):
            self.ctl.press("a")
            self.ctl.wait(60)
        for _ in range(4):
            self.ctl.press("b")
            self.ctl.wait(30)
        doors = {(w[0], w[1]) for w in m.get("warps", [])}
        if doors:
            self.approach(doors)
            for direction in ("down", "up", "left", "right"):
                self.io.press(direction, hold=8, release=8)
                self.io.wait(60)
                if self.pos()[0] != mp:
                    return True
        return self.pos()[0] != mp

    # ---- field moves ------------------------------------------------------------------------

    def field_moves(self, rows: int = 8) -> list[str]:
        """The field submenu's entries, decoded from the window layer, top to bottom."""
        return [self.window_row(4 + 2 * i) for i in range(rows)]

    def use_field_move(
        self, name: str, face: str | None = None, member: int = 0
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Use a field move by *name*, choosing it off the menu the game draws.

        `road.cut_facing` hardcodes "CUT is row 0 of the lead's field submenu", which is true for
        Cut on this party and is exactly the kind of assumption that has cost this project runs.
        Which move sits on which row depends on the mon and what it has learned, so the row is
        read rather than assumed — the same fix the lift panel needed for its floor list.

        Returns whether the move was selected. Whether it *worked* is the caller's predicate:
        Cut is proved by stepping into the growth, Surf by ending up on water. Nothing here
        reports success from a menu having been navigated.
        """
        if face:
            self.ctl.press(face)
            self.ctl.wait(25)
        for _ in range(6):  # close anything already open before opening ours
            self.ctl.press("b")
            self.ctl.wait(25)
        self.ctl.press("start")
        self.ctl.wait(50)
        for _ in range(8):  # POKeMON is the row above ITEM
            if self.mem[qm.ADDR_MENU_CUR] == 1:
                break
            self.ctl.press("down" if self.mem[qm.ADDR_MENU_CUR] < 1 else "up")
            self.ctl.wait(20)
        self.ctl.press("a")
        self.ctl.wait(60)
        for _ in range(8):  # the party list, then the member whose move we want
            if self.mem[qm.ADDR_MENU_CUR] == member:
                break
            self.ctl.press("down" if self.mem[qm.ADDR_MENU_CUR] < member else "up")
            self.ctl.wait(20)
        self.ctl.press("a")
        self.ctl.wait(60)
        target = name.strip().upper()
        for _ in range(10):
            cursor = self.mem[qm.ADDR_MENU_CUR]
            if self.window_row(4 + 2 * cursor).upper().startswith(target):
                self.ctl.press("a")
                self.ctl.wait(60)
                return True
            if target not in " ".join(self.field_moves()).upper():
                break
            self.ctl.press("down")
            self.ctl.wait(20)
        print(f"  no field move called {name!r} on party member {member}", flush=True)
        for _ in range(6):
            self.ctl.press("b")
            self.ctl.wait(30)
        return False

    def surf_onto(self, face: str) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Ride onto water. The predicate is the position, never the menu."""
        before = self.pos()
        if not self.use_field_move("SURF", face=face):
            return False
        for _ in range(4):
            self.ctl.press("a")
            self.ctl.wait(50)
        self.io.press(face, hold=8, release=8)
        self.io.wait(45)
        return self.pos() != before

    def strength_push(
        self, face: str
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Enable Strength, then shove the boulder. Proved by the boulder's tile opening up."""
        if not self.use_field_move("STRENGTH", face=face):
            return False
        for _ in range(4):
            self.ctl.press("a")
            self.ctl.wait(50)
        before = self.pos()
        self.io.press(face, hold=8, release=8)
        self.io.wait(45)
        return self.pos() != before

    # ---- surveying --------------------------------------------------------------------------

    def survey_pocket(
        self, max_cells: int = 400, log=print
    ) -> dict:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Walk the pocket for real and write down every wall that talks.

        The extracted collision grid cannot see a script gate. Inside Silph it calls a card-key
        door plain walkable floor, so *every* static region measured in that building over-reports
        — the 343 cells on 208 and the 128 on 235 both included ground behind locks. A route
        planned on those numbers is planned on a map of a different building.

        So this measures the pocket the way the only reliable statement about it can be made: a
        flood fill of **attempted steps**. Press, look at what happened, and when the step is
        refused, capture the sentence the game prints. The result is the pocket's true shape plus
        a door map keyed by (x, y, direction) — the locks turned into data.

        Each cell costs a save/load per direction, so this is deliberate, not cheap.
        """
        import io as _io
        from collections import deque

        deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        mp, sx, sy = self.settled_pos()
        m = self.truth["maps"][str(mp)]
        ungated = {k: v for k, v in m.items() if k != "gates"}
        bodies = self.bodies()
        origin = _io.BytesIO()
        self.pb.save_state(origin)

        def snap():
            self.flush_text()  # a snapshot holding an open box poisons every probe made from it
            buf = _io.BytesIO()
            self.pb.save_state(buf)
            return buf

        def load(buf):
            buf.seek(0)
            self.pb.load_state(buf)

        cells = {(sx, sy)}
        doors: dict[str, str] = {}
        exits: dict[str, int] = {}
        battles: list[str] = []
        queue = deque([((sx, sy), snap())])
        probes = 0
        while queue and len(cells) < max_cells:
            cell, state = queue.popleft()
            for direction, (dx, dy) in deltas.items():
                target = (cell[0] + dx, cell[1] + dy)
                if target in cells:
                    continue
                load(state)
                self.io.press(direction, hold=8, release=8)
                self.io.wait(40)
                probes += 1
                if self.mem[qm.ADDR_IN_BATTLE]:
                    battles.append(f"{cell[0]},{cell[1]},{direction}")
                    continue  # a fight is not a wall; the next load undoes it
                now = self.pos()
                if now[0] != mp:
                    exits[f"{cell[0]},{cell[1]},{direction}"] = now[0]
                    continue
                if (now[1], now[2]) == cell:
                    # A press can turn in place before it walks, so give it a second one before
                    # calling the step refused.
                    self.io.press(direction, hold=8, release=8)
                    self.io.wait(40)
                    now = self.pos()
                if now[0] != mp:
                    exits[f"{cell[0]},{cell[1]},{direction}"] = now[0]
                    continue
                if (now[1], now[2]) == cell:
                    # A door is a *discrepancy*, not a message. The text buffer cannot carry this
                    # judgement: it is not cleared by closing a box, only overwritten when
                    # something new is drawn, so it reads the same before and after a refusal.
                    # The reliable signal is structural — the extracted grid says this step is
                    # walkable and passable, no body is standing there, and the engine still says
                    # no. That is exactly an unmodelled gate, and it is what the collision grid
                    # cannot see. Any text present is recorded as evidence, never as the test.
                    # Judge against the *grid*, not against what we already believe. `passable`
                    # is gate-aware now, so testing with it would skip every known gate and a
                    # false positive — a wanderer that moved, a trainer freeze — would become
                    # permanent, never re-probed. Surveys must be able to disagree with the file
                    # they feed.
                    if (
                        rt.passable(ungated, self.pairs, cell[0], cell[1], target[0], target[1])
                        and target not in bodies
                    ):
                        said = self.dialogue()
                        doors[f"{cell[0]},{cell[1]},{direction}"] = said or ""
                        log(f'  GATE at {cell} {direction} -> {target}   [buffer: "{(said or "")[:70]}"]')
                    continue
                landed = (now[1], now[2])
                if landed not in cells:
                    cells.add(landed)
                    queue.append((landed, snap()))
        load(origin)
        result = {
            "map": mp,
            "start": [sx, sy],
            "cells": sorted(cells),
            # ``doors`` maps a refused step to whatever was in the text buffer at the time. The
            # gate itself is the *key*, established structurally; the value is a hint and is
            # frequently stale — 207's four gates all "said" a trainer's line from minutes
            # earlier. Never read a value here as the door's own message.
            "doors": doors,
            "exits": exits,
            "battles": battles,
            "probes": probes,
            "truncated": len(cells) >= max_cells,
        }
        log(f"  surveyed map {mp}: {len(cells)} cells measured, {len(doors)} talking walls, {probes} probes")
        self.emit("supervisor.surveyed", map=mp, cells=len(cells), doors=len(doors), probes=probes)
        return result

    # ---- the oracle -------------------------------------------------------------------------

    def oracle_goto(
        self, goal_test, max_states: int = 500
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
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

    def escape_pocket(
        self, max_states: int = 700
    ) -> bool:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        """Ride whatever this floor offers until we stand outside our own walkable region.

        Teleport pads are intra-map warps (``dst == this map``), and ``road.walk`` blocks every
        warp tile by design — the standing doctrine that a door is not a floor. That is right for
        walking and exactly wrong on a floor whose pads *are* the way across.

        Where this applies is measured, not assumed, and the measurement corrected a guess:
        Silph's floors have almost no intra-map pads (208 and 213 hold two each, the rest none) —
        they are cross-linked to *other floors* instead — so this returns False there, correctly.
        **Sabrina's gym, map 178, has thirty.** That is the floor this exists for.

        The goal is a **region**, not a cell: anywhere our own reachable set does not contain, on
        the same map. Aiming at a specific tile is what kept failing, because nothing knows which
        tile is on the far side of a pad until the game puts you there. Accepting any *other map*
        does not work either — the first run of this rode the floor's exit door out and called it
        an escape, which was true and useless.
        """
        mp, x, y = self.pos()
        region = road.reachable(self.truth, self.pairs, mp, (x, y), self.bodies())
        print(f"  escaping a {len(region)}-cell pocket on map {mp} by riding what the floor offers", flush=True)
        found = self.oracle_goto(lambda p: p[0] == mp and (p[1], p[2]) not in region, max_states=max_states)
        if found:
            self.emit("supervisor.pocket_escaped", map=mp, from_cells=len(region), to=list(self.pos()))
        return found

    # ---- banking --------------------------------------------------------------------------

    def unlock_gates(self) -> int:
        """Drop every measured door gate that names an item now in the bag. Returns how many.

        Called on boot and after each pickup, because the bag is what turns a locked door into a
        door. The CARD KEY was taken on 5F and the very next leg planned as though it had not
        been: `no-path` on 3F -> 7F, our own model refusing a route the world would have allowed.
        """
        held = {name for name, _qty in self.bag_named()}
        if not held:
            return 0
        opened = 0
        for m in self.truth.get("maps", {}).values():
            gates = m.get("gates")
            if not gates:
                continue
            kept = rt.gates_the_bag_opens(gates, held)
            opened += len(gates) - len(kept)
            m["gates"] = kept
        if opened:
            print(f"  the bag opens {opened} measured door gate(s)", flush=True)
        return opened

    def center_counter(self, map_id: int) -> tuple[tuple[int, int], str] | None:
        """Where to stand and which way to face to be healed, if this map is a Pokemon Center.

        A nurse is not an ordinary body: she stands *behind a counter*, so no cell is adjacent to
        her and `engage_bodies` — which only ever walks to a neighbouring tile — cannot meet her.
        Measured cost: a leg reached Saffron's Center, talked to all three idle NPCs (growth
        rates, Silph gossip, the Cable Club), and reported the heal refused with three fainted
        party members.

        The geometry is one template, verified live at Cerulean, Pewter and Vermilion
        (`quartermaster.CENTERS`): nurse sprite at (3,1), player at (3,3), facing up. Saffron's
        map 182 is the same 14x8 tileset-6 interior with the same nurse tile, which is how it was
        identified — by signature, not by recall.
        """
        m = self.truth["maps"].get(str(map_id))
        if not m or (m["width"], m["height"], m["tileset"]) != (14, 8, 6):
            return None
        if not any(s["kind"] == "npc" and (s["x"], s["y"]) == (3, 1) for s in m.get("sprites", [])):
            return None
        return (3, 3), "up"

    def step_off_targets(self, map_id: int, x: int, y: int) -> list[tuple[str, tuple[int, int]]]:
        """Directions off a warp tile that land on ordinary floor — doors excluded, in order."""
        m = self.truth["maps"].get(str(map_id))
        if not m:
            return []
        warps = self.warp_tiles(map_id)
        out = []
        for direction, (dx, dy) in (("up", (0, -1)), ("down", (0, 1)), ("left", (-1, 0)), ("right", (1, 0))):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < m["width"] and 0 <= ny < m["height"]):
                continue
            if m["grid"][ny][nx] != "1" or (nx, ny) in warps:
                continue
            if not rt.passable(m, self.pairs, x, y, nx, ny):
                continue
            out.append((direction, (nx, ny)))
        return out

    def _step_off_mat(self, mp: int, x: int, y: int) -> bool:  # pragma: no cover - drives the emulator
        """Try each floor-ward neighbour, undoing any step that leaves the map.

        A mat's neighbours can fire too — Silph 3F's (11,11) sits beside another door, and the
        step-off went straight back to 7F, so the *next* leg booted on the wrong side of the
        building and spent its budget trying to get back. A step that changes the map is not a
        step off the mat, so it is rolled back and the next direction tried.
        """
        import io as _io

        def snap():
            buf = _io.BytesIO()
            self.pb.save_state(buf)
            return buf

        before = snap()
        for direction, cell in self.step_off_targets(mp, x, y):
            self.ctl.press(direction)
            self.ctl.wait(30)
            if self.pos() == (mp, *cell):
                print(f"  stepped off the {mp} warp mat at ({x}, {y}) before banking", flush=True)
                return True
            before.seek(0)
            self.pb.load_state(before)  # that neighbour was a door too; undo and try another
        print(f"  WARNING: could not step off the warp mat at ({x}, {y}) on {mp}", flush=True)
        return False

    def bank(
        self, name: str, *, directory: Path | None = None
    ) -> Path:  # pragma: no cover - writes and reloads a real save state
        """Bank a baton the next leg can actually boot.

        Two states are worthless as batons and both were paid for: one banked mid-dialogue (every
        step swallowed) and one banked standing ON a warp mat, which boots back through the door
        it just came out of. Settle first, step off the door if we are on it, then save.
        """
        import io as _io

        arrival = self.pos()[0]
        entry = _io.BytesIO()
        self.pb.save_state(entry)  # the map we were asked to bank; anything else is not it
        mp, x, y = self.pos()
        if (x, y) in self.warp_tiles(mp):
            # Step off BEFORE settling. `settle`'s probe will use a door when every neighbour is
            # one, and Silph 3F's (11,11) mat is surrounded by them — so settling first fired the
            # warp and the baton recorded (212,5,3), a floor away from the leg that had just
            # arrived. Two chained legs booted on the wrong side of the building that way.
            self._step_off_mat(mp, x, y)
        self.settle()
        if self.pos()[0] != arrival:
            print(f"  banking on {arrival} but settling left us on {self.pos()[0]} — rolling back", flush=True)
            entry.seek(0)
            self.pb.load_state(entry)
        mp, x, y = self.pos()
        if (x, y) in self.warp_tiles(mp):
            # A real step, not a probe. `probe_step` presses and *undoes*, which leaves us on the
            # mat, and the reload check cannot see the problem because an in-process reload does
            # not settle. Booting that baton in a fresh process does, and the settle walks out
            # through the door: Saffron's Center banked at (182,3,7) came back up in the city,
            # and the leg spent its ladder trying to get back in. A Center has two mats side by
            # side, so the escape has to prefer a neighbour that is not itself a door.
            self._step_off_mat(mp, x, y)
        path = (directory or BATON_DIR) / f"{name}.state"
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = self.settled_pos()
        with path.open("wb") as fh:
            self.pb.save_state(fh)
        # Read it back. Three batons this session were unusable — one banked mid-dialogue, one
        # standing on a warp mat, one mid-transition reporting a tile its map does not have — and
        # each was discovered a leg later by a run that had already spent its budget booting it.
        # A baton nobody can boot is not a baton, and the check costs one load.
        with path.open("rb") as fh:
            self.pb.load_state(fh)
        got = self.settled_pos()
        if got != expected:
            print(f"  WARNING: {path.name} reloads as {got}, not {expected} — do not trust it", flush=True)
            self.emit("baton.unstable", name=name, expected=list(expected), got=list(got))
        else:
            print(f"  banked {path.name} at {expected}", flush=True)
        return path

    def shot(
        self, path: str | Path
    ) -> Path:  # pragma: no cover - drives the emulator; verified live, not in unit tests
        from PIL import Image

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(self.pb.screen.ndarray).save(out)
        return out
