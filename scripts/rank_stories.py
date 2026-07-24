#!/usr/bin/env python3
"""
Rank Stories — Week 2: relevance ranking via the Claude API
Takes the list of stories fetched by ai_news_digest.py and asks Claude to
pick the top 5 most relevant to Dara's audience (creators/entrepreneurs
learning AI), scored 1-10 with a one-line reason, returned as JSON.

Run for real (needs ANTHROPIC_API_KEY in .env):
    python scripts/rank_stories.py

Run offline, no API key or network needed — proves the prompt-building and
JSON-parsing logic work before ever touching the API:
    python scripts/rank_stories.py --dry-run
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

# Who we're ranking for — baked into the prompt so "relevance" means the
# same thing every run. Update this if the audience definition ever changes.
AUDIENCE = "content creators and entrepreneurs who are learning AI and want practical, buildable takeaways"

TOP_N = 5


def build_ranking_prompt(stories: list[dict]) -> str:
    """Turn a list of fetched stories into the instruction Claude needs to
    rank them. Kept separate from the API call so it can be tested (and
    read) without ever making a network request.
    """
    numbered = []
    for i, story in enumerate(stories, 1):
        numbered.append(
            f"{i}. \"{story['title']}\" — {story['source']}\n"
            f"   {story.get('summary', '')}"
        )
    story_list = "\n".join(numbered)

    return f"""You are ranking AI news headlines for relevance to this audience: {AUDIENCE}.

Here are {len(stories)} stories, numbered:

{story_list}

Pick the top {TOP_N} stories most relevant to this audience and score each one.
Relevant means: practical, teaches something buildable, affects how creators/
entrepreneurs work, or is a big-enough story they need to know about it.
Not relevant means: pure stock-market/finance angle, enterprise IT minutiae,
or anything with no clear takeaway for this audience.

Respond with ONLY valid JSON, no other text, in exactly this shape:

{{
  "rankings": [
    {{
      "story_number": <the number from the list above>,
      "title": "<the story's title, copied exactly>",
      "relevance_score": <integer 1-10, 10 = most relevant>,
      "reason": "<one sentence explaining why this matters to the audience>"
    }}
  ]
}}

Return exactly {TOP_N} entries in "rankings", sorted highest score first."""


def parse_ranking_response(raw_text: str) -> list[dict]:
    """Pull the rankings list out of Claude's response text.

    Claude is asked to return ONLY JSON, but models occasionally wrap it in
    ```json fences or add a stray sentence — so we don't trust raw_text to
    be clean JSON as-is. This strips common wrapping before parsing, and
    raises a clear error (instead of a cryptic one) if the shape is wrong.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present, e.g. ```json ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence (``` or ```json)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # drop closing fence
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude's response wasn't valid JSON: {e}\n\nRaw response:\n{raw_text}")

    if "rankings" not in data or not isinstance(data["rankings"], list):
        raise ValueError(f"JSON parsed but missing a 'rankings' list. Got: {data}")

    for entry in data["rankings"]:
        missing = {"story_number", "title", "relevance_score", "reason"} - entry.keys()
        if missing:
            raise ValueError(f"Ranking entry missing field(s) {missing}: {entry}")

    return data["rankings"]


def _coerce_score(value) -> int:
    """Turn whatever Claude put in relevance_score into an int we can sort by.

    The prompt asks for an integer, but models sometimes hand back "9"
    (a string) or 9.0 (a float). Both are fine and get normalized. Only
    genuinely non-numeric garbage ("high") raises — better to surface that
    loudly than to silently sort it as zero.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            raise ValueError(f"relevance_score isn't a number: {value!r}")


def finalize_rankings(rankings: list[dict]) -> list[dict]:
    """Enforce the top-N contract in code instead of trusting the model.

    The prompt asks Claude for "exactly TOP_N entries, sorted highest score
    first" — but a prompt is a request, not a guarantee. Claude might return
    six entries, or return them out of order. This normalizes each score to
    an int, sorts highest-first, and caps the result at TOP_N so downstream
    code (the newsletter builder) always gets exactly what it expects.
    """
    for entry in rankings:
        entry["relevance_score"] = _coerce_score(entry["relevance_score"])
    ranked = sorted(rankings, key=lambda e: e["relevance_score"], reverse=True)
    return ranked[:TOP_N]


def rank_stories(stories: list[dict]) -> list[dict]:
    """Send fetched stories to Claude, return the top N ranked with scores.

    Mirrors the client pattern from hello_claude.py's summarize_paragraph():
    import the SDK inside the function so a missing-key error surfaces
    first and clearly, rather than as an import-time crash.
    """
    from anthropic import Anthropic

    if not stories:
        return []

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment automatically
    prompt = build_ranking_prompt(stories)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text
    rankings = parse_ranking_response(raw_text)
    rankings = finalize_rankings(rankings)  # sort highest-first, cap to TOP_N

    # Attach the full original story dict (link, date, etc.) back onto each
    # ranking so downstream code (Week 3 summarization, Week 4 newsletter)
    # has everything in one place, not just the number/title Claude echoed.
    for entry in rankings:
        idx = entry["story_number"] - 1
        if 0 <= idx < len(stories):
            entry["story"] = stories[idx]

    return rankings


# ── Offline test data, used only by --dry-run ───────────────────────────────

SAMPLE_STORIES = [
    {"source": "TechCrunch AI", "title": "OpenAI launches a new tool for building AI agents without code",
     "summary": "The no-code builder lets small teams wire up multi-step AI workflows in a browser."},
    {"source": "MIT Tech Review AI", "title": "Chipmaker reports record quarterly earnings on AI datacenter demand",
     "summary": "Wall Street analysts raised price targets after the earnings call."},
    {"source": "The Verge AI", "title": "Google adds AI-generated chapter summaries to YouTube Studio",
     "summary": "Creators can now auto-generate timestamped chapters from a video transcript."},
    {"source": "Wired AI", "title": "New study questions accuracy of AI-generated medical advice",
     "summary": "Researchers found inconsistent answers across several chatbot models on common symptoms."},
    {"source": "VentureBeat AI", "title": "Anthropic releases prompt caching to cut API costs for developers",
     "summary": "The feature reuses repeated prompt context so bulk API calls cost significantly less."},
    {"source": "Ars Technica AI", "title": "Enterprise AI governance framework updated by industry consortium",
     "summary": "The revision adds compliance checklists aimed at large regulated companies."},
    {"source": "Hugging Face Blog", "title": "New open-source model beats GPT-4 on coding benchmarks",
     "summary": "The model is free to download and fine-tune, and runs on a single high-end GPU."},
]


def run_dry_run():
    """Exercise build_ranking_prompt() and parse_ranking_response() with a
    canned Claude-shaped response — no API key, no network, no cost.
    Proves the two hardest-to-get-wrong parts (prompt shape, JSON parsing)
    work before ever spending a real API call on them.
    """
    print(f"Building ranking prompt for {len(SAMPLE_STORIES)} sample stories...\n")
    prompt = build_ranking_prompt(SAMPLE_STORIES)
    print("--- Prompt preview (first 400 chars) ---")
    print(prompt[:400] + "...\n")

    # A fake Claude response, wrapped in a code fence like models sometimes
    # do, to prove the fence-stripping in parse_ranking_response() works.
    fake_response = """```json
{
  "rankings": [
    {"story_number": 1, "title": "OpenAI launches a new tool for building AI agents without code", "relevance_score": 9, "reason": "Directly buildable — creators can use this no-code agent tool themselves."},
    {"story_number": 5, "title": "Anthropic releases prompt caching to cut API costs for developers", "relevance_score": 8, "reason": "Lowers the cost barrier for solo builders shipping their own AI tools."},
    {"story_number": 7, "title": "New open-source model beats GPT-4 on coding benchmarks", "relevance_score": 8, "reason": "Free, downloadable model creators can experiment with immediately."},
    {"story_number": 3, "title": "Google adds AI-generated chapter summaries to YouTube Studio", "relevance_score": 7, "reason": "A direct workflow upgrade for the exact platform this audience creates on."},
    {"story_number": 4, "title": "New study questions accuracy of AI-generated medical advice", "relevance_score": 4, "reason": "Relevant as a cautionary talking point but not a buildable takeaway."}
  ]
}
```"""

    print("Parsing a sample fenced JSON response (proves fence-stripping works)...\n")
    rankings = parse_ranking_response(fake_response)
    rankings = finalize_rankings(rankings)  # sort highest-first, cap to TOP_N

    for entry in rankings:
        idx = entry["story_number"] - 1
        if 0 <= idx < len(SAMPLE_STORIES):
            entry["story"] = SAMPLE_STORIES[idx]

    print(f"Parsed {len(rankings)} ranked stories:\n")
    for r in rankings:
        print(f"  [{r['relevance_score']}/10] {r['title']}")
        print(f"           {r['reason']}\n")

    # Also prove parse_ranking_response() correctly REJECTS bad input.
    print("Checking the parser correctly rejects malformed JSON...")
    try:
        parse_ranking_response("not json at all")
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
        print("\nWant to test the ranking logic without a key? Run:")
        print("  python scripts/rank_stories.py --dry-run")
        sys.exit(1)

    # Reuse the real fetcher so this ranks actual current headlines.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ai_news_digest import FEEDS, fetch_feed, deduplicate_articles

    print("Fetching AI news...\n")
    all_stories = []
    for feed in FEEDS:
        all_stories.extend(fetch_feed(feed))
    all_stories = deduplicate_articles(all_stories)

    if not all_stories:
        print("No stories fetched — check your internet connection.")
        sys.exit(1)

    print(f"Fetched {len(all_stories)} stories. Sending to Claude for ranking...\n")

    try:
        rankings = rank_stories(all_stories)
    except Exception as e:
        print(f"Ranking failed: {e}")
        sys.exit(1)

    print(f"Top {len(rankings)} stories by relevance:\n")
    for r in rankings:
        print(f"  [{r['relevance_score']}/10] {r['title']}")
        print(f"           {r['reason']}\n")


if __name__ == "__main__":
    main()
