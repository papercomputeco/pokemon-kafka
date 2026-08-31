"""The loop body, tested without a cartridge.

A fake Rig stands in for the emulator: it holds a scripted sequence of hop outcomes and records
what the runner asked it to do. That is enough to pin the behaviour that actually matters — the
ladder escalates navigation -> puzzle and then *stops with a written record*, a non-answer is
never silently turned into an action, GIVE_UP ends the leg, the budget is honoured, and the
badge check watches the byte change rather than a remembered bit.
"""

import json

import pytest
import rom_truth as rt
import supervisor
from supervisor import LADDER_ATTEMPTS, LegRunner, menu_for


class FakeRig:
    """Enough Rig to drive a leg: a position, a scripted hop outcome per call, a call log."""

    def __init__(self, *, start=(1, 5, 5), hops=None, truth=None, badges=0b11111, bodies=()):
        self._pos = start
        self._hops = list(hops or [])  # each entry: the map id we land on after cross/warp
        self.truth = truth or _truth()
        self.pairs = set()
        self._badges = badges
        self._bodies = set(bodies)
        self.run_id = "testrun00"
        self.calls: list[tuple] = []
        self.events: list[dict] = []
        self.io = self
        self.said = "MOVE ASIDE!"
        self._bag: list = []
        self._pickups: dict = {}

    # reads
    def pos(self):
        return self._pos

    def badges(self):
        return self._badges

    def party(self):
        return [("CHARIZARD", 99, 337)]

    def dialogue(self):
        return ""

    def bodies(self):
        return set(self._bodies)

    def settled_pos(self):
        return self._pos

    def item_balls(self, map_id):
        return [
            (s["x"], s["y"])
            for s in self.truth["maps"].get(str(map_id), {}).get("sprites", [])
            if s.get("kind") == "item"
        ]

    def bag(self):
        return list(self._bag)

    def collect_item(self, bx, by):
        self.calls.append(("collect", (bx, by)))
        if (bx, by) in self._pickups:
            self._bag.append(self._pickups[(bx, by)])
            return True
        return False

    def emit(self, event, **fields):
        self.events.append({"event": event, **fields})
        return {}

    # moves — each consumes one scripted outcome.
    # "refused" is the generic failure here on purpose: it is the code with no deterministic
    # recovery, so these fixtures exercise the crew ladder. "no-path" is structural and the
    # runner answers it itself (see the reroute tests below).
    def _advance(self, label, arg):
        self.calls.append((label, arg))
        if self._hops:
            landed = self._hops.pop(0)
            if landed is not None:
                self._pos = (landed, 1, 1)
        return "refused"

    def cross(self, cur, nxt, **kw):
        return self._advance("cross", nxt)

    def warp(self, mp, x, y, **kw):
        return self._advance("warp", (x, y))

    def traverse(self, interior, **kw):
        return self._advance("traverse", interior)

    def gate(self, cur, cells, **kw):
        self.calls.append(("gate", cur))
        return False

    def walk(self, mp, targets, **kw):
        # A walk that records but never moves would let the runner "arrive" everywhere and
        # nowhere; the real one lands on a target cell, so this one does too.
        self.calls.append(("walk", sorted(targets)))
        if targets:
            self._pos = (mp, *sorted(targets)[0])
        return True

    def approach(self, cells):
        self.calls.append(("approach", sorted(cells)))
        if not cells:
            return False
        self._pos = (self._pos[0], *sorted(cells)[0])
        return True

    def talk(self, face):
        self.calls.append(("talk", face))
        return self.said

    def wait(self, frames):
        self.calls.append(("wait", frames))


def _truth():
    """Two maps joined by one edge, plus a dead-end house on map 1 to back out through — the
    smallest world where the routed chain to map 2 is unambiguously the *edge*, not a door."""
    grid = ["1" * 8 for _ in range(8)]

    def m(**kw):
        return {
            "width": 8,
            "height": 8,
            "tileset": 0,
            "grid": grid,
            "sprites": [],
            "warps": [],
            "connections": {},
            **kw,
        }

    return {
        "maps": {
            "1": m(warps=[[2, 7, 9, 0]], connections={"east": 2}),
            "2": m(connections={"west": 1}),
            "9": m(warps=[[0, 0, 1, 0]]),  # the house: one door, straight back to map 1
        }
    }


def _consult(*answers):
    """A scripted seat: hands back (action, why, model) per call and logs the tier it was asked at."""
    seen = []

    def consult(tier, facts, menu):
        seen.append({"tier": tier, "facts": facts, "menu": list(menu)})
        action = answers[len(seen) - 1] if len(seen) <= len(answers) else answers[-1]
        return action, "scripted", "fake-model"

    consult.seen = seen
    return consult


# --------------------------------------------------------------------------- menus


def test_menu_drops_edge_action_on_a_warp_hop():
    assert "TRY_FAR_EDGE_CELL" in menu_for("no-path", edge_hop=True)
    assert "TRY_FAR_EDGE_CELL" not in menu_for("no-path", edge_hop=False)


def test_every_menu_action_is_one_the_engine_implements():
    for failure in list(supervisor.MENUS) + ["something-new"]:
        for action in menu_for(failure):
            assert action in supervisor.ACTIONS


def test_no_route_menu_never_offers_an_edge_or_retry_that_cannot_help():
    menu = menu_for("no-route")
    assert "RETRY_SAME" not in menu  # nothing to retry: the graph has no chain at all
    assert "GIVE_UP" in menu


# --------------------------------------------------------------------------- the happy leg


def test_a_clean_hop_arrives_without_ever_consulting():
    rig = FakeRig(hops=[2])
    consult = _consult("RETRY_SAME")
    result = LegRunner(rig, goal=2, consult=consult, log=lambda *_: None).run()
    assert result["ok"] and result["outcome"] == "arrived"
    assert consult.seen == []  # models are asked on failure, never on a working hop
    assert [e["event"] for e in rig.events] == ["supervisor.leg_start", "supervisor.leg_end"]


def test_arrival_is_read_from_the_rig_not_assumed():
    rig = FakeRig(start=(2, 3, 3))
    result = LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None).run()
    assert result["outcome"] == "arrived" and rig.calls == []


# --------------------------------------------------------------------------- the ladder


def test_the_ladder_escalates_navigation_then_puzzle_then_writes_the_record(tmp_path):
    rig = FakeRig(hops=[None] * 12)
    consult = _consult("RETRY_SAME")
    runner = LegRunner(rig, goal=2, consult=consult, log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    tiers = [c["tier"] for c in consult.seen]
    assert tiers == ["navigation", "navigation", "puzzle", "puzzle"]
    assert result["outcome"] == "exhausted" and not result["ok"]
    doc = next(tmp_path.glob("*.md")).read_text()
    assert "Anthropic was NOT called" in doc and "RETRY_SAME" in doc
    assert any(e["event"] == "supervisor.exhausted" for e in rig.events)


def test_a_non_answer_is_never_turned_into_an_action(tmp_path):
    """An unparsed reply must cost its attempt and nothing more — not the first menu item."""
    rig = FakeRig(hops=[None] * 12)
    runner = LegRunner(rig, goal=2, consult=_consult(None), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    assert not any(c[0] in ("gate", "talk", "walk") for c in rig.calls)
    assert any("no menu action" in n for n in runner.notes)


def test_give_up_ends_the_leg_with_a_record(tmp_path):
    rig = FakeRig(hops=[None] * 12)
    runner = LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    assert result["outcome"] == "gave-up"
    assert len(list(tmp_path.glob("*.md"))) == 1


def test_the_wall_counter_is_per_wall_so_progress_resets_the_ladder(tmp_path):
    # Fail the 1->2 hop LADDER_ATTEMPTS times, then let it through: the leg must still arrive.
    rig = FakeRig(hops=[None] * LADDER_ATTEMPTS + [2])
    runner = LegRunner(rig, goal=2, consult=_consult("RETRY_SAME"), log=lambda *_: None, learnings_dir=tmp_path)
    assert runner.run()["ok"]


# --------------------------------------------------------------------------- executed actions


def test_talk_to_blocker_walks_adjacent_faces_and_banks_what_was_said(tmp_path):
    rig = FakeRig(hops=[None] * 12, bodies={(6, 5)})
    runner = LegRunner(rig, goal=2, consult=_consult("TALK_TO_BLOCKER"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    assert ("talk", "right") in rig.calls  # the body is east of (5, 5)
    assert any("MOVE ASIDE!" in n for n in runner.notes)


def test_talk_to_blocker_with_no_body_records_that_the_block_is_not_a_sprite(tmp_path):
    rig = FakeRig(hops=[None] * 12)
    runner = LegRunner(rig, goal=2, consult=_consult("TALK_TO_BLOCKER"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    assert any("terrain or a script" in n for n in runner.notes)
    assert not any(c[0] == "talk" for c in rig.calls)


def test_wait_for_bodies_waits_rather_than_declaring_a_wall(tmp_path):
    rig = FakeRig(hops=[None] * 12, bodies={(6, 5)})
    runner = LegRunner(rig, goal=2, consult=_consult("WAIT_FOR_BODIES"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    assert ("wait", supervisor.BODY_WAIT_FRAMES) in rig.calls


def test_far_edge_cell_aims_at_the_far_end_of_the_open_edge(tmp_path):
    rig = FakeRig(hops=[None] * 12)
    runner = LegRunner(rig, goal=2, consult=_consult("TRY_FAR_EDGE_CELL"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    walks = [c for c in rig.calls if c[0] == "walk"]
    assert walks and walks[0][1] == [(7, 0)]  # from (5,5), the far cell on map 1's east column


def test_back_out_uses_the_nearest_warp_on_this_map(tmp_path):
    rig = FakeRig(hops=[None] * 12)
    runner = LegRunner(
        rig, goal=2, consult=_consult("BACK_OUT_AND_REENTER"), log=lambda *_: None, learnings_dir=tmp_path
    )
    runner.run()
    assert ("warp", (2, 7)) in rig.calls


# --------------------------------------------------------------------------- budget + engage


def test_the_budget_stops_the_leg_even_mid_wall(tmp_path):
    ticks = iter([0, 0, 10_000])
    rig = FakeRig(hops=[None] * 12)
    runner = LegRunner(
        rig,
        goal=2,
        budget_s=60,
        consult=_consult("RETRY_SAME"),
        clock=lambda: next(ticks),
        log=lambda *_: None,
        learnings_dir=tmp_path,
    )
    result = runner.run()
    assert result["outcome"] == "budget" and not result["ok"]


def test_engage_watches_the_badge_byte_change_not_a_remembered_bit():
    rig = FakeRig(start=(2, 3, 3), badges=0b11111, bodies={(4, 3)})
    original_talk = rig.talk

    def talk(face):  # the leader falls; the byte gains a bit we never had to name
        rig._badges = 0b111111
        return original_talk(face)

    rig.talk = talk
    result = LegRunner(rig, goal=2, engage=True, consult=_consult("GIVE_UP"), log=lambda *_: None).run()
    assert result["ok"] and result["badges"] == 0b111111


def test_engage_that_changes_nothing_is_reported_as_such():
    rig = FakeRig(start=(2, 3, 3), badges=0b11111, bodies={(4, 3)})
    result = LegRunner(rig, goal=2, engage=True, consult=_consult("GIVE_UP"), log=lambda *_: None).run()
    assert result["outcome"] == "engaged-no-badge" and not result["ok"]


# --------------------------------------------------------------------------- the facts


def test_the_facts_handed_over_are_measured_and_carry_the_per_tileset_warning():
    rig = FakeRig(bodies={(6, 5)})
    facts = supervisor.describe(rig, 2, {"via": "edge", "to": 2}, "no-path", ["the guard says NO"])
    assert "map 1 at (5, 5)" in facts
    assert "tileset" in facts and "per-tileset" in facts
    assert "OPEN EDGE CELLS" in facts and "(7, 0)" in facts
    assert "LIVE BODIES" in facts and "(6, 5)" in facts
    assert "BADGES byte: 0b00011111" in facts
    assert "OBSERVED: the guard says NO" in facts


def test_facts_for_a_missing_route_say_so_plainly():
    rig = FakeRig()
    facts = supervisor.describe(rig, 99, None, "no-route")
    assert "NO ROUTE" in facts


# --------------------------------------------------------------------------- the seat wiring


def test_the_consult_posts_to_the_tapes_proxy_and_parses_the_reply(monkeypatch):
    import expedition_crew as crew

    posted = {}

    class _Resp:
        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "ACTION: USE_GATE_WARP\nWHY: the gate severs it"}}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        posted["url"] = req.full_url
        posted["body"] = json.loads(req.data)
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    action, why, model = supervisor.TapesConsult(log=lambda *_: None)(
        "puzzle", "facts here", ["USE_GATE_WARP", "GIVE_UP"]
    )
    assert posted["url"] == crew.TAPES_CHAT_URL  # :42345 — an uncaptured call is a doctrine break
    assert posted["body"]["model"] == crew.CREW["puzzle"]["model"]
    assert "recalled details are frequently wrong" in posted["body"]["messages"][0]["content"]
    assert (action, model) == ("USE_GATE_WARP", crew.CREW["puzzle"]["model"])
    assert why == "the gate severs it"


def test_a_dead_proxy_is_a_non_answer_not_a_crash(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    action, why, _ = supervisor.TapesConsult(log=lambda *_: None)("navigation", "facts", ["RETRY_SAME"])
    assert action is None and "consult failed" in why


def test_the_seats_are_the_benchmarked_crew_and_never_anthropic():
    import expedition_crew as crew

    for tier in ("navigation", "puzzle"):
        assert "claude" not in crew.seat_for(tier)["model"].lower()


# --------------------------------------------------------------------------- the old half still works


def test_the_cross_run_classifier_is_untouched():
    sup = supervisor.Supervisor()
    assert sup.classify_exit(budget_s=7200, used_s=7000, baton=True, harness_death=False)["action"] == "next_leg"


@pytest.mark.parametrize("cmd", ["run", "classify-exit", "replay"])
def test_every_documented_subcommand_is_registered(cmd):
    with pytest.raises(SystemExit):
        supervisor.main([cmd, "--help"])


def test_a_goal_chain_parses_into_legs():
    assert supervisor.parse_goals("10,181,178") == [10, 181, 178]
    assert supervisor.parse_goals("7") == [7]
    assert supervisor.parse_goals(" 10 , 178 ") == [10, 178]


def test_route_lookup_is_the_hop_source_not_a_search():
    """The runner asks rom_truth for the chain; the smallest world answers with one edge hop."""
    chain = rt.route(_truth(), 1, 2)
    assert chain and chain[0]["via"] == "edge" and chain[0]["to"] == 2


# --------------------------------------------------------------- determinism before consultation


def _fork_truth():
    """Map 1 reaches map 2 two ways: a direct edge, and a detour through map 3. The direct edge
    is Cycling Road — a graph path the world refuses."""
    grid = ["1" * 8 for _ in range(8)]

    def m(**kw):
        return {
            "width": 8,
            "height": 8,
            "tileset": 0,
            "grid": grid,
            "sprites": [],
            "warps": [],
            "connections": {},
            **kw,
        }

    return {
        "maps": {
            "1": m(connections={"east": 2, "south": 3}),
            "2": m(connections={"west": 1, "south": 4}),
            "3": m(connections={"north": 1, "east": 4}),
            "4": m(connections={"west": 3, "north": 2}),
        }
    }


class SeveredRig(FakeRig):
    """One named hop reports no-path forever; every other hop lands."""

    def __init__(self, severed=(1, 2), **kw):
        kw.setdefault("truth", _fork_truth())
        super().__init__(**kw)
        self.severed = severed

    def cross(self, cur, nxt, **kw):
        self.calls.append(("cross", nxt))
        if (cur, nxt) == self.severed:
            return "no-path"
        self._pos = (nxt, 1, 1)
        return True


def test_a_structurally_refused_hop_is_banned_and_routed_around_without_a_consult(tmp_path):
    """Cycling Road, in miniature: 1->2 is a graph edge no player can walk, so take 1->3->4->2."""
    rig = SeveredRig()
    consult = _consult("GIVE_UP")
    runner = LegRunner(rig, goal=2, consult=consult, log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    assert result["ok"], result["reason"]
    assert (1, 2) in runner.banned
    assert consult.seen == []  # a fact about the graph is not a question for a model
    assert any(e["event"] == "supervisor.rerouted" for e in rig.events)


def test_the_gate_building_is_tried_before_the_hop_is_banned(tmp_path):
    rig = SeveredRig()
    runner = LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    assert ("gate", 1) in rig.calls  # a severed route is usually its own gate building
    assert (1, 2) in runner.gated


def test_banning_the_only_chain_falls_back_to_the_crew_rather_than_looping(tmp_path):
    rig = SeveredRig(truth=_truth())  # the two-map world: nothing to reroute through
    runner = LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    assert result["outcome"] == "gave-up"
    assert any("leaves no chain" in n for n in runner.notes)


def test_route_can_ban_a_hop_the_world_refuses():
    truth = _fork_truth()
    assert rt.route(truth, 1, 2)[0]["to"] == 2  # the direct edge, unbanned
    detour = rt.route(truth, 1, 2, banned={(1, 2)})
    assert [h["to"] for h in detour] == [3, 4, 2]
    assert rt.route(truth, 1, 2, banned={(1, 2), (1, 3)}) is None


# ------------------------------------------------------- one body is a gate, not a missing road


class BlockedRig(SeveredRig):
    """1->2 is severed while `blocker` stands there; engaging it opens the road."""

    def __init__(self, blocker=(3, 2), **kw):
        super().__init__(severed=(1, 2), truth=_corridor_world(), **kw)
        self._pos = (1, 0, 5)
        self._bodies = {blocker, (1, 4)}  # the wall, and a bystander right next to us
        self.blocker = blocker

    def cross(self, cur, nxt, **kw):
        self.calls.append(("cross", nxt))
        if (cur, nxt) == self.severed and self.blocker in self._bodies:
            return "no-path"
        self._pos = (nxt, 1, 1)
        return True

    def talk(self, face):
        self.calls.append(("talk", face))
        self._bodies.discard(self.blocker)  # beaten/moved: the road opens
        return "I like shorts!"


def _corridor_world():
    rows = ["0011000", "0011000", "0001000", "0011000", "1111111", "1111111"]

    def m(**kw):
        return {
            "width": 7,
            "height": 6,
            "tileset": 0,
            "grid": rows,
            "sprites": [],
            "warps": [],
            "connections": {},
            **kw,
        }

    return {"maps": {"1": m(connections={"north": 2}), "2": m(connections={"south": 1})}}


def test_one_body_severing_a_hop_is_engaged_before_anything_is_banned(tmp_path):
    """Route 12: the north road was banned as impassable when the wall was one unfought trainer."""
    rig = BlockedRig()
    consult = _consult("GIVE_UP")
    runner = LegRunner(rig, goal=2, consult=consult, log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    assert result["ok"], result["reason"]
    assert runner.banned == set()  # nothing was banned: the road was there all along
    assert consult.seen == []  # and nothing was asked: one body is not a judgement call
    assert any(e["event"] == "supervisor.blocker_engaged" for e in rig.events)


def test_the_body_underfoot_is_not_mistaken_for_the_wall(tmp_path):
    rig = BlockedRig()
    LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path).run()
    walks = [c[1] for c in rig.calls if c[0] == "walk"]
    # It walked to a cell adjacent to the choke at (3,2), not to the bystander at (1,4).
    assert walks and set(walks[0]) <= {(2, 2), (4, 2), (3, 1), (3, 3)}


def test_the_same_blocker_is_only_engaged_once(tmp_path):
    """A body that does not clear must not become an infinite errand."""
    rig = BlockedRig()

    def stubborn(face):  # engaging changes nothing: the body stays exactly where it was
        rig.calls.append(("talk", face))
        return "..."

    rig.talk = stubborn
    runner = LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.run()
    assert len(runner.engaged) == 1
    assert len([c for c in rig.calls if c[0] == "talk"]) == 1


def test_gate_doors_tell_a_pass_through_from_a_dead_end_house():
    import road

    truth = {
        "maps": {
            "23": {"warps": [[10, 15, 87, 0], [11, 15, 87, 1], [10, 21, 87, 2], [11, 77, 189, 0]]},
        }
    }
    assert road.gate_doors(truth, 23) == {(10, 15), (11, 15), (10, 21)}  # map 87 is the gate


def test_clearing_a_blocker_retires_the_verdicts_reached_while_it_stood(tmp_path):
    """Route 12 was banned as impassable, and its gate marked tried, on evidence gathered while
    the blocker still stood there. Clearing it makes both verdicts stale."""
    rig = BlockedRig()
    runner = LegRunner(rig, goal=2, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.banned.add((1, 2))
    runner.gated.add((1, 2))
    runner._clear_blocker({"via": "edge", "to": 2})
    assert (1, 2) not in runner.banned
    assert (1, 2) not in runner.gated


# ------------------------------------------------------------- the facility floors (tileset 22)


def test_the_oracle_is_offered_only_on_tile_driven_floors():
    """Spin arrows and teleport pads live in tileset 22; a route map has nothing to search."""
    assert "ORACLE_SEARCH" not in menu_for("warp-dead", facility=False)
    assert menu_for("warp-dead", facility=True)[0] == "ORACLE_SEARCH"


class FacilityRig(FakeRig):
    """A tileset-22 floor whose warp will not fire until the oracle finds the way onto it."""

    def __init__(self):
        grid = ["1" * 8 for _ in range(8)]
        truth = {
            "maps": {
                "181": {
                    "width": 8,
                    "height": 8,
                    "tileset": 22,
                    "grid": grid,
                    "sprites": [],
                    "warps": [[6, 4, 208, 0]],
                    "connections": {},
                },
                "208": {
                    "width": 8,
                    "height": 8,
                    "tileset": 22,
                    "grid": grid,
                    "sprites": [],
                    "warps": [[0, 0, 181, 0]],
                    "connections": {},
                },
            }
        }
        super().__init__(start=(181, 1, 1), truth=truth, hops=[None] * 12)
        self.oracle_calls = []

    def oracle_goto(self, goal_test, max_states=500):
        self.oracle_calls.append(max_states)
        self._pos = (208, 1, 1)  # the oracle found the pad and it fired
        return True


def test_the_oracle_action_runs_the_facing_keyed_search_toward_the_hop_target(tmp_path):
    rig = FacilityRig()
    runner = LegRunner(rig, goal=208, consult=_consult("ORACLE_SEARCH"), log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    assert rig.oracle_calls, "the oracle was never run on a tileset-22 floor"
    assert result["ok"] and result["outcome"] == "arrived"


def test_the_facility_menu_reaches_the_seat(tmp_path):
    rig = FacilityRig()
    consult = _consult("GIVE_UP")
    LegRunner(rig, goal=208, consult=consult, log=lambda *_: None, learnings_dir=tmp_path).run()
    assert "ORACLE_SEARCH" in consult.seen[0]["menu"]


def test_a_dead_door_is_routed_around_rather_than_asked_about(tmp_path):
    """Silph 1F's (16,10) pad is dead and the floor has two other ways up. A door that will not
    open is as structural as a severed grid — a lookup, not a question."""

    class DeadDoorRig(FakeRig):
        def __init__(self):
            super().__init__(truth=_fork_truth(), start=(1, 5, 5))

        def cross(self, cur, nxt, **kw):
            self.calls.append(("cross", nxt))
            if (cur, nxt) == (1, 2):
                return "warp-dead"
            self._pos = (nxt, 1, 1)
            return True

    rig = DeadDoorRig()
    consult = _consult("GIVE_UP")
    runner = LegRunner(rig, goal=2, consult=consult, log=lambda *_: None, learnings_dir=tmp_path)
    result = runner.run()
    assert result["ok"] and (1, 2) in runner.banned
    assert consult.seen == []


def test_the_consult_waits_as_long_as_the_seat_needs(monkeypatch):
    import expedition_crew as crew

    waits = {}

    class _Resp:
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ACTION: GIVE_UP\nWHY: x"}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        waits[json.loads(req.data)["model"]] = timeout
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    consult = supervisor.TapesConsult(log=lambda *_: None)
    consult("navigation", "facts", ["GIVE_UP"])
    consult("puzzle", "facts", ["GIVE_UP"])
    assert waits[crew.CREW["puzzle"]["model"]] > waits[crew.CREW["navigation"]["model"]]


# ------------------------------------------------------------------- the floor's own item balls


def _floor_with_balls():
    grid = ["1" * 8 for _ in range(8)]
    return {
        "maps": {
            "209": {
                "width": 8,
                "height": 8,
                "tileset": 22,
                "grid": grid,
                "warps": [[6, 6, 234, 0]],
                "connections": {},
                "sprites": [
                    {"kind": "item", "x": 3, "y": 4},
                    {"kind": "item", "x": 5, "y": 2},
                    {"kind": "trainer", "x": 1, "y": 1},
                ],
            },
            "234": {
                "width": 8,
                "height": 8,
                "tileset": 22,
                "grid": grid,
                "warps": [],
                "connections": {},
                "sprites": [],
            },
        }
    }


def test_the_sweep_opens_every_ball_the_cartridge_lists_and_reports_the_bag(tmp_path):
    rig = FakeRig(start=(209, 1, 4), truth=_floor_with_balls())
    rig._pickups = {(3, 4): (48, 1), (5, 2): (20, 3)}
    runner = LegRunner(rig, goal=234, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    gained = runner.sweep_items()
    assert sorted(gained) == [(20, 3), (48, 1)]
    assert sorted(c[1] for c in rig.calls if c[0] == "collect") == [(3, 4), (5, 2)]
    assert any(e["event"] == "supervisor.item_collected" for e in rig.events)


def test_a_ball_is_only_tried_once_per_leg(tmp_path):
    rig = FakeRig(start=(209, 1, 4), truth=_floor_with_balls())
    runner = LegRunner(rig, goal=234, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path)
    runner.sweep_items()
    runner.sweep_items()
    assert len([c for c in rig.calls if c[0] == "collect"]) == 2  # two balls, not four


def test_the_sweep_is_offered_only_where_unopened_balls_remain():
    assert "SWEEP_ITEMS" not in menu_for("warp-dead", items=False)
    assert menu_for("warp-dead", items=True)[0] == "SWEEP_ITEMS"


def test_arriving_with_sweep_on_opens_the_floor(tmp_path):
    rig = FakeRig(start=(209, 1, 4), truth=_floor_with_balls())
    rig._pickups = {(3, 4): (48, 1)}
    runner = LegRunner(
        rig, goal=209, sweep=True, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path
    )
    assert runner.run()["ok"]
    assert rig.bag() == [(48, 1)]


# ------------------------------------------------------------------- clearing a story floor


def _top_floor():
    grid = ["1" * 16 for _ in range(18)]
    return {
        "maps": {
            "234": {
                "width": 16,
                "height": 18,
                "tileset": 22,
                "grid": grid,
                "warps": [],
                "connections": {},
                "sprites": [
                    {"kind": "trainer", "x": 1, "y": 9},
                    {"kind": "trainer", "x": 10, "y": 2},
                    {"kind": "npc", "x": 9, "y": 15},
                    {"kind": "item", "x": 2, "y": 12},
                ],
            }
        }
    }


def test_clearing_a_floor_fights_every_trainer_the_cartridge_lists(tmp_path):
    """Silph's top floor changes no badge, so the badge-watching engage is the wrong instrument."""
    rig = FakeRig(start=(234, 8, 8), truth=_top_floor())
    runner = LegRunner(
        rig, goal=234, clear_floor=True, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path
    )
    assert runner.run()["ok"]
    assert runner.engaged == {(1, 9), (10, 2)}  # both trainers, and neither the npc nor the ball
    assert len([e for e in rig.events if e["event"] == "supervisor.trainer_engaged"]) == 2


def test_clearing_a_floor_stops_early_when_a_badge_actually_lands():
    rig = FakeRig(start=(234, 8, 8), truth=_top_floor())
    original = rig.talk

    def talk(face):
        rig._badges = 0b111111
        return original(face)

    rig.talk = talk
    runner = LegRunner(rig, goal=234, clear_floor=True, consult=_consult("GIVE_UP"), log=lambda *_: None)
    assert runner.run()["ok"]
    assert len(runner.engaged) == 1  # the first fight flipped the byte; no need for the second


def test_a_floor_with_no_trainers_says_so_rather_than_claiming_a_clear(tmp_path):
    truth = _top_floor()
    truth["maps"]["234"]["sprites"] = [{"kind": "npc", "x": 9, "y": 15}]
    rig = FakeRig(start=(234, 8, 8), truth=truth)
    runner = LegRunner(
        rig, goal=234, clear_floor=True, consult=_consult("GIVE_UP"), log=lambda *_: None, learnings_dir=tmp_path
    )
    runner.run()
    assert any("lists no trainers" in n for n in runner.notes)


def test_the_lift_tour_is_registered_with_its_own_arguments():
    with pytest.raises(SystemExit):
        supervisor.main(["lift-tour", "--help"])
