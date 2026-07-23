"""
Tests for scripts/ai_news_digest.py — the RSS fetch/dedup/formatting helpers
that don't touch the network. fetch_feed() itself isn't tested here (it needs
a live HTTP call); everything downstream of it — dedup, HTML stripping,
truncation — is pure logic and gets tested directly.

All OFFLINE. No network needed.

Run:
    pytest tests/ -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ai_news_digest import (
    strip_html,
    truncate,
    normalize_title,
    deduplicate_articles,
)


# ── strip_html() ──────────────────────────────────────────────────────────

def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_handles_plain_text():
    assert strip_html("Already plain text") == "Already plain text"


def test_strip_html_handles_empty_string():
    assert strip_html("") == ""


# ── truncate() ────────────────────────────────────────────────────────────

def test_truncate_leaves_short_text_untouched():
    assert truncate("A short sentence.", max_chars=200) == "A short sentence."


def test_truncate_cuts_long_text_at_word_boundary():
    text = "word " * 100  # 500 chars, well over the limit
    result = truncate(text, max_chars=50)
    assert len(result) <= 53  # 50 + "..."
    assert result.endswith("...")
    assert not result[:-3].endswith(" ")  # didn't cut mid-word into trailing space


def test_truncate_collapses_internal_whitespace():
    messy = "Too   many\n\nspaces   and\tlinebreaks"
    assert truncate(messy, max_chars=200) == "Too many spaces and linebreaks"


# ── normalize_title() ────────────────────────────────────────────────────────

def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("OpenAI Launches GPT-5!") == "openai launches gpt5"


def test_normalize_title_makes_near_duplicates_match():
    a = normalize_title("OpenAI Launches GPT-5!")
    b = normalize_title("OpenAI launches GPT-5")
    assert a == b


# ── deduplicate_articles() ───────────────────────────────────────────────────

def _article(title, source="Test Source"):
    return {"source": source, "title": title, "link": "", "summary": "", "date": ""}


def test_dedup_removes_exact_repeat_across_feeds():
    articles = [
        _article("OpenAI launches GPT-5", source="TechCrunch AI"),
        _article("OpenAI launches GPT-5", source="The Verge AI"),
    ]
    result = deduplicate_articles(articles)
    assert len(result) == 1


def test_dedup_treats_punctuation_and_case_differences_as_duplicates():
    articles = [
        _article("OpenAI Launches GPT-5!"),
        _article("openai launches gpt5"),
    ]
    result = deduplicate_articles(articles)
    assert len(result) == 1


def test_dedup_keeps_the_first_copy_seen():
    articles = [
        _article("Same story", source="First Feed"),
        _article("Same story", source="Second Feed"),
    ]
    result = deduplicate_articles(articles)
    assert result[0]["source"] == "First Feed"


def test_dedup_keeps_genuinely_different_stories():
    articles = [_article("Story A"), _article("Story B"), _article("Story C")]
    result = deduplicate_articles(articles)
    assert len(result) == 3


def test_dedup_handles_empty_list():
    assert deduplicate_articles([]) == []
