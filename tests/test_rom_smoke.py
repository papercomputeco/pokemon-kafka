"""Boot each real ROM headless, script through the intro, and verify the profile
reads true values: bedroom map 38, empty party, ₽3000 (same expectations across
Red, Blue, and Yellow). This is the empirical gate that the Yellow -1 address
shift is correct on real emulator state — unit tests only prove the tables'
internal consistency.

Auto-skips when no ROMs are present (rom/ ships only locally). Deselect with
``-m "not rom"`` when iterating on fast tests.
"""

from pathlib import Path

import pytest

ROM_DIR = Path(__file__).resolve().parent.parent / "rom"
ROMS = sorted(ROM_DIR.glob("*.gb")) if ROM_DIR.exists() else []

pytestmark = [
    pytest.mark.rom,
    pytest.mark.skipif(not ROMS, reason="no ROMs present under rom/"),
]

EXPECTED_PROFILE = {
    "POKEMON RED": "red_blue",
    "POKEMON BLUE": "red_blue",
    "POKEMON YELLOW": "yellow",
}


def _run_intro(controller):
    """Mirror agent._advance_intro: title -> (NEW GAME) -> mash A through Oak/naming."""
    controller.wait(1500)
    controller.press("start")
    controller.wait(60)
    # With a save present the menu is CONTINUE/NEW GAME (DOWN selects NEW GAME);
    # without one, NEW GAME is already selected and DOWN+A lands harmlessly.
    controller.press("down")
    controller.wait(30)
    controller.press("a")
    controller.wait(60)
    for _ in range(600):
        controller.press("a")
        controller.wait(30)
    for _ in range(10):
        controller.press("b")
        controller.wait(15)


@pytest.mark.parametrize("rom", ROMS, ids=lambda r: r.name.split(" (")[0].replace(" ", "_"))
def test_intro_reaches_bedroom(rom):
    from agent import GameController
    from game_profile import detect_profile
    from memory_reader import MemoryReader
    from pyboy import PyBoy

    pyboy = PyBoy(str(rom), window="null")
    try:
        pyboy.set_emulation_speed(0)
        profile = detect_profile(pyboy)
        assert profile.name == EXPECTED_PROFILE[pyboy.cartridge_title.strip()]
        reader = MemoryReader(pyboy, profile)
        _run_intro(GameController(pyboy))
        state = reader.read_overworld_state()
        assert state.map_id == 38, f"{rom.name}: expected bedroom (38), got map {state.map_id}"
        assert state.party_count == 0, f"{rom.name}: party should be empty, got {state.party_count}"
        assert state.money == 3000, f"{rom.name}: money should read 3000, got {state.money}"
    finally:
        pyboy.stop()


def test_item_names_come_from_this_cartridge_and_match_what_was_measured_live():
    """The bag is a list of numeric ids, and every prior session reasoned about them from recall.

    The cross-checks are items whose identity was established *live* in the Rocket Hideout —
    if the decode were wrong, these would not line up.
    """
    import rom_truth as rt

    items = rt.item_names(rt.ROM_DEFAULT.read_bytes())
    assert items["1"] == "MASTER BALL"
    assert items["72"] == "SILPH SCOPE"
    assert items["73"] == "POKe FLUTE"
    assert items["74"] == "LIFT KEY"
    assert items["60"] == "FRESH WATER"
    assert all(name.strip() for name in items.values())


def test_the_extracted_truth_carries_the_item_table():
    import rom_truth as rt

    assert rt.load_truth()["items"]["74"] == "LIFT KEY"


def test_item_balls_name_what_they_hold():
    """Rocket Hideout B4F (map 202) is the cross-check: both of its balls were opened live this
    run, and the bag gained SILPH SCOPE and LIFT KEY. If the object-data item byte decoded
    wrong, these would not line up — and the two sessions spent sweeping Silph for the CARD KEY
    would have been one lookup: map 210, (21,16).
    """
    import rom_truth as rt

    truth = rt.load_truth()
    items = truth["items"]

    def balls(map_id: int) -> dict[tuple[int, int], str]:
        return {
            (s["x"], s["y"]): items[str(s["item"])]
            for s in truth["maps"][str(map_id)]["sprites"]
            if s["kind"] == "item"
        }

    assert balls(202)[(25, 2)] == "SILPH SCOPE"
    assert balls(202)[(10, 2)] == "LIFT KEY"
    assert balls(210)[(21, 16)] == "CARD KEY"


def test_hms_are_never_item_balls_always_a_person():
    """A rule the human supplied from real play (not this session's recall): HM items are never
    dropped as a field item ball, always handed over by an NPC. Verified across all five HMs on
    this cartridge, not assumed — this project has already lost time to exactly this shape of
    question (the BIKE VOUCHER, HM04/STRENGTH) checked one HM at a time, ad hoc, per mission.
    """
    import rom_truth as rt

    truth = rt.load_truth()
    hm_ids = {k for k, v in truth["items"].items() if v.strip().startswith("HM")}
    assert len(hm_ids) == 5  # HM01..HM05 — if this drops, the item table decode broke
    ball_ids = {str(s["item"]) for m in truth["maps"].values() for s in (m.get("sprites") or []) if s["kind"] == "item"}
    assert not (hm_ids & ball_ids), "an HM turned up as a field item ball — a person always gives it instead"
