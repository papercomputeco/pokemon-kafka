#!/usr/bin/env python3
"""Diagnostic: check if button inputs actually move the player."""

import sys

try:
    from pyboy import PyBoy
except ImportError:
    print("PyBoy not installed")
    sys.exit(1)

rom_path = sys.argv[1]
pyboy = PyBoy(rom_path, window="null")

# Skip intro: mash A for a while
for _ in range(1500):
    pyboy.tick()
pyboy.button("start")
for _ in range(60):
    pyboy.tick()
for i in range(600):
    pyboy.button("a")
    for _ in range(30):
        pyboy.tick()
    pyboy.button_release("a")
    for _ in range(10):
        pyboy.tick()


# Now read position
def pos():
    x = pyboy.memory[0xD362]
    y = pyboy.memory[0xD361]
    map_id = pyboy.memory[0xD35E]
    party = pyboy.memory[0xD163]
    # Check several text/menu indicators
    joypad_disabled = pyboy.memory[0xD730]
    text_progress = pyboy.memory[0xC4F2]
    warp_flag = pyboy.memory[0xD736]
    return (
        f"Map:{map_id} Pos:({x},{y}) Party:{party} JoyDisabled:0x{joypad_disabled:02X}"
        f" TextProg:0x{text_progress:02X} Warp:0x{warp_flag:02X}"
    )


print(f"After intro: {pos()}")

# Try pressing down with lots of frames
for attempt in range(10):
    print(f"\nAttempt {attempt}: pressing DOWN...")
    pyboy.button("down")
    for _ in range(20):
        pyboy.tick()
    pyboy.button_release("down")
    for _ in range(20):
        pyboy.tick()
    print(f"  After DOWN: {pos()}")

    print("  pressing A...")
    pyboy.button("a")
    for _ in range(20):
        pyboy.tick()
    pyboy.button_release("a")
    for _ in range(30):
        pyboy.tick()
    print(f"  After A: {pos()}")

pyboy.stop()
