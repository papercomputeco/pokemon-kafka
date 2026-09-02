"""The crew's casting rules, in code — who takes a leg, how they are asked, what is recorded.

`.claude/skills/expedition/SKILL.md` states the doctrine; this module is the part of it a run
cannot skip by accident. Titles come from benchmarks/2026-08-22-skill-matrix.md (six models,
three skill-isolated legs) and match the router's own table
(`scripts/semantic_router.py missions`):

* **The Investigator** ``qwen38-27b-128k`` — recon; observes before anyone reasons
* **The Point Man** ``qwen38-27b-128k`` — navigation, best line of six (49 turns / 36 HP)
* **The Extractor** ``kimi-k2.6:cloud`` — puzzle, deepest of six (B2F, 18 tiles)
* **The Wheelman** ``laguna-xs-128k`` — battle, 6/6 execution baseline

Anthropic is not a seat. A leg escalates navigation → puzzle and then *stops*, leaving a written
failure for the operator; Opus is a human decision made holding that record, not a rung.

Recon comes **before** the ladder, not on it. A wall is observed before it is reasoned about:
``LegRunner.recon`` talks to the bodies on the map and the sentences land in the facts under
``HEARD``. A seat handed only failure codes is reasoning about a world nobody looked at, and four
legs were lost that way.

Everything here is pure: prompt text, response parsing, tier selection, telemetry records and the
failure document. The emulator-driving loop injects I/O around it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Seats, and the measured evidence behind each (README "The model crew").
CREW: dict[str, dict] = {
    "battle": {"title": "The Wheelman", "model": "laguna-xs-128k", "tokens": 1600, "timeout": 180},
    "navigation": {"title": "The Point Man", "model": "qwen38-27b-128k", "tokens": 1600, "timeout": 180},
    # The Extractor thinks in a different weight class, and both of its numbers are measured
    # rather than guessed. On one bounded-choice prompt it spent 6,286 reasoning tokens and
    # truncated with no answer at a 1,600 cap, then spent 11,635 and returned a correct ACTION
    # line at 6,000; seven NO-ANSWERs across two legs were that and nothing else. The wall clock
    # has to move with the budget: raising it to 8,000 tokens while leaving a 120s timeout only
    # changed how the seat failed, from "truncated" to "timed out", twice, on the very next leg.
    # Puzzle is the tier we escalate TO — starving it either way is how a ladder ends in silence.
    #
    # 2026-09-01, measured on the Silph 7F wall: the budget was never the binding constraint.
    # This gateway gives the seat **exactly 300 seconds**, and it spends all of them thinking —
    # 8,000 tokens plain, `think=false`, `json_object`, 32,000 tokens, and both streamed variants:
    # six attempts, six non-answers, 22-35 KB of reasoning apiece and not one ACTION line. A
    # non-stream call past the ceiling comes back 502. What clears it is not more budget but a
    # second call: `closing_prompt` hands the seat its own cut-off reasoning and asks only for the
    # line, and that answered in 49s. The thinking was never the problem; finishing was.
    "puzzle": {"title": "The Extractor", "model": "kimi-k2.6:cloud", "tokens": 8000, "timeout": 420},
    # The Investigator exists because of a counted failure, not a hunch. Across four legs of the
    # badge-7 water arc the crew engaged ZERO bodies on maps 7, 30, 31, 8 and 166 -- all 76
    # recorded conversations belong to the badge-6 arc -- while map 30's stuck doc listed ten live
    # bodies and used them only as obstacles. The cartridge calls all ten `trainer`. The first
    # time anyone spoke to one it answered, and the operator's single question ("are you talking
    # to NPCs?") moved the leg further than a day of engine work.
    #
    # This seat does not choose a route. It decides WHAT TO OBSERVE before anyone reasons: which
    # body to talk to, which direction to face, which screen to read. It is seated on navigation's
    # model because recon is a movement problem, and it is cheap on purpose -- it runs before the
    # expensive seats, so its budget is small and its timeout short.
    "recon": {"title": "The Investigator", "model": "qwen38-27b-128k", "tokens": 1200, "timeout": 120},
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
ANSWER_TIMEOUT = 180.0  # seconds; the per-seat value in CREW overrides this

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


def seat_for(tier: str) -> dict:
    """The crew seat for a skill tier. Unknown tiers fall back to navigation."""
    return CREW.get(tier, CREW["navigation"])


def answer_tokens(tier: str) -> int:
    """The seat's token budget — thinking models need room for the answer *after* the thinking."""
    return int(seat_for(tier).get("tokens", ANSWER_TOKENS))


def answer_timeout(tier: str) -> float:
    """How long to wait for that seat. Must scale with its budget, or the budget buys nothing."""
    return float(seat_for(tier).get("timeout", ANSWER_TIMEOUT))


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


def chat_body(model: str, prompt: str, max_tokens: int = ANSWER_TOKENS, *, stream: bool = False) -> dict[str, Any]:
    """OpenAI-shaped request body; the caller posts it at TAPES_CHAT_URL."""
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if stream:
        body["stream"] = True
    return body


def closing_prompt(prior_text: str, menu: list[str], keep: int = 4000) -> str:
    """Ask a seat that ran out of clock to convert its own thinking into the one line we need.

    Measured on the Silph 7F wall (2026-09-01): the Extractor gets exactly 300 seconds from this
    gateway — streamed or not, at 8,000 tokens or 32,000 — and spends all of it reasoning, six
    attempts out of six, ending mid-thought with no ACTION line. Its thinking is not wasted
    though: it is the most expensive thing the leg bought. Handing that tail back turns a second
    300 seconds into a conclusion instead of a fresh deliberation from zero.
    """
    return (
        "You already reasoned about this expedition wall. Your own reasoning, cut off when the "
        "clock ran out:\n\n"
        + prior_text[-keep:].strip()
        + "\n\nDo not reason further. Output exactly two lines and nothing else:\nACTION: <one of "
        + ", ".join(menu)
        + ">\nWHY: <one sentence>"
    )


def stream_deltas(lines) -> Any:
    """Yield the text deltas of an OpenAI-shaped SSE stream — ``reasoning`` counts as text.

    A thinking seat writes its answer *after* the thinking, so a stream reader that only watches
    ``content`` sees nothing for four minutes and then a truncation.
    """
    for raw in lines:
        line = raw.decode() if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = __import__("json").loads(payload)
        except ValueError:
            continue
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            for key in ("content", "reasoning"):
                piece = delta.get(key)
                if isinstance(piece, str) and piece:
                    yield piece


def decide_from_stream(lines, menu: list[str]) -> tuple[str | None, str, str]:
    """Read the stream until the seat names a menu action. Returns ``(action, why, text)``.

    The Extractor cannot answer this endpoint in one shot, and both halves of that are measured
    (2026-09-01, on the Silph 7F wall): at 8,000 tokens it returns ~30 KB of reasoning, zero
    bytes of content and ``finish_reason: length`` after ~240s — identically for plain,
    ``think=false`` and ``json_object`` requests — and at 32,000 tokens the gateway answers 502
    at a hard 300s ceiling. More budget cannot help when the wall is wall-clock.

    Streaming removes both walls at once: bytes arrive as they are produced, so no single
    response has to fit inside the ceiling, and the moment an ``ACTION:`` line parses the leg has
    its decision and stops reading. The bare-word fallback stays end-of-stream only — mid-thought
    a model names every option it is weighing.
    """
    text = ""
    for piece in stream_deltas(lines):
        text += piece
        if "\n" not in piece and len(piece) < 40:
            continue  # cheap guard: only re-parse on line boundaries, not every token
        action, why = parse_decision(text, menu, bare_word=False)
        if action is not None:
            return action, why, text
    action, why = parse_decision(text, menu)
    return action, why, text


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


def parse_decision(text: str, menu: list[str], *, bare_word: bool = True) -> tuple[str | None, str]:
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
    if action is None and bare_word:  # some answer with the bare word — but only trust the tail
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
