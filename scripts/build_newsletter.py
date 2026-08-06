#!/usr/bin/env python3
"""
Build Newsletter — Week 4: assemble the send-ready draft.

This is the last step of the v2 pipeline and the whole reason the project
exists. The earlier steps fetch (ai_news_digest), rank (rank_stories), and
summarize in Dara's voice (summarize_stories). This one takes those
voice-matched blurbs and drops them into Dara's newsletter template, producing
a markdown draft in content/newsletter/ that needs ≤10 minutes of editing
before send.

Design mirrors the rest of the pipeline:
  - The template is baked in as a constant (NEWSLETTER_TEMPLATE-style rendering
    in render_newsletter) so this repo stays self-contained and shareable — it
    does NOT reach out to the HQ's templates/newsletter.md at runtime. If that
    template changes, mirror the change here, same way BRAND_VOICE mirrors
    brand/voice.md in summarize_stories.py.
  - Rendering (pure string work) is kept separate from saving (file I/O) so the
    hard part — getting the draft to look right — is fully testable offline,
    with no API key, no network, no disk writes. Same split as
    build_ranking_prompt vs the API call.
  - Batch resilience carries through from summarize_stories: a story whose blurb
    failed (blurb is None) is rendered as a clearly-flagged manual-blurb gap,
    NOT silently dropped and NOT a crash. Friday's draft is more useful with
    four good stories and one visible "write this one yourself" note than with a
    hole you don't notice until after you hit send.

Run for real (needs ANTHROPIC_API_KEY in .env) — fetches, ranks, summarizes,
then writes the draft to content/newsletter/:
    python scripts/build_newsletter.py

Run offline, no API key or network needed — assembles a draft from canned
ranked+summarized data so you can see exactly what the output looks like:
    python scripts/build_newsletter.py --dry-run
"""

import datetime
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = "content/newsletter"

# Human-touch sections the agent can't (and shouldn't) invent: subject lines,
# the tool of the week, the video link, the Skool prompt. We leave these as
# clearly-marked TODOs so the ≤10-minute edit is guided, not a blank page. This
# is deliberate — a fabricated tool recommendation or made-up video link would
# be worse than an obvious placeholder. "Fill what we can, flag what we can't."
TODO = "[TODO: {}]"


def render_story_block(entry: dict, index: int) -> str:
    """Render one numbered story for the 'This Week in AI' section.

    Pulls the voice-matched blurb (summary + why_it_matters) that
    summarize_stories.py attached under entry["blurb"], and the original story's
    link (under entry["story"], attached by attach_stories in rank_stories.py)
    for the 'Read more' line.

    If entry["blurb"] is None the summary step failed for this one story. Per the
    batch-resilience contract we surface that as a visible manual-blurb TODO that
    names what went wrong — never a silent drop, never a crash. The story still
    takes its slot in the newsletter so the numbering and the link are there and
    Dara only has to write the two sentences.
    """
    title = entry.get("title", "Untitled story")
    story = entry.get("story", {})
    link = story.get("link", "")

    lines = [f"**{index}. {title}**"]

    blurb = entry.get("blurb")
    if blurb is None:
        reason = entry.get("blurb_error") or "auto-summary unavailable"
        lines.append(TODO.format(f"write this blurb manually — auto-summary failed: {reason}"))
    else:
        # summary = what happened; why_it_matters = why the reader cares. The
        # template wants both in the 2-3 sentence block, so join them on one line.
        lines.append(f"{blurb['summary']} {blurb['why_it_matters']}")

    lines.append(f"→ Read more: {link}" if link else TODO.format("add the source link"))
    return "\n".join(lines)


def render_this_week_in_ai(rankings: list[dict]) -> str:
    """Render the whole 'This Week in AI' section from the ranked stories.

    Renumbers 1..N over the entries as given (they arrive already sorted
    highest-relevance-first from finalize_rankings). If there are no stories at
    all — e.g. every feed was down — we emit a visible placeholder instead of a
    blank section, so the failure is obvious in the draft rather than looking
    like an empty-but-fine newsletter.
    """
    if not rankings:
        return TODO.format("no stories were ranked this week — check the fetch/rank step")
    blocks = [render_story_block(entry, i) for i, entry in enumerate(rankings, 1)]
    return "\n\n".join(blocks)


def render_newsletter(rankings: list[dict], issue_number=None, date=None) -> str:
    """Fill Dara's newsletter template with this week's stories, return markdown.

    Pure string work — no file I/O — so it's fully testable. The story section is
    filled from the voice-matched blurbs; the human-touch sections (subject
    lines, tool of the week, video, community) are left as guided TODOs (see the
    TODO note above for why we don't auto-invent those).
    """
    date = date or datetime.date.today()
    friendly_date = date.strftime("%B %d, %Y")
    issue = str(issue_number) if issue_number is not None else "[#]"

    lines = [
        "# Dara Obafemi's AI Weekly",
        "",
        f"**Issue #:** {issue}",
        f"**Date:** {friendly_date}",
        "**Subject line options:**",
        f"1. {TODO.format('curiosity-driven subject line')}",
        f"2. {TODO.format('news-driven subject line')}",
        f"3. {TODO.format('how-to-driven subject line')}",
        "",
        "---",
        "",
        "## PREVIEW TEXT",
        TODO.format("one line under the subject, 90 chars max"),
        "",
        "---",
        "",
        "## HEADER",
        '"Hey [first name],"',
        "",
        TODO.format("1-2 sentence personal opener on what mattered in AI this week"),
        "",
        "---",
        "",
        "## THIS WEEK IN AI",
        "",
        render_this_week_in_ai(rankings),
        "",
        "---",
        "",
        "## AI TOOL OF THE WEEK",
        "",
        f"**{TODO.format('tool name')}** — {TODO.format('one-line description')}",
        "",
        f"What it does: {TODO.format('2-3 sentences')}",
        f"Best for: {TODO.format('who should use it')}",
        f"Free or paid? {TODO.format('answer')}",
        f"→ Try it: {TODO.format('link')}",
        "",
        "---",
        "",
        "## THIS WEEK'S VIDEO",
        "",
        f"**{TODO.format('video title')}**",
        TODO.format("1-2 sentences teasing the video"),
        f"→ **Watch now: {TODO.format('YouTube link')}**",
        "",
        "---",
        "",
        "## FROM THE COMMUNITY (Skool)",
        "",
        f"> {TODO.format('quote or discussion topic from the free Skool community')}",
        "",
        f"→ **Join free: {TODO.format('Skool link')}**",
        "",
        "---",
        "",
        "## CLOSING",
        "",
        f"That's it for this week. Reply and let me know: {TODO.format('question to drive replies')}",
        "",
        "Talk soon,",
        "**Dara**",
        "",
        "---",
        "",
        "*[Unsubscribe] · [View in browser]*",
        "*Dara Obafemi · AI Content & Community*",
    ]
    return "\n".join(lines)


def count_manual_gaps(rankings: list[dict]) -> int:
    """How many stories still need a hand-written blurb (blurb came back None).

    Used only to tell Dara, in the run summary, how much of the ≤10-minute edit
    is story-writing vs the fixed human-touch sections — so a run where the API
    quietly failed on 3 of 5 stories reads as 'mostly manual' at a glance.
    """
    return sum(1 for entry in rankings if entry.get("blurb") is None)


# Every unfilled field render_newsletter emits — via TODO.format(...) — starts
# with this exact marker. Counting it tells us the true size of the edit.
TODO_MARKER = "[TODO:"


def count_todos(text: str) -> int:
    """Count the placeholder blanks still left to fill in a rendered draft.

    Every unfilled field — the three subject lines, the preview text, the header
    opener, the whole tool-of-the-week block, the video link, the Skool prompt,
    the closing question, plus any failed-blurb story gap — renders as a
    `[TODO: ...]` marker (see the TODO constant). Counting them turns the vague
    "≤10-minute edit" into a concrete number Dara can see up front — both to know
    how much work is left and to confirm nothing was accidentally left behind.

    Like next_issue_number, this reports a FACT we can derive rather than leaving
    Dara to eyeball it. The one thing to keep straight: this counts ALL the
    blanks, so the total already INCLUDES the story-blurb gaps that
    count_manual_gaps() reports on their own (a failed blurb is itself a TODO).
    The run summary presents both without double-speak — N blanks total, of which
    M are story blurbs you have to write yourself — so the numbers never look
    like they're contradicting each other.
    """
    return text.count(TODO_MARKER)


def save_newsletter(text: str, output_dir: str, date=None) -> str:
    """Write the rendered draft to content/newsletter/newsletter-YYYY-MM-DD.md.

    The only file-I/O function in this module, kept apart from rendering so the
    rendering can be tested without touching disk. Creates the output dir if
    needed, same as write_digest() does.
    """
    date = date or datetime.date.today()
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"newsletter-{date.strftime('%Y-%m-%d')}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    return filepath


# newsletter-YYYY-MM-DD.md — the exact shape save_newsletter() writes. Used to
# recognize prior issues on disk (and to ignore anything else that happens to
# live in the folder).
NEWSLETTER_FILE = re.compile(r"newsletter-\d{4}-\d{2}-\d{2}\.md")


def next_issue_number(output_dir: str, date=None) -> int:
    """Work out the next issue number by counting prior newsletters on disk.

    The issue number is a FACT — it's just "how many weekly issues came before
    this one, plus one" — so unlike the tool of the week or the video link, it's
    something we can (and should) fill in automatically instead of leaving Dara a
    TODO. Deriving it from the filesystem keeps a single source of truth: the
    drafts themselves.

    Two edge cases that matter:
      - No content/newsletter/ yet (or it's empty) → this is issue #1.
      - Re-running on the SAME day must NOT bump the number. Today's file gets
        overwritten, not added, so we exclude it from the count — run the script
        three times on a Friday and it stays issue #N all three times.

    This reads the directory (I/O), so it lives down here with save_newsletter
    rather than up with the pure renderers, and it's tested with tmp_path.
    """
    date = date or datetime.date.today()
    today_name = f"newsletter-{date.strftime('%Y-%m-%d')}.md"
    if not os.path.isdir(output_dir):
        return 1
    prior = [
        name for name in os.listdir(output_dir)
        if NEWSLETTER_FILE.fullmatch(name) and name != today_name
    ]
    return len(prior) + 1


# ── Offline test data, used only by --dry-run ───────────────────────────────
# Shaped exactly like what rank_stories + summarize_rankings produce: each entry
# has title/relevance_score, an attached original story (for the link), and a
# blurb — with one deliberately failed blurb to prove the manual-gap flagging.

SAMPLE_RANKINGS = [
    {
        "title": "OpenAI launches a new tool for building AI agents without code",
        "relevance_score": 9,
        "story": {"link": "https://example.com/openai-no-code-agents"},
        "blurb": {
            "summary": "OpenAI released a no-code tool that lets you build AI agents in the browser by wiring up steps visually.",
            "why_it_matters": "If you've wanted your own AI agent but can't code, the barrier just dropped to near zero — you can prototype one this week.",
        },
        "blurb_error": None,
    },
    {
        "title": "Anthropic releases prompt caching to cut API costs for developers",
        "relevance_score": 8,
        "story": {"link": "https://example.com/anthropic-prompt-caching"},
        "blurb": {
            "summary": "Anthropic added prompt caching, which reuses repeated context across calls so bulk usage costs a lot less.",
            "why_it_matters": "Cheaper API calls mean solo builders can afford to run their own AI tools at scale instead of just testing them.",
        },
        "blurb_error": None,
    },
    {
        # Deliberately failed blurb — proves the manual-gap flag renders instead
        # of dropping the story or crashing the whole draft.
        "title": "New open-source model beats GPT-4 on coding benchmarks",
        "relevance_score": 8,
        "story": {"link": "https://example.com/open-source-coding-model"},
        "blurb": None,
        "blurb_error": "Claude's summary response wasn't valid JSON",
    },
]


def run_dry_run():
    """Assemble a full draft from the canned rankings and print it — no API key,
    no network, no disk write. Shows exactly what the send-ready draft looks
    like, including how a failed blurb appears as a flagged manual gap.
    """
    print("Assembling a newsletter draft from canned ranked+summarized data...\n")
    draft = render_newsletter(SAMPLE_RANKINGS, issue_number=1)
    print("--- Draft preview ---\n")
    print(draft)

    gaps = count_manual_gaps(SAMPLE_RANKINGS)
    todos = count_todos(draft)
    print(
        f"\n\n{len(SAMPLE_RANKINGS)} stories assembled, "
        f"{gaps} {'needs' if gaps == 1 else 'need'} a manual blurb (auto-summary failed) — "
        "flagged inline above, not dropped."
    )
    print(
        f"{todos} blanks ([TODO: ...]) left to fill in this draft — that's the whole "
        "≤10-minute edit surface, story gaps included."
    )
    print("\nDry run complete. Nothing was written to disk; no API call was made.")


def main():
    # The draft (and its "→ Read more" lines) is UTF-8, but the default Windows
    # console is cp1252 and would crash trying to PRINT the arrow — Dara's own
    # machine. Reconfigure stdout to UTF-8 so console output never dies on a
    # character the saved file handles fine. No-op where stdout is already UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # older Python or a stdout that can't be reconfigured — not fatal

    if "--dry-run" in sys.argv:
        run_dry_run()
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("No ANTHROPIC_API_KEY found.")
        print("Add one to a .env file in the project root, e.g.:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        print("See .env.example for the expected format.")
        print("\nWant to see what the assembled draft looks like without a key? Run:")
        print("  python scripts/build_newsletter.py --dry-run")
        sys.exit(1)

    # Reuse the real fetch → rank → summarize pipeline so the draft is built
    # from actual current headlines summarized in Dara's voice.
    from rank_stories import rank_stories
    from summarize_stories import summarize_rankings
    from ai_news_digest import FEEDS, fetch_feed, deduplicate_articles

    print("Fetching AI news...\n")
    all_stories = []
    for feed in FEEDS:
        all_stories.extend(fetch_feed(feed))
    all_stories = deduplicate_articles(all_stories)

    if not all_stories:
        print("No stories fetched — check your internet connection.")
        sys.exit(1)

    print(f"Fetched {len(all_stories)} stories. Ranking, summarizing, then assembling the draft...\n")

    try:
        rankings = rank_stories(all_stories)
        rankings = summarize_rankings(rankings)
    except Exception as e:
        print(f"Pipeline failed before assembly: {e}")
        sys.exit(1)

    # Determine output dir relative to the repo root, same as ai_news_digest.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    output_dir = os.path.join(repo_root, OUTPUT_DIR)

    issue = next_issue_number(output_dir)
    draft = render_newsletter(rankings, issue_number=issue)
    filepath = save_newsletter(draft, output_dir)

    gaps = count_manual_gaps(rankings)
    filled = len(rankings) - gaps
    todos = count_todos(draft)
    print(f"Newsletter draft saved to: {filepath} (issue #{issue})")
    print(
        f"  {filled} of {len(rankings)} stories filled in Dara's voice"
        + (f"; {gaps} need a manual blurb (flagged inline)." if gaps else ".")
    )
    # The total blank count already includes any failed-blurb story gaps, so
    # call those out inside the total rather than as a separate, competing number.
    if gaps:
        print(
            f"  {todos} blanks left to fill — {gaps} of them story blurbs you write, "
            "the rest the fixed human-touch fields (subject lines, tool of the week, video, Skool)."
        )
    else:
        print(
            f"  {todos} blanks left to fill — the fixed human-touch fields "
            "(subject lines, tool of the week, video, Skool)."
        )
    print(f"\nOpen the draft, fill those {todos} TODOs, and it should need ≤10 minutes before send.")


if __name__ == "__main__":
    main()
