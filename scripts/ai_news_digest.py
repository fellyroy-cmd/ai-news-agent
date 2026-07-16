#!/usr/bin/env python3
"""
AI News Digest Generator
Fetches the latest AI news from RSS feeds and saves a digest to content/research/
Run: python scripts/ai_news_digest.py
"""

import os
import sys
import json
import datetime
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.error import URLError
from html.parser import HTMLParser

# ── RSS Feed Sources ────────────────────────────────────────────────────────

FEEDS = [
    {"name": "TechCrunch AI",       "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "The Verge AI",        "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "VentureBeat AI",      "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "MIT Tech Review AI",  "url": "https://www.technologyreview.com/feed/"},
    {"name": "Ars Technica AI",     "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"name": "OpenAI Blog",         "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google AI Blog",      "url": "https://blog.google/technology/ai/rss/"},
    {"name": "Hugging Face Blog",   "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Wired AI",            "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
]

MAX_ITEMS_PER_FEED = 3   # How many stories to pull per source
OUTPUT_DIR = "content/research"

# ── HTML Stripper ────────────────────────────────────────────────────────────

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return "".join(self.fed)


def strip_html(html: str) -> str:
    s = HTMLStripper()
    s.feed(html)
    return s.get_data().strip()


def truncate(text: str, max_chars: int = 200) -> str:
    text = " ".join(text.split())  # collapse whitespace
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."

# ── RSS Parser ───────────────────────────────────────────────────────────────

def fetch_feed(feed: dict) -> list[dict]:
    """Fetch and parse an RSS feed. Returns list of article dicts."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DaraNewsBot/1.0)"}
    try:
        req = Request(feed["url"], headers=headers)
        with urlopen(req, timeout=10) as resp:
            data = resp.read()
        root = ET.fromstring(data)
    except (URLError, ET.ParseError) as e:
        print(f"  [skip] {feed['name']}: {e}")
        return []

    items = []
    # Handle both RSS <channel><item> and Atom <entry> formats
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for entry in entries[:MAX_ITEMS_PER_FEED]:
        title = (
            entry.findtext("title") or
            entry.findtext("atom:title", namespaces=ns) or
            "No title"
        ).strip()

        link = (
            entry.findtext("link") or
            (entry.find("atom:link", ns).get("href") if entry.find("atom:link", ns) is not None else "") or
            ""
        ).strip()

        summary_raw = (
            entry.findtext("description") or
            entry.findtext("summary") or
            entry.findtext("atom:summary", namespaces=ns) or
            entry.findtext("atom:content", namespaces=ns) or
            ""
        )
        summary = truncate(strip_html(summary_raw))

        pub_date = (
            entry.findtext("pubDate") or
            entry.findtext("atom:published", namespaces=ns) or
            entry.findtext("atom:updated", namespaces=ns) or
            ""
        ).strip()

        items.append({
            "source": feed["name"],
            "title": title,
            "link": link,
            "summary": summary,
            "date": pub_date,
        })

    return items


# ── Content Ideas Generator ──────────────────────────────────────────────────

def generate_content_ideas(articles: list[dict]) -> list[str]:
    """Simple rule-based content idea generator from headlines."""
    ideas = []
    keywords = {
        "released": "First look: {title}",
        "launches": "I tested {source}'s new AI — here's what happened",
        "vs": "Which is actually better? {title}",
        "how": "How to use this: {title}",
        "warning": "This AI concern is real — let's talk about it",
        "beats": "{title} — what this means for creators",
        "replace": "Will AI replace [X]? Let's be honest",
        "free": "This free AI tool just changed everything",
        "open": "Open source AI is winning — here's why it matters",
        "gpt": "GPT update breakdown — what actually changed",
        "gemini": "Google Gemini update — is it worth switching?",
        "claude": "Claude just got an upgrade — here's what's new",
        "agent": "AI agents explained — what they are and why you need to care",
    }

    seen = set()
    for article in articles[:10]:
        title_lower = article["title"].lower()
        for kw, template in keywords.items():
            if kw in title_lower and template not in seen:
                idea = template.format(
                    title=article["title"],
                    source=article["source"]
                )
                ideas.append(idea)
                seen.add(template)
                break

    if not ideas:
        ideas = [f"AI news breakdown: top stories this week ({datetime.date.today().strftime('%B %Y')})"]

    return ideas[:5]


# ── Digest Writer ────────────────────────────────────────────────────────────

def write_digest(articles: list[dict], output_dir: str) -> str:
    today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")
    friendly_date = today.strftime("%B %d, %Y")

    ideas = generate_content_ideas(articles)

    lines = [
        f"# AI News Digest — {friendly_date}",
        "",
        f"*Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {len(FEEDS)} feeds | Stories: {len(articles)}*",
        "",
        "---",
        "",
        "## Top Stories",
        "",
    ]

    for i, article in enumerate(articles, 1):
        lines += [
            f"### {i}. {article['title']}",
            f"**Source:** {article['source']}",
        ]
        if article["summary"]:
            lines.append(f"**Summary:** {article['summary']}")
        if article["link"]:
            lines.append(f"**Link:** {article['link']}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Content Ideas From This Week's News",
        "",
    ]
    for idea in ideas:
        lines.append(f"- {idea}")

    lines += [
        "",
        "---",
        "",
        "## Newsletter Pick",
        "",
        f"Best story for this week's newsletter: **{articles[0]['title']}** ({articles[0]['source']})",
        f"> {articles[0]['summary']}",
        "",
        "---",
        "",
        "*Run `/ai-news` in Claude to regenerate, or `/new-idea` to expand these into full content plans.*",
    ]

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"digest-{date_str}.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching AI news...\n")

    all_articles = []
    for feed in FEEDS:
        print(f"  Fetching: {feed['name']}")
        articles = fetch_feed(feed)
        all_articles.extend(articles)
        print(f"    -> {len(articles)} stories")

    if not all_articles:
        print("\nNo articles fetched. Check your internet connection or RSS feed URLs.")
        sys.exit(1)

    print(f"\nTotal stories collected: {len(all_articles)}")

    # Determine output directory relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(script_dir)
    output_dir = os.path.join(workspace_root, OUTPUT_DIR)

    filepath = write_digest(all_articles, output_dir)
    print(f"\nDigest saved to: {filepath}")
    print("\nDone. Open the digest file or run /ai-news in Claude to review.")


if __name__ == "__main__":
    main()
