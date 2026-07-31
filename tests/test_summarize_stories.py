"""
Tests for scripts/summarize_stories.py — the Week 3 summarization step: turning
one story into a brand-voice prompt, and turning Claude's response back into a
usable {summary, why_it_matters} object.

Like the ranking tests, these are all OFFLINE. No API key, no network, no cost.
They pin the two parts most likely to break silently: the prompt actually carries
the brand voice + the story details, and the parser accepts good JSON while
clearly rejecting bad shapes.

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

import summarize_stories
from summarize_stories import (
    build_summary_prompt,
    parse_summary_response,
    summarize_rankings,
    BRAND_VOICE,
)


SAMPLE_STORY = {
    "source": "TechCrunch AI",
    "title": "OpenAI launches a new tool for building AI agents without code",
    "summary": "The no-code builder lets small teams wire up multi-step AI workflows in a browser.",
}


# ── build_summary_prompt() ───────────────────────────────────────────────────

def test_prompt_includes_story_title_source_and_snippet():
    prompt = build_summary_prompt(SAMPLE_STORY)
    assert SAMPLE_STORY["title"] in prompt
    assert SAMPLE_STORY["source"] in prompt
    assert SAMPLE_STORY["summary"] in prompt


def test_prompt_bakes_in_the_brand_voice():
    # Week 3's whole point is voice — the prompt must actually carry it.
    prompt = build_summary_prompt(SAMPLE_STORY)
    assert BRAND_VOICE in prompt
    assert "Dara Obafemi" in prompt


def test_prompt_asks_for_json_only():
    prompt = build_summary_prompt(SAMPLE_STORY)
    assert "ONLY valid JSON" in prompt


def test_prompt_asks_for_both_summary_and_why_it_matters():
    prompt = build_summary_prompt(SAMPLE_STORY)
    assert "summary" in prompt
    assert "why_it_matters" in prompt


def test_prompt_handles_story_with_no_summary_key():
    # A hand-built story dict might omit "summary"; .get() should protect this.
    story = {"source": "Test Source", "title": "A title with no summary key"}
    prompt = build_summary_prompt(story)
    assert "A title with no summary key" in prompt


# ── parse_summary_response() ─────────────────────────────────────────────────

VALID_SUMMARY = {
    "summary": "A plain two-sentence summary of what happened.",
    "why_it_matters": "The practical takeaway for the audience.",
}


def test_parses_clean_unfenced_json():
    blurb = parse_summary_response(json.dumps(VALID_SUMMARY))
    assert blurb["summary"] == VALID_SUMMARY["summary"]
    assert blurb["why_it_matters"] == VALID_SUMMARY["why_it_matters"]


def test_strips_json_code_fence():
    fenced = "```json\n" + json.dumps(VALID_SUMMARY) + "\n```"
    blurb = parse_summary_response(fenced)
    assert blurb["summary"] == VALID_SUMMARY["summary"]


def test_strips_plain_code_fence_no_language_tag():
    fenced = "```\n" + json.dumps(VALID_SUMMARY) + "\n```"
    blurb = parse_summary_response(fenced)
    assert blurb["why_it_matters"] == VALID_SUMMARY["why_it_matters"]


def test_returns_only_the_two_expected_fields():
    # A chatty model that adds extra keys shouldn't leak them downstream.
    noisy = dict(VALID_SUMMARY, extra="should be dropped", note="also dropped")
    blurb = parse_summary_response(json.dumps(noisy))
    assert set(blurb.keys()) == {"summary", "why_it_matters"}


def test_rejects_non_json_text():
    with pytest.raises(ValueError):
        parse_summary_response("Sure! Here's your summary: it's a great story.")


def test_rejects_json_that_isnt_an_object():
    # If Claude returns a JSON list instead of an object, fail clearly rather
    # than crashing later on data.keys().
    with pytest.raises(ValueError, match="wasn't an object"):
        parse_summary_response(json.dumps(["summary", "why_it_matters"]))


def test_rejects_missing_summary_field():
    with pytest.raises(ValueError, match="summary"):
        parse_summary_response(json.dumps({"why_it_matters": "only half of it"}))


def test_rejects_missing_why_it_matters_field():
    with pytest.raises(ValueError, match="why_it_matters"):
        parse_summary_response(json.dumps({"summary": "only half of it"}))


def test_error_message_includes_raw_response_for_debugging():
    with pytest.raises(ValueError, match="not json at all"):
        parse_summary_response("not json at all")


# ── value validation: a present key isn't enough, it must be usable ──────────

def test_rejects_empty_summary_string():
    # "summary": "" passes the key-exists check but would land as a blank blurb
    # in the newsletter — reject it here instead.
    with pytest.raises(ValueError, match="summary"):
        parse_summary_response(json.dumps({"summary": "", "why_it_matters": "real"}))


def test_rejects_whitespace_only_why_it_matters():
    with pytest.raises(ValueError, match="why_it_matters"):
        parse_summary_response(json.dumps({"summary": "real", "why_it_matters": "   "}))


def test_rejects_null_field_value():
    # A JSON null becomes Python None — a present key with an unusable value.
    with pytest.raises(ValueError, match="summary"):
        parse_summary_response(json.dumps({"summary": None, "why_it_matters": "real"}))


def test_rejects_non_string_field_value():
    # A model returning a list/number for a field shouldn't slip through.
    with pytest.raises(ValueError, match="why_it_matters"):
        parse_summary_response(json.dumps({"summary": "real", "why_it_matters": ["a", "b"]}))


def test_strips_surrounding_whitespace_from_values():
    padded = {"summary": "  clean summary  ", "why_it_matters": "\nclean takeaway\n"}
    blurb = parse_summary_response(json.dumps(padded))
    assert blurb["summary"] == "clean summary"
    assert blurb["why_it_matters"] == "clean takeaway"


# ── summarize_rankings(): one bad story must not kill the whole batch ─────────
# These monkeypatch summarize_story so no API call or network is ever made —
# we're testing the batch-resilience layer, not the single-story call.

GOOD_BLURB = {"summary": "s", "why_it_matters": "w"}


def test_summarize_rankings_attaches_a_blurb_to_every_story(monkeypatch):
    monkeypatch.setattr(summarize_stories, "summarize_story", lambda story: GOOD_BLURB)
    rankings = [{"title": "A"}, {"title": "B"}]
    out = summarize_rankings(rankings)
    assert all(r["blurb"] == GOOD_BLURB for r in out)
    assert all(r["blurb_error"] is None for r in out)


def test_summarize_rankings_survives_one_failed_story(monkeypatch):
    # The whole point of tonight's change: a single malformed blurb should NOT
    # throw away the other stories' good summaries or crash the send-ready run.
    def flaky(story):
        if story["title"] == "bad":
            raise ValueError("Claude returned garbage for this one")
        return GOOD_BLURB

    monkeypatch.setattr(summarize_stories, "summarize_story", flaky)
    rankings = [{"title": "good1"}, {"title": "bad"}, {"title": "good2"}]
    out = summarize_rankings(rankings)

    # The two good stories still get real blurbs.
    assert out[0]["blurb"] == GOOD_BLURB
    assert out[2]["blurb"] == GOOD_BLURB
    # The bad one is flagged (not silently dropped, not a crash).
    assert out[1]["blurb"] is None
    assert "garbage" in out[1]["blurb_error"]


def test_summarize_rankings_does_not_raise_when_every_story_fails(monkeypatch):
    # Even a total wipe-out degrades to flagged gaps rather than an exception,
    # so main() can still print a draft that shows exactly what needs a manual blurb.
    def always_fails(story):
        raise ValueError("boom")

    monkeypatch.setattr(summarize_stories, "summarize_story", always_fails)
    rankings = [{"title": "A"}, {"title": "B"}]
    out = summarize_rankings(rankings)  # must not raise
    assert all(r["blurb"] is None for r in out)
    assert all(r["blurb_error"] == "boom" for r in out)
