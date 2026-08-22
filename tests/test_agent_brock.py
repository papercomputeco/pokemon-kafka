"""Badge 1: the Pewter Center heal loop and the Brock face-cycle (PR #93).

These two methods are what turned four runs' worth of "walk into the Gym and white out" into six
lanes of ``brock_won: true``. Each test pins one branch of the decision the run measured; the
docstrings say which probe or lane it came from so the numbers stay checkable.
"""

from unittest.mock import MagicMock

from agent import (
    PEWTER_CENTER_DOOR,
    PEWTER_CENTER_MAP,
    PEWTER_CITY_MAP,
    PEWTER_GYM_MAP,
    PEWTER_MAX_HEAL_TRIPS,
    POKECENTER_NURSE_TILE,
)
from memory_reader import OverworldState
from test_agent import _make_agent


def _ag(tmp_path, hp, max_hp=48):
    ag = _make_agent(tmp_path)
    ag.memory.read_party = MagicMock(return_value=[{"species": "Charmeleon", "level": 16, "hp": hp, "max_hp": max_hp}])
    ag.memory.read_warps = MagicMock(return_value=[(4, 13, 2)])  # the Gym door mat -> Pewter
    ag._pilot_to = MagicMock(return_value="up")  # any step toward the target; None = standing on it
    return ag


# ---- _pewter_heal_action -------------------------------------------------------------------------


def test_heal_is_pewter_only_and_never_after_the_badge(tmp_path):
    ag = _ag(tmp_path, hp=3)
    assert ag._pewter_heal_action(OverworldState(map_id=51, x=1, y=1)) is None, "not on a Pewter map"
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35, badges=0x01)) is None
    ag.memory.read_party = MagicMock(return_value=[])
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35)) is None, "no party"


def test_pewter_city_walks_to_the_center_when_hp_is_below_the_gate(tmp_path):
    """The lever every prior run missed: the Center is on the arrival map, ~25 turns, worth 40 HP."""
    ag = _ag(tmp_path, hp=20)  # 20/48 = 0.42 < PEWTER_HEAL_GATE
    d = ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35))
    assert d == "up"
    ag._pilot_to.assert_called_with(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35), *PEWTER_CENTER_DOOR)
    assert ag._pewter_heal_trips == 1 and ag._heal_trip_open is True
    # a second call on the same trip does not count another trip
    ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=17, y=30))
    assert ag._pewter_heal_trips == 1


def test_pewter_city_declines_when_healthy_and_presses_into_the_door_when_on_it(tmp_path):
    ag = _ag(tmp_path, hp=48)
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35)) is None
    ag = _ag(tmp_path, hp=10)
    ag._pilot_to = MagicMock(return_value=None)  # standing on the door tile, not warped yet
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=13, y=25)) == "up"


def test_heal_trips_are_capped_so_a_lane_cannot_shuttle_forever(tmp_path):
    ag = _ag(tmp_path, hp=5)
    ag._pewter_heal_trips = PEWTER_MAX_HEAL_TRIPS
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35)) is None
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_GYM_MAP, x=4, y=9)) is None


def test_inside_the_center_it_pilots_to_the_nurse_then_alternates_face_and_talk(tmp_path):
    ag = _ag(tmp_path, hp=20)
    st = OverworldState(map_id=PEWTER_CENTER_MAP, x=1, y=1)
    assert ag._pewter_heal_action(st) == "up"
    ag._pilot_to.assert_called_with(st, *POKECENTER_NURSE_TILE)
    ag._pilot_to = MagicMock(return_value=None)  # on the counter tile
    ag.turn_count = 40
    seq = [ag._pewter_heal_action(st) for _ in range(4)]
    assert seq == ["up", "a", "up", "a"], "face the nurse, press A, repeat — the yes/no box is mashed elsewhere"


def test_inside_the_center_healthy_means_done_and_lets_building_exit_take_over(tmp_path):
    ag = _ag(tmp_path, hp=48)
    ag._heal_trip_open = True
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CENTER_MAP, x=3, y=3)) is None
    assert ag._pewter_heal_done is True and ag._heal_trip_open is False
    # idempotent: a second healthy tick logs nothing new and still defers to _building_exit
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_CENTER_MAP, x=3, y=3)) is None


def test_gym_retreats_to_the_door_below_the_retreat_gate_and_steps_off_the_mat(tmp_path):
    """Probe c: healed lane beat the Jr. Trainer at 12 HP cost, then would have met Brock at 36/48.
    Below PEWTER_GYM_RETREAT_GATE it goes back out to heal rather than fight at a deficit."""
    ag = _ag(tmp_path, hp=30)  # 0.625 < 0.9
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=4, y=6)
    assert ag._pewter_heal_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 4, 13)  # nearest warp = the door mat
    assert ag._gym_retreat is True
    ag._pilot_to = MagicMock(return_value=None)  # standing on the mat and not warped: step south off it
    assert ag._pewter_heal_action(st) == "down"


def test_gym_does_not_retreat_when_healthy_or_when_the_map_has_no_warps(tmp_path):
    ag = _ag(tmp_path, hp=48)
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_GYM_MAP, x=4, y=6)) is None
    ag = _ag(tmp_path, hp=10)
    ag.memory.read_warps = MagicMock(return_value=[])
    assert ag._pewter_heal_action(OverworldState(map_id=PEWTER_GYM_MAP, x=4, y=6)) is None


# ---- _brock_engage_action ------------------------------------------------------------------------


def test_brock_engage_only_fires_in_his_row_without_the_badge(tmp_path):
    ag = _ag(tmp_path, hp=48)
    assert ag._brock_engage_action(OverworldState(map_id=PEWTER_CITY_MAP, x=5, y=1)) is None
    assert ag._brock_engage_action(OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=0x01)) is None
    assert ag._brock_engage_action(OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=3)) is None, "y>2: not his row"
    assert ag._brock_engage_action(OverworldState(map_id=PEWTER_GYM_MAP, x=1, y=1)) is None, "x<3: off the row"


def test_brock_engage_cycles_facing_with_an_a_press_between_each(tmp_path):
    """Probe E stood on (5,1) for 2000 turns and never fought: facing is not a plan input, so cycle
    it. Brock is adjacent from that tile in exactly one direction; the press that finds him opens
    the challenge and then the battle (measured: 11 battle turns from here)."""
    ag = _ag(tmp_path, hp=48)
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1)
    seq = [ag._brock_engage_action(st) for _ in range(9)]
    assert seq == ["up", "a", "left", "a", "right", "a", "down", "a", "up"]


# ---- the dispatch in the overworld step -----------------------------------------------------------


def test_overworld_step_pins_quest_nav_inside_the_gym_and_dispatches_engage(tmp_path):
    """A backtrack restore in the Gym yanked the lane off Brock's tile back to (4,13) three times
    (probe E). Inside map 54 without the badge, restores are off and the engage action wins."""
    ag = _ag(tmp_path, hp=48)
    ag.door_cooldown = 0
    ag._pewter_heal_action = MagicMock(return_value=None)
    ag._brock_engage_action = MagicMock(return_value="a")
    ag._quest_nav_active = False
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1)
    assert ag.choose_overworld_action(st) == "a"
    assert ag._quest_nav_active is True


def test_overworld_step_prefers_the_heal_over_everything_else_in_pewter(tmp_path):
    ag = _ag(tmp_path, hp=48)
    ag.door_cooldown = 0
    ag._pewter_heal_action = MagicMock(return_value="left")
    ag._brock_engage_action = MagicMock(return_value="a")
    assert ag.choose_overworld_action(OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=35)) == "left"
    ag._brock_engage_action.assert_not_called()


# ---- brock_won measurement: keep the highest enemy level seen, not the first-turn snapshot -------


def test_battle_records_the_highest_enemy_level_seen_and_backfills_an_unknown_species(tmp_path):
    """`brock_won` was null on lanes that DID win: the first-turn snapshot can read the enemy struct
    mid-write (a lower level, species "Unknown"), and the gym-leader check keys off that level.
    Keep the max observed during the fight and let a real species name replace "Unknown"."""
    from unittest.mock import patch

    from memory_reader import BattleState
    from test_agent_quest_coverage import TestRunLoopHooks, _wild

    ag = _make_agent(tmp_path)
    TestRunLoopHooks()._battle_helpers(ag)
    # The loop reads battle state more than once per turn (the wedge watchdog re-reads it), so
    # drive it statefully: the very first read is the mid-write snapshot, every later read is Onix
    # at its real level, and the fight ends after a few turns.
    reads = {"n": 0}

    def battle_state():
        reads["n"] += 1
        if reads["n"] == 1:
            return _wild(battle_type=2, enemy_level=12, enemy_species=0)  # mid-write snapshot -> "#00"
        if reads["n"] < 12:
            return _wild(battle_type=2, enemy_level=14, enemy_species=0x22)  # what it really is
        return BattleState(battle_type=0)

    ag.memory.read_battle_state = MagicMock(side_effect=battle_state)
    ag.memory.read_overworld_state = MagicMock(return_value=OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1))
    import agent as agent_mod

    with patch.object(agent_mod, "Image", None):
        ag.run(max_turns=6)
    assert ag._battle_opponent_level == 14, "the max seen, not the first-turn snapshot"
    # the first snapshot's species ("#00") is kept — only an empty/"Unknown" name is backfilled;
    # what matters for brock_won is the level (>= 12 identifies the gym leader).
    assert ag._battle_opponent_species in ("#00", "Onix")


def test_battle_backfills_the_species_when_the_first_snapshot_named_none(tmp_path):
    """The other half of the max-level guard: a snapshot that yields no species name is replaced by
    the first real one. `BattleState.enemy_species_name` never returns "" or "Unknown" for the
    Red/Blue reader (unmapped bytes render as "#XX"), so this models a reader that does — the
    condition is written for that case and is otherwise unreachable through run()."""
    from unittest.mock import PropertyMock, patch

    from memory_reader import BattleState
    from test_agent_quest_coverage import TestRunLoopHooks, _wild

    ag = _make_agent(tmp_path)
    TestRunLoopHooks()._battle_helpers(ag)
    reads = {"n": 0}

    def battle_state():
        reads["n"] += 1
        if reads["n"] < 12:
            return _wild(battle_type=2, enemy_level=14 if reads["n"] > 1 else 12, enemy_species=0x22)
        return BattleState(battle_type=0)

    ag.memory.read_battle_state = MagicMock(side_effect=battle_state)
    ag.memory.read_overworld_state = MagicMock(return_value=OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1))
    names = iter(["Unknown"] + ["Onix"] * 40)
    import agent as agent_mod

    with (
        patch.object(agent_mod, "Image", None),
        patch.object(BattleState, "enemy_species_name", new_callable=PropertyMock, side_effect=lambda: next(names)),
    ):
        ag.run(max_turns=6)
    assert ag._battle_opponent_level == 14
    assert ag._battle_opponent_species == "Onix"


# ---- Brock identification after the badge --------------------------------------------------


def _run_one_trainer_fight(tmp_path, map_id, pre_badges, enemy_level=14):
    """Drive run() through a single trainer battle on ``map_id`` with ``pre_badges`` already held."""
    from unittest.mock import patch

    import agent as agent_mod
    from memory_reader import BattleState
    from test_agent_quest_coverage import TestRunLoopHooks, _wild

    ag = _make_agent(tmp_path)
    TestRunLoopHooks()._battle_helpers(ag)
    reads = {"n": 0}

    def battle_state():
        reads["n"] += 1
        return _wild(battle_type=2, enemy_level=enemy_level, enemy_species=0x22) if reads["n"] < 12 else BattleState(0)

    def mem_read(addr):
        if addr == ag.memory.ADDR_BADGES:
            return pre_badges
        if addr == ag.memory.ADDR_MAP_ID:
            return map_id
        return 0

    ag.memory.read_battle_state = MagicMock(side_effect=battle_state)
    ag.memory._read = MagicMock(side_effect=mem_read)
    ag.memory.read_overworld_state = MagicMock(return_value=OverworldState(map_id=map_id, x=5, y=1, badges=pre_badges))
    with patch.object(agent_mod, "Image", None):
        ag.run(max_turns=6)
    return ag


def test_a_trainer_fought_with_the_badge_already_in_hand_is_not_brock(tmp_path):
    """Brock is the fight that *earns* the Boulder Badge, so holding it first disqualifies the
    fight. Without this gate a seeded post-badge leg matched the ">= 12 is the gym leader"
    fallback on the first Route 3 trainer, and `_resolve_brock_badge` read the bit that was
    already set — so the run claimed a win it never fought. Beat 11 recorded `brock_turns: 4`
    exactly this way, on a seed whose badge came from a different run entirely."""
    from agent import ROUTE_3_MAP

    ag = _run_one_trainer_fight(tmp_path, ROUTE_3_MAP, pre_badges=0x01)
    assert ag.brock_turns is None and ag.brock_won is None
    assert ag.brock_lead_species is None and ag.brock_lead_level is None


def test_the_badgeless_gym_fight_is_still_recorded(tmp_path):
    """The gate must not cost the real detection: same fight, no badge yet, still Brock."""
    ag = _run_one_trainer_fight(tmp_path, PEWTER_GYM_MAP, pre_badges=0x00)
    assert ag.brock_turns is not None
    assert ag.brock_lead_level is not None
