# SURF works, and surfability is not a tile id (2026-09-02)

Measured on map 30 from `b7_badge.state`, the baton the badge-7 crew stalled on. Result:
**`use_field_move("SURF", species="Gyarados")` armed and the player moved** — (6,4) → (6,6) →
(6,7), banked `b7_surfing.state`. The crew's leg was not blocked by the menu and not blocked by
the cartridge; it was blocked by facing the wrong way and reading the refusal as a menu defect.

## The cursor glyph was a real tile, and the constant was right by luck

`CURSOR_TILE = 0xED` was written from assumption, which is the one thing this repo forbids. It
happens to be correct, and now it is measured rather than believed: with the start menu open,
moving the cursor from entry 0 to entry 1 moved tile `0xED` from window row 2 to row 4, and the
tile it swapped with is `0x17F`, not `0x7F`.

    cursor 0 -> 1
      row 2: [(11, '0xed', '0x17f')]
      row 4: [(11, '0x17f', '0xed')]

So blank on the window layer is `0x17F` — PyBoy offsets window tile ids by `0x100` — while the
cursor glyph itself reads as a bare `0xED`. An earlier probe that sampled only columns 0-5 saw
`0x100`-range border tiles and nearly bought the conclusion that `0xED` never matches.

The cursor sits in the column *left* of the text, so on the start menu masked and raw decode
identically (`'POKéDEX'` either way). The `AAAAAAAASURF` splice `field_moves` was blamed for is
**not** the cursor: it is the roster rendering under the field submenu, and `use_field_move`
already handles it by anchoring on CANCEL and matching by containment rather than `startswith`.
Two different defects wearing the same symptom.

## The refusal sentence, and what it is not

Facing up: **"No SURFing on GYARADOS here!"**. Facing down, from the same cell, with the same
party and the same menu path: the player surfed.

The tiles are the same id. `(6,3)` and `(6,5)` both read `0x36` out of the extracted grid, so
whatever the engine consults to allow a surf, our collision model does not express it as a
property of the tile the player faces. **Do not add a "water tile id" constant** — the histogram
that suggests one is seductive (`0x14` is 818 of map 30's 1080 cells, 1398 of map 31's 1800, and
non-walkable in all three water maps) and it does not predict this refusal.

The cheap, correct probe is the game's own sentence: arm SURF, read the text box, and if the
position changed the direction was water. Four presses answers what an address hunt did not.

## The island is a strip, and that is why the leg looked sealed

From (6,4) the body-aware walkable region on map 30 is **six cells**: (6,4) through (11,4), a
one-tile-tall strip. No cell in it is adjacent to a `0x14` tile. A leg that asks "can I walk to
water" gets no for a correct reason and the wrong conclusion — the crossing continues by surfing
off the strip, not by finding a shore.

## Operating note for the next leg

- Baton: `b7_surfing.state`, map 30 at (6,7), **on the water**, party healthy (Gyarados L20 73/73,
  Dugtrio 100, Primeape 99, Pidgeot 99, Hypno 99, Charizard 100).
- Keep Gyarados **off the lead** and awake. Gen 1 omits fainted members from the POKéMON menu, so
  a fainted surfer is an unusable surfer — that is what ended the previous leg.
- `rom_truth` already locates the tileset table by signature (`TILESETS = 0xC7BE`). A leg that
  finds itself typing a hex offset into a probe has left the doctrine; the table is a lookup.
