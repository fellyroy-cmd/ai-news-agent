"""
Tests for scripts/build_newsletter.py — the Week 4 assembly step: turning
ranked + voice-summarized stories into a send-ready newsletter draft.

Like every other test in this project these are OFFLINE. No API key, no network,
and (except for the one save test, which uses pytest's tmp_path) no disk writes.
They pin the parts most likely to break silently:
  - each story block carries its title, both halves of the blurb, and its link
  - a failed blurb (blurb is None) renders as a VISIBLE manual-gap TODO — never
    silently dropped, never a crash (the batch-resilience contract from Week 3)
  - the full draft carries the story section plus the human-touch TODO sections
  - save writes to the dated path and the file round-trips

Run:
    pip install -r requirements-dev.txt
    pytest tests/ -v
"""

import datetime
import sys
from pathlib import Path

# Make scripts/ importable without installing the project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_newsletter import (
    render_story_block,
    render_this_week_in_ai,
    render_newsletter,
    count_manual_gaps,
    count_todos,
    describe_blanks,
    save_newsletter,
    next_issue_number,
)


GOOD_ENTRY = {
    "title": "OpenAI launches a no-code agent builder",
    "relevance_score": 9,
    "story": {"link": "https://example.com/openai-agents"},
    "blurb": {
        "summary": "OpenAI shipped a no-code way to build agents in the browser.",
        "why_it_matters": "Non-coders can prototype an agent this week.",
    },
    "blurb_error": None,
}

FAILED_ENTRY = {
    "title": "Open-source model tops the coding benchmarks",
    "relevance_score": 8,
    "story": {"link": "https://example.com/oss-model"},
    "blurb": None,
    "blurb_error": "Claude's summary response wasn't valid JSON",
}


# ── render_story_block() ─────────────────────────────────────────────────────

def test_story_block_includes_title_number_and_link():
    block = render_story_block(GOOD_ENTRY, 1)
    assert "**1. OpenAI launches a no-code agent builder**" in block
    assert "→ Read more: https://example.com/openai-agents" in block


def test_story_block_includes_both_halves_of_the_blurb():
    # Both what-happened and why-it-matters must land in the block; dropping
    # why_it_matters would quietly gut the value of the Week 3 work.
    block = render_story_block(GOOD_ENTRY, 1)
    assert GOOD_ENTRY["blurb"]["summary"] in block
    assert GOOD_ENTRY["blurb"]["why_it_matters"] in block


def test_failed_blurb_renders_a_visible_manual_gap_not_a_crash():
    # The batch-resilience contract: a None blurb becomes a flagged TODO that
    # names the reason, and the story keeps its slot (title + link still there).
    block = render_story_block(FAILED_ENTRY, 3)
    assert "**3. Open-source model tops the coding benchmarks**" in block
    assert "TODO" in block
    assert "valid JSON" in block  # the blurb_error reason is surfaced
    assert "→ Read more: https://example.com/oss-model" in block


def test_story_block_flags_a_missing_link():
    entry = dict(GOOD_ENTRY, story={})  # no link attached
    block = render_story_block(entry, 1)
    assert "TODO" in block
    assert "source link" in block


def test_story_block_survives_entry_with_no_attached_story():
    # A hand-built entry might have no "story" key at all — must not KeyError.
    entry = {k: v for k, v in GOOD_ENTRY.items() if k != "story"}
    block = render_story_block(entry, 1)
    assert "OpenAI launches a no-code agent builder" in block
    assert "TODO" in block  # link is missing, so it's flagged


# ── render_this_week_in_ai() ─────────────────────────────────────────────────

def test_section_numbers_stories_in_order():
    section = render_this_week_in_ai([GOOD_ENTRY, FAILED_ENTRY])
    assert "**1. OpenAI launches a no-code agent builder**" in section
    assert "**2. Open-source model tops the coding benchmarks**" in section


def test_section_keeps_failed_stories_rather_than_dropping_them():
    # Two stories in → two blocks out, even though one blurb failed.
    section = render_this_week_in_ai([GOOD_ENTRY, FAILED_ENTRY])
    assert section.count("**") >= 4  # two bold headers, two ** each


def test_empty_rankings_render_a_visible_placeholder_not_a_blank():
    section = render_this_week_in_ai([])
    assert "TODO" in section
    assert section.strip() != ""


# ── render_newsletter() ──────────────────────────────────────────────────────

def test_full_draft_contains_the_story_section_content():
    draft = render_newsletter([GOOD_ENTRY], issue_number=7)
    assert GOOD_ENTRY["blurb"]["summary"] in draft
    assert "## THIS WEEK IN AI" in draft


def test_full_draft_uses_the_given_issue_number_and_date():
    draft = render_newsletter([GOOD_ENTRY], issue_number=7, date=datetime.date(2026, 8, 4))
    assert "**Issue #:** 7" in draft
    assert "August 04, 2026" in draft


def test_full_draft_defaults_issue_number_to_placeholder():
    draft = render_newsletter([GOOD_ENTRY])
    assert "**Issue #:** [#]" in draft


def test_full_draft_keeps_human_touch_sections_as_todos():
    # We deliberately don't auto-invent subject lines, the tool of the week, or
    # the video link — those stay as guided TODOs for Dara's ≤10-min edit.
    draft = render_newsletter([GOOD_ENTRY])
    for heading in (
        "## AI TOOL OF THE WEEK",
        "## THIS WEEK'S VIDEO",
        "## FROM THE COMMUNITY (Skool)",
        "## CLOSING",
    ):
        assert heading in draft
    assert "subject line" in draft
    assert "tool name" in draft
    assert "YouTube link" in draft


# ── count_manual_gaps() ──────────────────────────────────────────────────────

def test_counts_only_the_stories_with_a_failed_blurb():
    assert count_manual_gaps([GOOD_ENTRY, FAILED_ENTRY, GOOD_ENTRY]) == 1
    assert count_manual_gaps([GOOD_ENTRY, GOOD_ENTRY]) == 0
    assert count_manual_gaps([FAILED_ENTRY, FAILED_ENTRY]) == 2


# ── count_todos() ────────────────────────────────────────────────────────────

def test_count_todos_counts_the_blanks_in_a_real_draft():
    # A clean draft (every story blurb filled) still has the fixed human-touch
    # blanks: 3 subject lines + preview + header opener + 6 tool-of-the-week
    # fields (name, description, what/best-for/free/link) + 3 video fields
    # (title, teaser, link) + 2 Skool fields + the closing question = 17.
    draft = render_newsletter([GOOD_ENTRY], issue_number=1)
    assert count_todos(draft) == 17


def test_count_todos_includes_a_failed_blurb_gap():
    # The failed-blurb story renders its own [TODO: write this blurb...], so a
    # draft with one gap has exactly one more blank than the all-filled draft.
    clean = count_todos(render_newsletter([GOOD_ENTRY], issue_number=1))
    with_gap = count_todos(render_newsletter([GOOD_ENTRY, FAILED_ENTRY], issue_number=1))
    assert with_gap == clean + 1


def test_count_todos_total_is_never_less_than_the_manual_gap_count():
    # The invariant the run summary relies on: the blank total always INCLUDES
    # the story-blurb gaps, so it can never contradict count_manual_gaps().
    rankings = [GOOD_ENTRY, FAILED_ENTRY, FAILED_ENTRY]
    draft = render_newsletter(rankings, issue_number=1)
    assert count_todos(draft) >= count_manual_gaps(rankings)


def test_count_todos_is_zero_for_text_with_no_placeholders():
    assert count_todos("nothing to fill in here") == 0


# ── describe_blanks() ────────────────────────────────────────────────────────

def test_describe_blanks_names_story_gaps_as_a_subset_of_the_total():
    # The 08-06 rule: the gap count must be presented INSIDE the total, never as
    # a competing number. So the sentence carries the total AND names the gaps as
    # "of them", so the reader never has to reconcile two figures.
    line = describe_blanks(18, 1)
    assert "18 blanks left to fill" in line
    assert "1 of them a story blurb you write" in line


def test_describe_blanks_pluralizes_multiple_story_gaps():
    line = describe_blanks(19, 2)
    assert "19 blanks left to fill" in line
    assert "2 of them story blurbs you write" in line


def test_describe_blanks_omits_the_story_clause_when_there_are_no_gaps():
    # With every blurb filled, there's no story-gap subset to name — just the
    # fixed human-touch fields. No "story blurb" wording should appear.
    line = describe_blanks(17, 0)
    assert "17 blanks left to fill" in line
    assert "story blurb" not in line
    assert "human-touch fields" in line


def test_describe_blanks_uses_singular_blank_for_a_lone_blank():
    assert "1 blank left to fill" in describe_blanks(1, 0)
    assert "1 blanks" not in describe_blanks(1, 0)


# ── save_newsletter() ────────────────────────────────────────────────────────

def test_save_writes_the_dated_file_and_round_trips(tmp_path):
    draft = render_newsletter([GOOD_ENTRY], issue_number=1, date=datetime.date(2026, 8, 4))
    out = save_newsletter(draft, str(tmp_path), date=datetime.date(2026, 8, 4))
    assert out.endswith("newsletter-2026-08-04.md")
    assert Path(out).read_text(encoding="utf-8") == draft


def test_save_creates_the_output_dir_if_missing(tmp_path):
    nested = tmp_path / "content" / "newsletter"  # does not exist yet
    out = save_newsletter("hello", str(nested), date=datetime.date(2026, 8, 4))
    assert Path(out).exists()


# ── next_issue_number() ──────────────────────────────────────────────────────

def test_first_ever_issue_is_number_one_when_dir_is_missing(tmp_path):
    missing = tmp_path / "content" / "newsletter"  # never created
    assert next_issue_number(str(missing)) == 1


def test_first_ever_issue_is_number_one_when_dir_is_empty(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    assert next_issue_number(str(tmp_path)) == 1


def test_issue_number_is_one_past_the_count_of_prior_newsletters(tmp_path):
    (tmp_path / "newsletter-2026-07-24.md").write_text("x", encoding="utf-8")
    (tmp_path / "newsletter-2026-07-31.md").write_text("x", encoding="utf-8")
    # today's file doesn't exist yet, so it's a brand-new issue: 2 prior → #3
    assert next_issue_number(str(tmp_path), date=datetime.date(2026, 8, 7)) == 3


def test_same_day_rerun_does_not_bump_the_issue_number(tmp_path):
    # Two prior issues plus TODAY's already saved. Re-running must reuse #3, not
    # jump to #4 — the same-day file is overwritten, not added as a new issue.
    (tmp_path / "newsletter-2026-07-24.md").write_text("x", encoding="utf-8")
    (tmp_path / "newsletter-2026-07-31.md").write_text("x", encoding="utf-8")
    (tmp_path / "newsletter-2026-08-07.md").write_text("x", encoding="utf-8")
    assert next_issue_number(str(tmp_path), date=datetime.date(2026, 8, 7)) == 3


def test_issue_count_ignores_unrelated_files(tmp_path):
    # Only newsletter-YYYY-MM-DD.md files count — not the research digests,
    # a README, or a stray note that happens to share the folder.
    (tmp_path / "newsletter-2026-07-24.md").write_text("x", encoding="utf-8")
    (tmp_path / "digest-2026-07-24.md").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert next_issue_number(str(tmp_path), date=datetime.date(2026, 8, 7)) == 2
