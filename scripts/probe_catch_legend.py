"""Stage C: catch the (6,1) legendary from platform_main.state (162 (7,2)).

Plan from the measured movesets: lead Charizard -> switch Dugtrio; SCRATCH once (~35%), SAND-ATTACK x2; switch
Hypno; POISON GAS until 'poisoned' (the catch formula's status bonus); then ULTRA BALL every turn, switching the
tank when its HP < 35%. Verdict: the game's own 'caught' page / the battle ending with the enemy standing."""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/platform_main.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
ag, mr = rig.ag, rig.ag.memory
LOG = []


def enemy_name(bs):
    v = getattr(bs, "enemy_species_name", None)
    if v is None:
        v = getattr(mr, "enemy_species_name", None)
    try:
        return v() if callable(v) else (v if v is not None else f"species#{bs.enemy_species}")
    except Exception:
        return f"species#{bs.enemy_species}"


def journal(c):
    append_observations(
        "pokedex/memory",
        [
            {
                "referenced_time": datetime.now(timezone.utc).isoformat(),
                "priority": "important",
                "source_session": "extractor",
                "content": c,
            }
        ],
        dedupe=True,
    )


def in_battle():
    return bool(rig.mem[qm.ADDR_IN_BATTLE])


def pages_until_menu(cap=60):
    """Advance text with B until the battle menu is drawn (or the battle ends); return the distinct pages."""
    out = []
    for _ in range(cap):
        if not in_battle():
            t = rig.textbox()
            if t and (not out or t != out[-1]):
                out.append(t)
            return out
        if mr.battle_menu_visible():
            return out
        t = rig.textbox()
        if t and (not out or t != out[-1]):
            out.append(t)
        rig.ctl.press("b")
        rig.ctl.wait(24)
    return out


def bag_index(name):
    for i, (n, _q) in enumerate(rig.bag_named(full=True)):
        if n == name:
            return i
    return None


def do_fight(slot):
    bs = mr.read_battle_state()
    if not ag._select_battle_menu("fight"):
        return []
    ag._select_move_slot(slot)
    ag._await_turn_resolved(bs.enemy_hp, bs.player_hp, list(bs.move_pp))
    return pages_until_menu()


def do_switch(party_index):
    if not ag._select_battle_menu("pkmn"):
        return []
    rig.ctl.wait(20)
    rig.ctl.navigate_menu(party_index)
    rig.ctl.wait(120)
    rig.ctl.mash_a(5, delay=30)
    rig.ctl.wait(60)
    return pages_until_menu()


def do_ball():
    idx = bag_index("ULTRA BALL")
    if idx is None or not ag._select_battle_menu("item"):
        return [], False
    rig.ctl.wait(20)
    for _ in range(24):
        pos = mr._read(0xCC36) + mr._read(0xCC26)
        if pos == idx:
            break
        rig.ctl.press("down" if pos < idx else "up")
        rig.ctl.wait(12)
    rig.ctl.press("a")
    rig.ctl.wait(120)
    rig.ctl.mash_a(3, delay=30)
    pages = pages_until_menu(cap=80)
    caught = any("caught" in p.lower() for p in pages) or (not in_battle() and mr.read_enemy_hp() > 0)
    return pages, caught


def active_hp_frac():
    bs = mr.read_battle_state()
    return (bs.player_hp / bs.player_max_hp) if bs.player_max_hp else 1.0, bs


print("start", rig.pos(), "balls", dict(rig.bag_named(full=True)).get("ULTRA BALL"), flush=True)
# engage: stand at (6,2), face up, A until the battle starts
rig.walk(162, {(6, 2)}, battle=rig.battle) if not in_battle() else None
if rig.pos()[1:] != (6, 2) and not in_battle():
    print("cannot stand at (6,2):", rig.pos(), flush=True)
    sys.exit(1)
rig.io.press("up", hold=4, release=8)
rig.ctl.wait(16)
cry = []
for _ in range(12):
    if in_battle():
        break
    rig.ctl.press("a")
    rig.ctl.wait(50)
    t = rig.textbox()
    if t and (not cry or t != cry[-1]):
        cry.append(t)
rig.ctl.wait(120)
bs = mr.read_battle_state()
print(
    "engaged:",
    cry,
    "| enemy",
    enemy_name(bs),
    "L",
    bs.enemy_level,
    "hp",
    bs.enemy_hp,
    "/",
    bs.enemy_max_hp,
    flush=True,
)
journal(f"map=162 (6,1) engaged: {cry}; enemy {enemy_name(bs)} L{bs.enemy_level} hp {bs.enemy_hp}/{bs.enemy_max_hp}")
rig.screenshot("legend_battle_start")
pages_until_menu()
phase = ["switch_dug", "scratch", "sand", "sand", "switch_hyp", "gas"]
poisoned = False
throws = 0
caught = False
for turn in range(90):
    if not in_battle():
        break
    frac, bs = active_hp_frac()
    if bs.enemy_hp == 0:
        print("the enemy fainted", flush=True)
        break
    # tank guard
    if frac < 0.35:
        party = rig.party()
        pick = max(
            (i for i in (0, 2, 3, 4, 1) if party[i][2] > 0 and i != bs.player_species),
            key=lambda i: party[i][2],
            default=None,
        )
        if pick is not None:
            print(f"turn {turn}: tank at {frac:.0%}, switching to {party[pick][0]}", flush=True)
            LOG.append(do_switch(pick))
            continue
    if phase:
        step = phase.pop(0)
        if step == "switch_dug":
            p = do_switch(1)
        elif step == "scratch":
            p = do_fight(0)
        elif step == "sand":
            p = do_fight(3)
        elif step == "switch_hyp":
            p = do_switch(4)
        elif step == "gas":
            p = do_fight(1)
            if any("poison" in x.lower() for x in p):
                poisoned = True
            elif len([1 for x in LOG if x and any("POISON GAS" in y for y in x)]) < 6:
                phase.insert(0, "gas")
        LOG.append(p)
        bs2 = mr.read_battle_state()
        print(
            f"turn {turn}: {step} -> enemy {bs2.enemy_hp}/{bs2.enemy_max_hp} poisoned={poisoned} | {p[-2:]}", flush=True
        )
        continue
    p, caught = do_ball()
    throws += 1
    LOG.append(p)
    bs2 = mr.read_battle_state()
    print(
        f"turn {turn}: ULTRA BALL #{throws} -> caught={caught} enemy {bs2.enemy_hp}/{bs2.enemy_max_hp} | {p[-3:]}",
        flush=True,
    )
    if caught:
        break
    if dict(rig.bag_named(full=True)).get("ULTRA BALL", 0) == 0:
        print("out of balls", flush=True)
        break
rig.screenshot("legend_battle_end")
tail = [p for p in LOG[-3:]]
print("caught:", caught, "throws:", throws, "in_battle:", in_battle(), "party:", rig.party(), flush=True)
journal(f"map=162 CATCH ATTEMPT: caught={caught} throws={throws} poisoned={poisoned}; last pages {tail}")
if caught:
    for _ in range(12):  # nickname prompt (B = no), transfer text
        rig.ctl.press("b")
        rig.ctl.wait(30)
    rig.bank("seafoam_legend_caught")
    print("*** LEGENDARY CAUGHT -- banked seafoam_legend_caught ***", rig.pos(), flush=True)
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
