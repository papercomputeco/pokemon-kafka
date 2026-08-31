"""The casting rules are doctrine, so they are tested like doctrine."""

from datetime import datetime, timezone

import expedition_crew as crew

MENU = ["RETRY_SAME", "TRY_FAR_EDGE_CELL", "USE_GATE_WARP", "BACK_OUT_AND_REENTER", "GIVE_UP"]


def test_seats_match_the_benchmarked_crew():
    assert crew.seat_for("navigation")["model"] == "qwen38-27b-128k"
    assert crew.seat_for("puzzle")["model"] == "kimi-k2.6:cloud"
    assert crew.seat_for("battle")["model"] == "laguna-xs-128k"
    assert crew.seat_for("navigation")["title"] == "The Point Man"


def test_unknown_tier_falls_back_to_navigation():
    assert crew.seat_for("interpretive-dance") == crew.CREW["navigation"]


def test_no_anthropic_model_is_ever_a_seat():
    for seat in crew.CREW.values():
        assert "claude" not in seat["model"].lower()
        assert "opus" not in seat["model"].lower()


def test_tier_escalates_from_navigation_to_puzzle():
    assert crew.tier_for_attempt(1) == "navigation"
    assert crew.tier_for_attempt(2) == "navigation"
    assert crew.tier_for_attempt(3) == "puzzle"
    assert crew.tier_for_attempt(2, nav_attempts=1) == "puzzle"


def test_prompt_carries_the_ground_truth_warning_and_the_menu():
    prompt = crew.build_prompt("map 25 is 20x54", MENU)
    assert "recalled details are frequently wrong" in prompt
    assert "map 25 is 20x54" in prompt
    assert "USE_GATE_WARP" in prompt
    assert prompt.rstrip().endswith("WHY: <one sentence>")


def test_chat_body_is_openai_shaped():
    body = crew.chat_body("qwen38-27b-128k", "hello", max_tokens=12)
    assert body["model"] == "qwen38-27b-128k"
    assert body["max_tokens"] == 12
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_capture_proxy_is_the_tapes_port_not_ollama():
    assert "42345" in crew.TAPES_CHAT_URL
    assert "11434" not in crew.TAPES_CHAT_URL


def test_extract_text_prefers_content():
    payload = {"choices": [{"message": {"content": "ACTION: RETRY_SAME", "reasoning": "noise"}}]}
    assert crew.extract_text(payload) == "ACTION: RETRY_SAME"


def test_extract_text_falls_back_to_reasoning_when_content_is_empty():
    # the exact shape kimi/qwen thinking models return through the ollama OpenAI shim
    payload = {"choices": [{"message": {"content": "", "reasoning": "ACTION: USE_GATE_WARP"}}]}
    assert crew.extract_text(payload) == "ACTION: USE_GATE_WARP"


def test_extract_text_handles_empty_and_malformed_payloads():
    assert crew.extract_text({}) == ""
    assert crew.extract_text({"choices": []}) == ""
    assert crew.extract_text({"choices": [{}]}) == ""
    assert crew.extract_text({"choices": [{"message": {"content": "   ", "reasoning": None}}]}) == ""


def test_parse_decision_reads_action_and_why():
    action, why = crew.parse_decision("ACTION: USE_GATE_WARP\nWHY: the warp is in region.", MENU)
    assert action == "USE_GATE_WARP"
    assert why == "the warp is in region."


def test_parse_decision_tolerates_markdown_and_case():
    action, why = crew.parse_decision("**action: try_far_edge_cell**\n*WHY:* far cells work", MENU)
    assert action == "TRY_FAR_EDGE_CELL"
    assert why == "far cells work"


def test_parse_decision_accepts_a_bare_action_word():
    action, why = crew.parse_decision("I would BACK_OUT_AND_REENTER here.", MENU)
    assert action == "BACK_OUT_AND_REENTER"
    assert why == ""


def test_parse_decision_reports_a_non_answer_instead_of_defaulting():
    action, why = crew.parse_decision("I am not sure what to do.", MENU)
    assert action is None
    assert why == ""


def test_parse_decision_ignores_actions_outside_the_menu():
    action, _why = crew.parse_decision("ACTION: LAUNCH_ROCKET", ["RETRY_SAME"])
    assert action is None


def test_telemetry_record_shape():
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    rec = crew.telemetry_record("sup-1", "expedition.hop", {"ok": True}, now=now)
    assert rec["run_id"] == "sup-1"
    assert rec["event"] == "expedition.hop"
    assert rec["source"] == "expedition"
    assert rec["ok"] is True
    assert rec["ts"].startswith("2026-08-30T12:00")


def test_telemetry_record_defaults_to_now_and_no_fields():
    rec = crew.telemetry_record("sup-2", "expedition.start")
    assert rec["event"] == "expedition.start"
    assert "ts" in rec


def test_failure_doc_records_the_ladder_and_refuses_anthropic():
    doc = crew.failure_doc(
        "sup-3",
        "map 10",
        "map 29 via edge west",
        "region: 4 cells",
        ["navigation/RETRY_SAME: nothing", "puzzle/GIVE_UP: stuck"],
    )
    assert "Expedition stuck: map 29 via edge west" in doc
    assert "The Point Man" in doc and "The Extractor" in doc
    assert "Anthropic was NOT called" in doc
    assert "- puzzle/GIVE_UP: stuck" in doc
    assert "region: 4 cells" in doc


# --------------------------------------------------------------------- thinking-model replies


def test_the_token_budget_leaves_room_for_an_answer_after_the_thinking():
    """Measured on the badge-6 leg: a 240-token cap bought four truncated chains of thought and
    not one ACTION line — the seats looked exhausted when they were never given room to answer."""
    assert crew.chat_body("qwen38-27b-128k", "prompt")["max_tokens"] >= 1000


def test_a_bare_word_is_trusted_only_in_the_conclusion():
    reply = "ACTION lines aside, let me think.\nRETRY_SAME is what I would normally do.\n" + (
        "\n".join(["filler"] * 10) + "\nGIVE_UP"
    )
    action, _ = crew.parse_decision(reply, MENU)
    assert action == "GIVE_UP"  # the tail decides, not the first option named mid-thought


def test_deliberation_that_names_two_options_is_not_a_choice():
    """The exact shape a thinking model truncates into: both options weighed, neither chosen."""
    reply = "The hop returned no-path.\nRETRY_SAME doesn't make sense here.\nGIVE_UP seems better, but"
    assert crew.parse_decision(reply, MENU)[0] is None


def test_an_explicit_action_line_still_wins_over_the_tail():
    reply = "ACTION: USE_GATE_WARP\nWHY: the gate severs the route\nRETRY_SAME was the alternative"
    assert crew.parse_decision(reply, MENU) == ("USE_GATE_WARP", "the gate severs the route")


def test_the_puzzle_seat_gets_the_budget_its_thinking_actually_costs():
    """Measured on one bounded-choice prompt: 6,286 reasoning tokens and NO answer at a 1,600
    cap; 11,635 and a correct ACTION line at 6,000. Puzzle is the tier we escalate TO."""
    assert crew.answer_tokens("puzzle") >= 6000
    assert crew.answer_tokens("puzzle") > crew.answer_tokens("navigation")
    assert crew.chat_body("m", "p", crew.answer_tokens("puzzle"))["max_tokens"] == crew.answer_tokens("puzzle")


def test_an_unknown_tier_still_gets_a_usable_budget():
    assert crew.answer_tokens("interpretive-dance") == crew.answer_tokens("navigation")


def test_the_wait_scales_with_the_seats_budget():
    """Raising the Extractor's tokens without its timeout only changed how it failed."""
    assert crew.answer_timeout("puzzle") > crew.answer_timeout("navigation")
    assert crew.answer_timeout("interpretive-dance") == crew.answer_timeout("navigation")
