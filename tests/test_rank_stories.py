"""
Tests for scripts/rank_stories.py — the two hardest-to-get-wrong parts of
the ranking step: turning stories into a prompt, and turning Claude's
response back into usable data.

These are all OFFLINE. No API key, no network, no cost. They test the same
edge cases the 2026-07-23 session verified by hand in the terminal — now
they're saved as real, runnable checks so a future change can't silently
break them without a test failing.

Run:
    pip install -r requirements-dev.txt
    pytest tests/ -v
"""

import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable without installing the project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rank_stories import (
    build_ranking_prompt,
    parse_ranking_response,
    finalize_rankings,
    attach_stories,
    TOP_N,
)


SAMPLE_STORIES = [
    {"source": "TechCrunch AI", "title": "OpenAI launches a new tool for building AI agents without code",
     "summary": "The no-code builder lets small teams wire up multi-step AI workflows in a browser."},
    {"source": "MIT Tech Review AI", "title": "Chipmaker reports record quarterly earnings on AI datacenter demand",
     "summary": "Wall Street analysts raised price targets after the earnings call."},
]


# ── build_ranking_prompt() ───────────────────────────────────────────────────

def test_prompt_includes_every_story_title():
    prompt = build_ranking_prompt(SAMPLE_STORIES)
    for story in SAMPLE_STORIES:
        assert story["title"] in prompt


def test_prompt_asks_for_json_only():
    prompt = build_ranking_prompt(SAMPLE_STORIES)
    assert "ONLY valid JSON" in prompt


def test_prompt_mentions_correct_story_count():
    prompt = build_ranking_prompt(SAMPLE_STORIES)
    assert f"Here are {len(SAMPLE_STORIES)} stories" in prompt


def test_prompt_handles_empty_story_list():
    # Shouldn't crash even if fetching returned nothing.
    prompt = build_ranking_prompt([])
    assert "Here are 0 stories" in prompt


def test_prompt_handles_story_with_no_summary():
    # generate_content_ideas() etc. always set "summary", but a hand-built
    # story dict (like in a quick test) might not — .get() should protect this.
    story = [{"source": "Test Source", "title": "A title with no summary key"}]
    prompt = build_ranking_prompt(story)
    assert "A title with no summary key" in prompt


# ── parse_ranking_response() ─────────────────────────────────────────────────

VALID_RANKING = {
    "rankings": [
        {"story_number": 1, "title": "Story one", "relevance_score": 9, "reason": "Buildable."},
        {"story_number": 2, "title": "Story two", "relevance_score": 5, "reason": "Less relevant."},
    ]
}


def test_parses_clean_unfenced_json():
    rankings = parse_ranking_response(json.dumps(VALID_RANKING))
    assert len(rankings) == 2
    assert rankings[0]["relevance_score"] == 9


def test_strips_json_code_fence():
    fenced = "```json\n" + json.dumps(VALID_RANKING) + "\n```"
    rankings = parse_ranking_response(fenced)
    assert len(rankings) == 2


def test_strips_plain_code_fence_no_language_tag():
    fenced = "```\n" + json.dumps(VALID_RANKING) + "\n```"
    rankings = parse_ranking_response(fenced)
    assert len(rankings) == 2


def test_rejects_non_json_text():
    with pytest.raises(ValueError):
        parse_ranking_response("Sure! Here are my top picks: story one is great.")


def test_rejects_json_missing_rankings_key():
    with pytest.raises(ValueError):
        parse_ranking_response(json.dumps({"top_stories": []}))


def test_rejects_ranking_entry_missing_a_required_field():
    broken = {"rankings": [{"story_number": 1, "title": "Story one", "relevance_score": 9}]}  # no "reason"
    with pytest.raises(ValueError):
        parse_ranking_response(json.dumps(broken))


def test_rejects_ranking_entry_that_isnt_a_json_object():
    # If Claude ever returns "rankings": ["some string", ...] instead of a
    # list of objects, entry.keys() would previously crash with a raw
    # AttributeError instead of the clear ValueError every other malformed
    # case in this file raises. This proves the same clear error applies here.
    broken = {"rankings": ["not an object"]}
    with pytest.raises(ValueError, match="wasn't a JSON object"):
        parse_ranking_response(json.dumps(broken))


def test_error_message_includes_raw_response_for_debugging():
    # A bad response should be easy to diagnose from the error alone.
    bad = "not json at all"
    with pytest.raises(ValueError, match="not json at all"):
        parse_ranking_response(bad)


def test_top_n_constant_is_a_positive_int():
    # Cheap guard: if TOP_N is ever accidentally set to 0, a string, etc.,
    # the prompt would silently ask Claude for a nonsensical number of results.
    assert isinstance(TOP_N, int)
    assert TOP_N > 0


# ── finalize_rankings() ──────────────────────────────────────────────────────
# These enforce the top-N-sorted contract in code, instead of trusting Claude
# to obey "return exactly TOP_N entries, sorted highest score first."

def _entry(score, title="x"):
    return {"story_number": 1, "title": title, "relevance_score": score, "reason": "r"}


def test_finalize_sorts_by_score_highest_first():
    # Deliberately out of order — Claude might return them this way.
    out = finalize_rankings([_entry(3), _entry(9), _entry(6)])
    assert [e["relevance_score"] for e in out] == [9, 6, 3]


def test_finalize_caps_to_top_n():
    # More entries than TOP_N (Claude returned too many) → keep only the best.
    too_many = [_entry(i) for i in range(1, TOP_N + 4)]  # TOP_N + 3 entries
    out = finalize_rankings(too_many)
    assert len(out) == TOP_N
    # The ones kept must be the highest scores.
    assert min(e["relevance_score"] for e in out) == (TOP_N + 3) - TOP_N + 1


def test_finalize_coerces_string_and_float_scores():
    # "8" (string) and 7.0 (float) should normalize to ints and sort correctly.
    out = finalize_rankings([_entry("8"), _entry(7.0), _entry(9)])
    assert [e["relevance_score"] for e in out] == [9, 8, 7]
    assert all(isinstance(e["relevance_score"], int) for e in out)


def test_finalize_raises_on_non_numeric_score():
    # The error must name the score field, not the story_number field — both
    # coercions now share one _coerce_int(value, field) helper, so this pins
    # down that the score call site passes the right field name through.
    with pytest.raises(ValueError, match="relevance_score isn't a number"):
        finalize_rankings([_entry("high")])


def test_finalize_coerces_string_and_float_story_numbers():
    # Claude sometimes echoes the story number back as "1" (string) or 1.0
    # (float). Both must normalize to an int, because rank_stories() and
    # run_dry_run() do `story_number - 1` to look the story back up — and
    # "1" - 1 is a raw TypeError, not a clear error.
    a = {"story_number": "1", "title": "x", "relevance_score": 9, "reason": "r"}
    b = {"story_number": 2.0, "title": "y", "relevance_score": 5, "reason": "r"}
    out = finalize_rankings([a, b])
    assert all(isinstance(e["story_number"], int) for e in out)
    assert [e["story_number"] for e in out] == [1, 2]


def test_finalize_raises_on_non_numeric_story_number():
    bad = {"story_number": "first", "title": "x", "relevance_score": 9, "reason": "r"}
    with pytest.raises(ValueError, match="story_number isn't a number"):
        finalize_rankings([bad])


# ── attach_stories() ─────────────────────────────────────────────────────────
# rank_stories() and run_dry_run() used to have this same lookup loop copied
# verbatim; it now lives in one helper so the two can't drift apart. These
# pin down the two behaviors that matter: it attaches the right story, and it
# skips (doesn't crash on) a story_number that's out of range.

def test_attach_stories_maps_number_to_the_right_story():
    # story_number is 1-based (matches how the prompt numbers them), so
    # story_number 2 must attach the SECOND story in the list.
    rankings = [
        {"story_number": 1, "title": "x", "relevance_score": 9, "reason": "r"},
        {"story_number": 2, "title": "y", "relevance_score": 5, "reason": "r"},
    ]
    attach_stories(rankings, SAMPLE_STORIES)
    assert rankings[0]["story"] is SAMPLE_STORIES[0]
    assert rankings[1]["story"] is SAMPLE_STORIES[1]


def test_attach_stories_skips_out_of_range_number_without_crashing():
    # If Claude references a story_number that isn't in the fetched list
    # (here 99, with only 2 stories), that entry is left without a "story"
    # key rather than crashing — matching the original inline behavior.
    rankings = [{"story_number": 99, "title": "x", "relevance_score": 9, "reason": "r"}]
    attach_stories(rankings, SAMPLE_STORIES)
    assert "story" not in rankings[0]
