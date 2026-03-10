"""Tests for memory_reader.py — targeting 100% line coverage."""

import pytest
from memory_reader import BattleState, OverworldState, MemoryReader, CollisionMap


# ---------------------------------------------------------------------------
# Dataclass default-value tests
# ---------------------------------------------------------------------------

class TestBattleStateDefaults:
    def test_defaults(self):
        bs = BattleState()
        assert bs.battle_type == 0
        assert bs.enemy_hp == 0
        assert bs.enemy_max_hp == 0
        assert bs.enemy_level == 0
        assert bs.enemy_species == 0
        assert bs.player_hp == 0
        assert bs.player_max_hp == 0
        assert bs.player_level == 0
        assert bs.player_species == 0
        assert bs.moves == [0, 0, 0, 0]
        assert bs.move_pp == [0, 0, 0, 0]
        assert bs.party_count == 0
        assert bs.party_hp == []


class TestOverworldStateDefaults:
    def test_defaults(self):
        ow = OverworldState()
        assert ow.map_id == 0
        assert ow.x == 0
        assert ow.y == 0
        assert ow.badges == 0
        assert ow.party_count == 0
        assert ow.party_hp == []
        assert ow.money == 0
        assert ow.text_box_active is False


# ---------------------------------------------------------------------------
# Low-level read helpers
# ---------------------------------------------------------------------------

class TestRead:
    def test_read_returns_byte(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[0x1234] = 0xAB
        assert reader._read(0x1234) == 0xAB

    def test_read_unset_address_returns_zero(self, mock_pyboy):
        reader = MemoryReader(mock_pyboy)
        assert reader._read(0x9999) == 0


class TestRead16:
    def test_read_16_combines_hi_lo(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[0x0010] = 0x01  # high byte
        fake_memory[0x0011] = 0x2C  # low byte
        assert reader._read_16(0x0010, 0x0011) == 0x012C  # 300

    def test_read_16_max_value(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[0x0010] = 0xFF
        fake_memory[0x0011] = 0xFF
        assert reader._read_16(0x0010, 0x0011) == 0xFFFF


class TestReadBCD:
    def test_single_byte_bcd(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        # 0x49 -> high=4, low=9 -> 49
        fake_memory[0x0001] = 0x49
        assert reader._read_bcd(0x0001) == 49

    def test_multi_byte_bcd(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        # Encoding of 123456:
        # byte1=0x12 -> 12, byte2=0x34 -> 34, byte3=0x56 -> 56
        # result = ((12)*100 + 34)*100 + 56 = 123456
        fake_memory[0x0001] = 0x12
        fake_memory[0x0002] = 0x34
        fake_memory[0x0003] = 0x56
        assert reader._read_bcd(0x0001, 0x0002, 0x0003) == 123456

    def test_bcd_zero(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[0x0001] = 0x00
        fake_memory[0x0002] = 0x00
        fake_memory[0x0003] = 0x00
        assert reader._read_bcd(0x0001, 0x0002, 0x0003) == 0


# ---------------------------------------------------------------------------
# read_battle_state
# ---------------------------------------------------------------------------

class TestReadBattleState:
    def test_no_battle_returns_early(self, mock_pyboy, fake_memory):
        """battle_type == 0 should return default BattleState immediately."""
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_BATTLE_TYPE] = 0
        state = reader.read_battle_state()
        assert state.battle_type == 0
        assert state.enemy_hp == 0
        assert state.moves == [0, 0, 0, 0]
        assert state.party_hp == []

    def test_wild_battle_full_read(self, mock_pyboy, fake_memory):
        """battle_type > 0 should populate every field."""
        reader = MemoryReader(mock_pyboy)
        mem = fake_memory

        mem[MemoryReader.ADDR_BATTLE_TYPE] = 1  # wild battle

        # Enemy: HP=120, MaxHP=150, Level=7, Species=4
        mem[MemoryReader.ADDR_ENEMY_HP_HI] = 0x00
        mem[MemoryReader.ADDR_ENEMY_HP_LO] = 120
        mem[MemoryReader.ADDR_ENEMY_MAX_HP_HI] = 0x00
        mem[MemoryReader.ADDR_ENEMY_MAX_HP_LO] = 150
        mem[MemoryReader.ADDR_ENEMY_LEVEL] = 7
        mem[MemoryReader.ADDR_ENEMY_SPECIES] = 4

        # Player: HP=200, MaxHP=250, Level=10, Species=0xB0
        mem[MemoryReader.ADDR_PLAYER_HP_HI] = 0x00
        mem[MemoryReader.ADDR_PLAYER_HP_LO] = 200
        mem[MemoryReader.ADDR_PLAYER_MAX_HP_HI] = 0x00
        mem[MemoryReader.ADDR_PLAYER_MAX_HP_LO] = 250
        mem[MemoryReader.ADDR_PLAYER_LEVEL] = 10
        mem[MemoryReader.ADDR_PLAYER_SPECIES] = 0xB0

        # Moves
        mem[MemoryReader.ADDR_MOVE_1] = 33   # Tackle
        mem[MemoryReader.ADDR_MOVE_2] = 45   # Growl
        mem[MemoryReader.ADDR_MOVE_3] = 52   # Ember
        mem[MemoryReader.ADDR_MOVE_4] = 0

        # PP
        mem[MemoryReader.ADDR_PP_1] = 35
        mem[MemoryReader.ADDR_PP_2] = 40
        mem[MemoryReader.ADDR_PP_3] = 25
        mem[MemoryReader.ADDR_PP_4] = 0

        # Party: 2 pokemon
        mem[MemoryReader.ADDR_PARTY_COUNT] = 2
        base0 = MemoryReader.PARTY_BASE
        mem[base0 + MemoryReader.PARTY_HP_OFFSET] = 0x00
        mem[base0 + MemoryReader.PARTY_HP_OFFSET + 1] = 200
        base1 = MemoryReader.PARTY_BASE + MemoryReader.PARTY_STRUCT_SIZE
        mem[base1 + MemoryReader.PARTY_HP_OFFSET] = 0x00
        mem[base1 + MemoryReader.PARTY_HP_OFFSET + 1] = 50

        state = reader.read_battle_state()

        assert state.battle_type == 1
        assert state.enemy_hp == 120
        assert state.enemy_max_hp == 150
        assert state.enemy_level == 7
        assert state.enemy_species == 4
        assert state.player_hp == 200
        assert state.player_max_hp == 250
        assert state.player_level == 10
        assert state.player_species == 0xB0
        assert state.moves == [33, 45, 52, 0]
        assert state.move_pp == [35, 40, 25, 0]
        assert state.party_count == 2
        assert state.party_hp == [200, 50]

    def test_trainer_battle(self, mock_pyboy, fake_memory):
        """battle_type == 2 (trainer) also triggers the full read path."""
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_BATTLE_TYPE] = 2
        fake_memory[MemoryReader.ADDR_PARTY_COUNT] = 0
        state = reader.read_battle_state()
        assert state.battle_type == 2
        assert state.party_hp == []


# ---------------------------------------------------------------------------
# read_overworld_state
# ---------------------------------------------------------------------------

class TestReadOverworldState:
    def test_full_overworld_read(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        mem = fake_memory

        mem[MemoryReader.ADDR_MAP_ID] = 12
        mem[MemoryReader.ADDR_PLAYER_X] = 5
        mem[MemoryReader.ADDR_PLAYER_Y] = 10
        mem[MemoryReader.ADDR_BADGES] = 0x03  # 2 badges
        mem[MemoryReader.ADDR_PARTY_COUNT] = 1

        # Party HP for 1 pokemon: 45
        base0 = MemoryReader.PARTY_BASE
        mem[base0 + MemoryReader.PARTY_HP_OFFSET] = 0x00
        mem[base0 + MemoryReader.PARTY_HP_OFFSET + 1] = 45

        # Money: $1234 => BCD 0x00, 0x12, 0x34
        mem[MemoryReader.ADDR_MONEY_1] = 0x00
        mem[MemoryReader.ADDR_MONEY_2] = 0x12
        mem[MemoryReader.ADDR_MONEY_3] = 0x34

        # No text box active
        mem[MemoryReader.ADDR_WD730] = 0x00

        state = reader.read_overworld_state()

        assert state.map_id == 12
        assert state.x == 5
        assert state.y == 10
        assert state.badges == 0x03
        assert state.party_count == 1
        assert state.party_hp == [45]
        assert state.money == 1234
        assert state.text_box_active is False

    def test_overworld_with_text_box_active(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_WD730] = 0x62
        fake_memory[MemoryReader.ADDR_PARTY_COUNT] = 0
        fake_memory[MemoryReader.ADDR_MONEY_1] = 0x00
        fake_memory[MemoryReader.ADDR_MONEY_2] = 0x00
        fake_memory[MemoryReader.ADDR_MONEY_3] = 0x00

        state = reader.read_overworld_state()
        assert state.text_box_active is True


# ---------------------------------------------------------------------------
# _is_text_or_script_active
# ---------------------------------------------------------------------------

class TestIsTextOrScriptActive:
    @pytest.mark.parametrize(
        "d730_val, expected",
        [
            (0x00, False),   # no bits set
            (0x02, True),    # bit 1 set (0x02 & 0x62 = 0x02)
            (0x20, True),    # bit 5 set (0x20 & 0x62 = 0x20)
            (0x40, True),    # bit 6 set (0x40 & 0x62 = 0x40)
            (0x62, True),    # all relevant bits set
            (0x01, False),   # bit 0 only — not in mask
            (0x80, False),   # bit 7 only — not in mask
            (0x9D, False),   # 0x9D = 10011101 — 0x9D & 0x62 = 0x00
        ],
    )
    def test_text_or_script_flag(self, mock_pyboy, fake_memory, d730_val, expected):
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_WD730] = d730_val
        assert reader._is_text_or_script_active() is expected


# ---------------------------------------------------------------------------
# _read_party_hp
# ---------------------------------------------------------------------------

class TestReadPartyHP:
    def test_zero_party_members(self, mock_pyboy):
        reader = MemoryReader(mock_pyboy)
        assert reader._read_party_hp(0) == []

    def test_one_party_member(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        base = MemoryReader.PARTY_BASE
        fake_memory[base + MemoryReader.PARTY_HP_OFFSET] = 0x00
        fake_memory[base + MemoryReader.PARTY_HP_OFFSET + 1] = 100
        assert reader._read_party_hp(1) == [100]

    def test_two_party_members(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        base0 = MemoryReader.PARTY_BASE
        fake_memory[base0 + MemoryReader.PARTY_HP_OFFSET] = 0x00
        fake_memory[base0 + MemoryReader.PARTY_HP_OFFSET + 1] = 80

        base1 = MemoryReader.PARTY_BASE + MemoryReader.PARTY_STRUCT_SIZE
        fake_memory[base1 + MemoryReader.PARTY_HP_OFFSET] = 0x01
        fake_memory[base1 + MemoryReader.PARTY_HP_OFFSET + 1] = 0x00
        # 0x0100 = 256
        assert reader._read_party_hp(2) == [80, 256]

    def test_capped_at_six(self, mock_pyboy, fake_memory):
        """Passing count=7 should still only read 6 entries (min(7, 6))."""
        reader = MemoryReader(mock_pyboy)
        for i in range(7):
            base = MemoryReader.PARTY_BASE + (i * MemoryReader.PARTY_STRUCT_SIZE)
            fake_memory[base + MemoryReader.PARTY_HP_OFFSET] = 0x00
            fake_memory[base + MemoryReader.PARTY_HP_OFFSET + 1] = 10 + i

        result = reader._read_party_hp(7)
        assert len(result) == 6
        assert result == [10, 11, 12, 13, 14, 15]

    def test_exactly_six(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        for i in range(6):
            base = MemoryReader.PARTY_BASE + (i * MemoryReader.PARTY_STRUCT_SIZE)
            fake_memory[base + MemoryReader.PARTY_HP_OFFSET] = 0x00
            fake_memory[base + MemoryReader.PARTY_HP_OFFSET + 1] = 20 + i

        result = reader._read_party_hp(6)
        assert len(result) == 6
        assert result == [20, 21, 22, 23, 24, 25]


# ---------------------------------------------------------------------------
# is_in_battle
# ---------------------------------------------------------------------------

class TestIsInBattle:
    def test_not_in_battle(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_BATTLE_TYPE] = 0
        assert reader.is_in_battle() is False

    def test_in_wild_battle(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_BATTLE_TYPE] = 1
        assert reader.is_in_battle() is True

    def test_in_trainer_battle(self, mock_pyboy, fake_memory):
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_BATTLE_TYPE] = 2
        assert reader.is_in_battle() is True


# ---------------------------------------------------------------------------
# player_whited_out
# ---------------------------------------------------------------------------

class TestPlayerWhitedOut:
    def test_all_fainted(self, mock_pyboy, fake_memory):
        """All party pokemon at 0 HP -> whited out."""
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_PARTY_COUNT] = 2
        # Both at 0 HP (default memory is 0)
        assert reader.player_whited_out() is True

    def test_some_alive(self, mock_pyboy, fake_memory):
        """At least one pokemon alive -> not whited out."""
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_PARTY_COUNT] = 2
        base0 = MemoryReader.PARTY_BASE
        # First pokemon fainted (0 HP — default)
        # Second pokemon alive
        base1 = MemoryReader.PARTY_BASE + MemoryReader.PARTY_STRUCT_SIZE
        fake_memory[base1 + MemoryReader.PARTY_HP_OFFSET] = 0x00
        fake_memory[base1 + MemoryReader.PARTY_HP_OFFSET + 1] = 25
        assert reader.player_whited_out() is False

    def test_first_alive(self, mock_pyboy, fake_memory):
        """First pokemon alive triggers early return False in the loop."""
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_PARTY_COUNT] = 1
        base0 = MemoryReader.PARTY_BASE
        fake_memory[base0 + MemoryReader.PARTY_HP_OFFSET] = 0x00
        fake_memory[base0 + MemoryReader.PARTY_HP_OFFSET + 1] = 1
        assert reader.player_whited_out() is False

    def test_empty_party(self, mock_pyboy, fake_memory):
        """No party members -> loop body never runs -> returns True."""
        reader = MemoryReader(mock_pyboy)
        fake_memory[MemoryReader.ADDR_PARTY_COUNT] = 0
        assert reader.player_whited_out() is True


# ---------------------------------------------------------------------------
# CollisionMap
# ---------------------------------------------------------------------------

class TestCollisionMap:
    def test_init_defaults(self):
        cm = CollisionMap()
        assert cm.grid == [[0] * 10 for _ in range(9)]
        assert cm.player_pos == (4, 4)
        assert cm.sprites == []

    def test_update_reads_collision_data(self, mock_pyboy):
        """update() should read game_area_collision and downsample 18x20 to 9x10."""
        cm = CollisionMap()
        raw = [[1] * 20 for _ in range(18)]
        mock_pyboy.game_wrapper.return_value.game_area_collision.return_value = raw
        cm.update(mock_pyboy)
        for row in cm.grid:
            for cell in row:
                assert cell == 1

    def test_update_walls_downsample(self, mock_pyboy):
        """A 2x2 block with any 0 should produce a 0 in the downsampled grid."""
        cm = CollisionMap()
        raw = [[1] * 20 for _ in range(18)]
        raw[0][0] = 0
        mock_pyboy.game_wrapper.return_value.game_area_collision.return_value = raw
        cm.update(mock_pyboy)
        assert cm.grid[0][0] == 0

    def test_update_all_walls(self, mock_pyboy):
        """All zeros -> all walls."""
        cm = CollisionMap()
        raw = [[0] * 20 for _ in range(18)]
        mock_pyboy.game_wrapper.return_value.game_area_collision.return_value = raw
        cm.update(mock_pyboy)
        for row in cm.grid:
            for cell in row:
                assert cell == 0

    def test_to_ascii(self):
        cm = CollisionMap()
        cm.grid = [[1] * 10 for _ in range(9)]
        cm.grid[0][0] = 0
        result = cm.to_ascii()
        assert isinstance(result, str)
        lines = result.strip().split("\n")
        assert len(lines) == 9
        assert "@" in lines[4]

    def test_to_ascii_with_sprites(self):
        cm = CollisionMap()
        cm.grid = [[1] * 10 for _ in range(9)]
        cm.sprites = [(0, 0)]
        result = cm.to_ascii()
        lines = result.strip().split("\n")
        assert "S" in lines[0]

    def test_player_pos_always_center(self):
        cm = CollisionMap()
        assert cm.player_pos == (4, 4)
