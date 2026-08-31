"""The crew's casting rules, in code — who takes a leg, how they are asked, what is recorded.

`.claude/skills/expedition/SKILL.md` states the doctrine; this module is the part of it a run
cannot skip by accident. Titles come from benchmarks/2026-08-22-skill-matrix.md (six models,
three skill-isolated legs) and match the router's own table
(`scripts/semantic_router.py missions`):

* **The Point Man** ``qwen38-27b-128k`` — navigation, best line of six (49 turns / 36 HP)
* **The Extractor** ``kimi-k2.6:cloud`` — puzzle, deepest of six (B2F, 18 tiles)
* **The Wheelman** ``laguna-xs-128k`` — battle, 6/6 execution baseline

Anthropic is not a seat. A leg escalates navigation → puzzle and then *stops*, leaving a written
failure for the operator; Opus is a human decision made holding that record, not a rung.

Everything here is pure: prompt text, response parsing, tier selection, telemetry records and the
failure document. The emulator-driving loop injects I/O around it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Seats, and the measured evidence behind each (README "The model crew").
CREW: dict[str, dict[str, str]] = {
    "battle": {"title": "The Wheelman", "model": "laguna-xs-128k"},
    "navigation": {"title": "The Point Man", "model": "qwen38-27b-128k"},
    "puzzle": {"title": "The Extractor", "model": "kimi-k2.6:cloud"},
}

# The tapes capture proxy (~/.tapes/config.toml: provider openai, upstream 11434, listen 42345).
# Calling ollama on :11434 directly produces an uncaptured session, which the doctrine forbids.
TAPES_CHAT_URL = "http://localhost:42345/v1/chat/completions"

# How many navigation-tier attempts a hop gets before the job is treated as a puzzle.
NAV_ATTEMPTS = 2

# Two of the three seats are thinking models: they spend the token budget on ``reasoning`` and
# only then write ``content``. Measured on the badge-6 leg, a 240-token cap bought four
# consultations that were pure truncated chain-of-thought and not one ACTION line — the seats
# looked exhausted when they had simply never been given room to answer.
ANSWER_TOKENS = 1600

# A bare menu word is only trusted this near the end of a reply. Mid-thought a model names every
# option it is weighing ("RETRY_SAME ... doesn't make sense"), so scraping the whole text hands
# back the action it was arguing *against* — a hollow decision wearing a real one's clothes.
CONCLUSION_LINES = 6

GROUND_TRUTH_PREAMBLE = (
    "Every fact below was MEASURED from the running game or extracted from this cartridge. "
    "Pokemon Red exists in several versions and recalled details are frequently wrong for this "
    "ROM, so trust these facts over anything you remember about the game. Do not introduce map "
    "layouts, item locations, species or type facts that are not stated here."
)


def seat_for(tier: str) -> dict[str, str]:
    """The crew seat for a skill tier. Unknown tiers fall back to navigation."""
    return CREW.get(tier, CREW["navigation"])


def tier_for_attempt(attempt: int, nav_attempts: int = NAV_ATTEMPTS) -> str:
    """Attempts 1..nav_attempts are navigation-class; past that the wall is a puzzle."""
    return "navigation" if attempt <= nav_attempts else "puzzle"


def build_prompt(facts: str, menu: list[str]) -> str:
    """The bounded-choice prompt: measured facts in, one menu action out."""
    return (
        "You are seated on a Pokemon Red expedition. "
        + GROUND_TRUTH_PREAMBLE
        + "\n\n"
        + facts.strip()
        + "\n\nChoose exactly ONE next action from this menu: "
        + ", ".join(menu)
        + ".\nReply in two lines:\nACTION: <name>\nWHY: <one sentence>"
    )


def chat_body(model: str, prompt: str, max_tokens: int = ANSWER_TOKENS) -> dict[str, Any]:
    """OpenAI-shaped request body; the caller posts it at TAPES_CHAT_URL."""
    return {
        "model": model,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }


def extract_text(payload: dict[str, Any]) -> str:
    """Pull the answer out of an OpenAI-shaped reply.

    Ollama's thinking models return an empty ``content`` with the answer in ``reasoning``;
    reading only ``content`` silently yields "" and sends the caller to its menu default,
    which is how a supervisor logs five hollow decisions in a row.
    """
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    for key in ("content", "reasoning"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def parse_decision(text: str, menu: list[str]) -> tuple[str | None, str]:
    """Read ``ACTION:``/``WHY:`` out of a reply.

    Returns ``(None, why)`` when no menu action was named — an unparsed answer is a
    non-answer, and the caller must treat it as such rather than quietly acting on
    whatever happens to sit first in the menu.
    """
    action: str | None = None
    why = ""
    upper_menu = {m.upper(): m for m in menu}
    for line in text.splitlines():
        stripped = line.strip().lstrip("*# ").strip()
        if stripped.upper().startswith("ACTION:"):
            candidate = stripped.split(":", 1)[1].strip().upper().strip(".`*")
            if candidate in upper_menu:
                action = upper_menu[candidate]
        elif stripped.upper().startswith("WHY:"):
            why = stripped.split(":", 1)[1].strip().lstrip("*`_ ").strip()
    if action is None:  # some models answer with the bare action word — but only trust the tail
        tail = "\n".join(text.strip().splitlines()[-CONCLUSION_LINES:]).upper()
        named = [name for name in menu if name.upper() in tail]
        if len(named) == 1:  # two options named in the conclusion is a deliberation, not a choice
            action = named[0]
    return action, why


def telemetry_record(
    run_id: str, event: str, fields: dict[str, Any] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """One line for data/telemetry/game/<date>.jsonl — the sink the benchmarks mine."""
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    record = {"ts": stamp, "run_id": run_id, "event": event, "source": "expedition"}
    record.update(fields or {})
    return record


def failure_doc(run_id: str, goal: str, where: str, facts: str, tried: list[str]) -> str:
    """The written exhaustion record. Anthropic is not called; the operator decides."""
    lines = [
        f"# Expedition stuck: {where}",
        "",
        f"run_id: {run_id}  •  goal: {goal}",
        "",
        "The ladder was exhausted: "
        f"{CREW['navigation']['title']} ({CREW['navigation']['model']}) then "
        f"{CREW['puzzle']['title']} ({CREW['puzzle']['model']}). "
        "Anthropic was NOT called — deciding whether Opus is worth it is the operator's call, "
        "made holding this record.",
        "",
        "## Measured facts at the point of failure",
        "",
        "```",
        facts.strip(),
        "```",
        "",
        "## Actions tried",
        "",
    ]
    lines.extend(f"- {item}" for item in tried)
    lines.append("")
    return "\n".join(lines)
