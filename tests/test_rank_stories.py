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

from rank_stories import build_ranking_prompt, parse_ranking_response, TOP_N


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
