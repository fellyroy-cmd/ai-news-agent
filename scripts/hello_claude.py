#!/usr/bin/env python3
"""
Hello Claude — first API call
Loads ANTHROPIC_API_KEY from a .env file and asks Claude to summarize
one hardcoded AI news paragraph. This is the smallest possible proof
that the API connection works before v2 wires it into the real pipeline
(ranking headlines, writing summaries in Dara's voice, drafting the newsletter).

Run: python scripts/hello_claude.py
"""

import os
import sys

from dotenv import load_dotenv

# Load variables from a local .env file (never committed — see .gitignore)
load_dotenv()

# One hardcoded paragraph of AI news to summarize. Later, this same
# "send text to Claude, get a summary back" call gets reused for every
# story the RSS fetcher pulls in.
SAMPLE_PARAGRAPH = """
OpenAI announced this week that its latest model update brings faster response
times and lower costs for developers building on its API, while also expanding
the context window so the model can process much longer documents in a single
request. The company said the changes are aimed at making it cheaper for
startups and independent developers to build AI-powered products without
needing enterprise-level budgets. Several early-access partners reported that
the update cut their per-request costs by roughly a third while maintaining
similar output quality, though some developers noted they still had to adjust
their prompts to get consistent results with the new version.
"""

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"


def summarize_paragraph(text: str) -> str:
    """Send one paragraph to Claude and return a short summary.

    Kept as its own function (instead of inline in main()) so v2 can import
    and reuse this exact call — same pattern, different input — once it's
    summarizing real fetched articles instead of one hardcoded paragraph.
    """
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment automatically

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": f"Summarize this in 2 sentences:\n\n{text}",
            }
        ],
    )

    return response.content[0].text


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        print("No ANTHROPIC_API_KEY found.")
        print("Add one to a .env file in the project root, e.g.:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        print("See .env.example for the expected format.")
        sys.exit(1)

    print("Sending paragraph to Claude...\n")

    try:
        summary = summarize_paragraph(SAMPLE_PARAGRAPH)
    except Exception as e:
        print(f"API call failed: {e}")
        sys.exit(1)

    print("Original paragraph:")
    print(SAMPLE_PARAGRAPH.strip())
    print("\nClaude's summary:")
    print(summary)


if __name__ == "__main__":
    main()
