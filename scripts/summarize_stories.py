#!/usr/bin/env python3
"""
Summarize Stories — Week 3: per-story summaries in Dara's brand voice.

Takes the top stories that rank_stories.py picked and asks Claude to write,
for each one, a short newsletter blurb in Dara's voice: a 2-3 sentence plain
summary plus a "why it matters" takeaway for the audience. The brand-voice
rules from brand/voice.md are baked into the prompt so the output sounds like
Dara, not a generic news wire — that's the whole point of Week 3.

Run for real (needs ANTHROPIC_API_KEY in .env) — ranks today's news, then
summarizes the top picks in one go:
    python scripts/summarize_stories.py

Run offline, no API key or network needed — proves the prompt-building and
JSON-parsing logic work before ever touching the API:
    python scripts/summarize_stories.py --dry-run
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Reuse the ranking step's shared plumbing instead of redefining it here.
# Same audience definition, same model, same fence-handling as the parser —
# one source of truth, per the 2026-07-27 DRY lesson.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rank_stories import AUDIENCE, CLAUDE_MODEL, strip_code_fences

# Dara's voice, distilled from brand/voice.md and baked straight into the
# prompt. If voice.md changes, update this block so summaries stay on-brand.
BRAND_VOICE = """Write in Dara Obafemi's brand voice:
- Clear: no jargon. If a technical term is unavoidable, explain it in plain words.
- Direct: get to the point fast and respect the reader's time.
- Energetic but never hype — enthusiastic without ever writing things like
  "AI will DESTROY everything!!!" or over-selling.
- Trustworthy: factual, no exaggeration, no invented details.
- Relatable: explain it like you're talking to a smart friend who just hasn't
  learned this topic yet — not talking down from a pedestal.
Never sensationalize and never overcomplicate something to sound clever."""


def build_summary_prompt(story: dict) -> str:
    """Turn one fetched story into the instruction Claude needs to write its
    newsletter blurb. Kept separate from the API call so it can be tested (and
    read) without ever making a network request — same design as
    build_ranking_prompt().
    """
    return f"""{BRAND_VOICE}

Here is one AI news story:

Title: {story['title']}
Source: {story['source']}
Original snippet: {story.get('summary', '')}

Write a short newsletter blurb about this story for this audience: {AUDIENCE}.

Respond with ONLY valid JSON, no other text, in exactly this shape:

{{
  "summary": "<2-3 sentences, plain language, on what actually happened>",
  "why_it_matters": "<1-2 sentences on why THIS audience should care — the practical, buildable takeaway>"
}}"""


def parse_summary_response(raw_text: str) -> dict:
    """Pull the summary object out of Claude's response text.

    Same defensive posture as parse_ranking_response(): Claude is asked for
    ONLY JSON but might wrap it in a code fence or return the wrong shape, so
    we strip fences (shared helper) and raise a clear error instead of a
    cryptic one if a required field is missing.
    """
    text = strip_code_fences(raw_text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Claude's summary response wasn't valid JSON: {e}\n\nRaw response:\n{raw_text}"
        )

    if not isinstance(data, dict):
        raise ValueError(f"Summary JSON parsed but wasn't an object. Got: {data!r}")

    missing = {"summary", "why_it_matters"} - data.keys()
    if missing:
        raise ValueError(f"Summary missing field(s) {missing}: {data}")

    # A key being present isn't enough — its value has to be usable. A model
    # can hand back "summary": "" (blank), null, or even a list, all of which
    # pass the "key exists" check above but would land as a broken or empty
    # blurb in the send-ready newsletter. Same posture as finalize_rankings()
    # pinning the top-N contract in code: don't trust the shape, enforce it.
    for field in ("summary", "why_it_matters"):
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Summary field {field!r} must be a non-empty string, got: {value!r}"
            )

    # Return only the two fields we rely on, so a chatty model that adds extra
    # keys can't leak surprise data into the newsletter step. Strip so trailing
    # whitespace from the model doesn't ride along into the draft.
    return {
        "summary": data["summary"].strip(),
        "why_it_matters": data["why_it_matters"].strip(),
    }


def summarize_story(story: dict) -> dict:
    """Send one story to Claude, return {"summary", "why_it_matters"}.

    Mirrors rank_stories()'s client pattern: import the SDK inside the
    function so a missing-key error surfaces first and clearly, rather than as
    an import-time crash.
    """
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment automatically
    prompt = build_summary_prompt(story)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    return parse_summary_response(response.content[0].text)


def summarize_rankings(rankings: list[dict]) -> list[dict]:
    """Attach a voice-matched blurb onto each ranked story.

    rank_stories() gives each entry its full original story under entry["story"]
    (via attach_stories()). We summarize that original story and stash the
    result under entry["blurb"] = {"summary", "why_it_matters"} so the Week 4
    newsletter builder has everything it needs in one place. If an entry has no
    attached "story" (e.g. a hand-built test entry), we fall back to the entry
    itself, which carries the title. Mutates and returns the same list.

    Batch resilience — the counterpart to the parser's "fail loud": one story's
    blurb coming back malformed (a bad API response, a shape parse_summary_response
    rejects) must NOT kill the whole run. Friday's draft is better with four good
    blurbs and one clearly-flagged gap than a hard crash and no draft at all. So a
    failed story gets blurb=None plus a human-readable blurb_error naming what went
    wrong — visible, not silently dropped — and the batch keeps going. Fail loud on
    the ONE value you're parsing; degrade gracefully when ONE item in a batch fails.
    """
    for entry in rankings:
        story = entry.get("story", entry)
        try:
            entry["blurb"] = summarize_story(story)
            entry["blurb_error"] = None
        except Exception as e:
            # Broad on purpose: at the batch layer, ANY failure on one story
            # (parse error, rate limit, network blip) should isolate to that
            # story, not abort the send-ready run. We record the reason rather
            # than swallow it, so nothing fails silently.
            entry["blurb"] = None
            entry["blurb_error"] = str(e)
    return rankings


# ── Offline test data, used only by --dry-run ───────────────────────────────

SAMPLE_STORY = {
    "source": "TechCrunch AI",
    "title": "OpenAI launches a new tool for building AI agents without code",
    "summary": "The no-code builder lets small teams wire up multi-step AI workflows in a browser.",
}


def run_dry_run():
    """Exercise build_summary_prompt() and parse_summary_response() with a
    canned Claude-shaped response — no API key, no network, no cost. Proves
    the prompt shape and JSON parsing work before spending a real call.
    """
    print("Building summary prompt for one sample story...\n")
    prompt = build_summary_prompt(SAMPLE_STORY)
    print("--- Prompt preview (first 400 chars) ---")
    print(prompt[:400] + "...\n")

    # A fake Claude response, wrapped in a code fence like models sometimes do,
    # to prove the shared fence-stripping works here too.
    fake_response = """```json
{
  "summary": "OpenAI released a no-code tool that lets you build AI agents in the browser by connecting steps visually, no programming required. Small teams can now wire up multi-step workflows themselves.",
  "why_it_matters": "If you've wanted an AI agent but can't code, this drops the barrier to near zero — you can prototype your own workflow this week instead of hiring a developer."
}
```"""

    print("Parsing a sample fenced JSON response (proves fence-stripping works)...\n")
    blurb = parse_summary_response(fake_response)
    print(f"  Summary:        {blurb['summary']}\n")
    print(f"  Why it matters: {blurb['why_it_matters']}\n")

    # Also prove parse_summary_response() correctly REJECTS bad input.
    print("Checking the parser correctly rejects malformed JSON...")
    try:
        parse_summary_response("not json at all")
        print("  FAILED: should have raised an error and didn't")
        sys.exit(1)
    except ValueError:
        print("  OK — malformed input was correctly rejected\n")

    print("Dry run complete. Prompt-building and JSON parsing both check out.")
    print("No API call was made — nothing here required a key or network access.")


def main():
    if "--dry-run" in sys.argv:
        run_dry_run()
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("No ANTHROPIC_API_KEY found.")
        print("Add one to a .env file in the project root, e.g.:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        print("See .env.example for the expected format.")
        print("\nWant to test the summarization logic without a key? Run:")
        print("  python scripts/summarize_stories.py --dry-run")
        sys.exit(1)

    # Reuse the real fetch → rank pipeline so this summarizes the actual
    # top-ranked headlines, not canned data.
    from rank_stories import rank_stories
    from ai_news_digest import FEEDS, fetch_feed, deduplicate_articles

    print("Fetching AI news...\n")
    all_stories = []
    for feed in FEEDS:
        all_stories.extend(fetch_feed(feed))
    all_stories = deduplicate_articles(all_stories)

    if not all_stories:
        print("No stories fetched — check your internet connection.")
        sys.exit(1)

    print(f"Fetched {len(all_stories)} stories. Ranking, then summarizing the top picks...\n")

    try:
        rankings = rank_stories(all_stories)
        rankings = summarize_rankings(rankings)
    except Exception as e:
        print(f"Summarization failed: {e}")
        sys.exit(1)

    failed = [r for r in rankings if r["blurb"] is None]
    ok = len(rankings) - len(failed)
    header = f"Summarized {ok} of {len(rankings)} top stories in Dara's voice"
    header += f" ({len(failed)} need a manual blurb):\n" if failed else ":\n"
    print(header)
    for r in rankings:
        blurb = r["blurb"]
        print(f"  [{r['relevance_score']}/10] {r['title']}")
        if blurb is None:
            print(f"     [!] Summary failed — needs a manual blurb: {r['blurb_error']}\n")
            continue
        print(f"     {blurb['summary']}")
        print(f"     Why it matters: {blurb['why_it_matters']}\n")


if __name__ == "__main__":
    main()
