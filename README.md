# AI News Agent

An agent that fetches AI news, ranks it for relevance, summarizes it in my voice, and drafts my weekly newsletter — so I stop manually assembling it every week.

This is Project 1 of 9 in my 9-month AI build challenge. I'm building 9 shipped AI products while doing an M.Sc. in AI, and documenting every one on YouTube.

## What it does (v1 — current state)

Right now this repo holds the **foundation**: a script that pulls the latest AI headlines from 9 RSS feeds (TechCrunch, The Verge, VentureBeat, MIT Tech Review, Ars Technica, OpenAI, Google AI, Hugging Face, Wired) and writes them to a markdown digest.

v1 does the fetching. It does not yet rank stories by relevance, write real summaries, or produce a send-ready newsletter — that's the whole point of v2.

```
scripts/ai_news_digest.py
```

Run it:

```bash
python scripts/ai_news_digest.py
```

It saves a dated digest to `content/research/digest-YYYY-MM-DD.md` — headlines, source, a truncated snippet of the original article text, and a link. No AI involved yet, just RSS parsing and basic rule-based content-idea suggestions.

## The plan for v2

The goal is one command, run every Friday morning, that produces a newsletter draft I can send after ≤10 minutes of editing. Building it in this order:

1. **Fetch** — RSS from all sources (done, above)
2. **Rank** — send the fetched headlines to the Claude API, get back the top 5 scored for relevance to my audience (creators and entrepreneurs learning AI)
3. **Summarize** — 2–3 sentence summary + "why it matters" per story, written in my voice (`brand/voice.md` baked into the prompt)
4. **Draft** — fill my newsletter template and save a ready-to-edit draft to `content/newsletter/`

Each of those is its own build session — I'm not skipping ahead.

## Why this matters

I write a weekly AI newsletter by hand: reading feeds, picking stories, writing summaries, formatting the email. This agent is meant to take that down to "run a script, read the draft, hit send." It's also my first real repo working with the Claude API, structured outputs, and `.env`-based auth — foundational skills for everything else in this build series.

## Setup

```bash
git clone https://github.com/fellyroy-cmd/ai-news-agent.git
cd ai-news-agent
python scripts/ai_news_digest.py
```

v1 (`ai_news_digest.py`) has no dependencies beyond the Python standard library — just `urllib` and `xml.etree` for RSS parsing.

The Claude API scripts (`hello_claude.py` and everything in v2 from here on) need:

```bash
pip install -r requirements.txt
cp .env.example .env   # then paste your real ANTHROPIC_API_KEY into .env
python scripts/hello_claude.py
```

`.env` is gitignored — your key never gets committed.

## v2 progress

- [x] Fetch RSS (v1) — now with duplicate detection when the same story runs on more than one feed
- [x] First Claude API call — `scripts/hello_claude.py` loads a key from `.env` and summarizes one hardcoded paragraph. Proves the API connection works before it gets wired into the real pipeline.
- [x] Rank fetched headlines by relevance — `scripts/rank_stories.py` sends every fetched story to Claude and gets back the top 5, each with a 1-10 relevance score and a one-line reason, as structured JSON.
- [ ] Summarize each story in Dara's voice (Week 3)
- [ ] Assemble the newsletter draft (Week 4)

Try it (needs an `ANTHROPIC_API_KEY` — see Setup below):

```bash
python scripts/hello_claude.py
python scripts/rank_stories.py
```

No API key yet? Test the ranking logic offline — no key, no network, no cost:

```bash
python scripts/rank_stories.py --dry-run
```

## Status

Week 2 of 4 — ranking. Follow the build on YouTube: "I Automated My Entire AI Newsletter With Python (as a Non-Coder)."
