#!/usr/bin/env python3
"""Generate one weekly issue of *The Long Run*.

Pipeline:
  1. Ask Claude (with the web_search server tool) to find the week's most relevant
     Brazilian + international economics & politics stories.
  2. Have it write the issue as structured JSON, in the economist persona
     (persona.md) — mixed depth: 1-2 lead deep dives + several short explainers.
  3. Save data/<slug>.json, render issues/<slug>.html, and update issues.json +
     index.html (the archive).

Run:
    python3 generate_issue.py                 # this week's issue (Mon-anchored)
    python3 generate_issue.py --date 2026-05-25
    python3 generate_issue.py --dry-run       # generate + save JSON, skip render
    python3 generate_issue.py --model claude-opus-4-8

Auth: Claude Code OAuth token from ~/.claude/.credentials.json (no API key).
"""

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic

import render as renderer

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PERSONA_PATH = ROOT / "persona.md"
INDEX_PATH = ROOT / "issues.json"
CREDS_PATH = Path.home() / ".claude" / ".credentials.json"

DEFAULT_MODEL = "claude-sonnet-4-6"  # strong + OAuth/web_search friendly; bump to opus for depth

PUBLICATION = "The Long Run"
TAGLINE = "Economics & politics, explained — once a week, with the theory underneath."


# ──────────────────────────────────────────────────────────────────────────
# Dates
# ──────────────────────────────────────────────────────────────────────────
def week_window(anchor: date):
    """Return (monday, sunday, slug, 'Mon D–D, YYYY') for the week containing anchor."""
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    slug = monday.isoformat()
    if monday.month == sunday.month:
        label = f"{monday.strftime('%b')} {monday.day}–{sunday.day}, {sunday.year}"
    else:
        label = f"{monday.strftime('%b')} {monday.day} – {sunday.strftime('%b')} {sunday.day}, {sunday.year}"
    return monday, sunday, slug, label


def issue_number(slug: str) -> int:
    """Sequential issue number = count of existing issues with an earlier slug + 1."""
    if not INDEX_PATH.exists():
        return 1
    idx = json.loads(INDEX_PATH.read_text())
    slugs = sorted({i["slug"] for i in idx.get("issues", [])} | {slug})
    return slugs.index(slug) + 1


# ──────────────────────────────────────────────────────────────────────────
# Prompting
# ──────────────────────────────────────────────────────────────────────────
SCHEMA_INSTRUCTIONS = """\
Produce ONE issue as a single JSON object. Output ONLY the JSON, wrapped in a
```json fenced block at the very end of your reply. Use this exact shape:

{
  "title": "a short thematic title for this week's issue (not a headline, a theme)",
  "editors_note": "2-4 friendly sentences: what tied the week together, what to read for. Warm, human, a little wry. No 'In this issue'.",
  "leads": [            // 1 to 2 deep-dive articles — the big stories of the week
    {
      "headline": "punchy, specific, not clickbait",
      "dek": "one sentence that says what the piece argues",
      "region": "Brazil" | "World" | "Brazil & World",
      "body": ["paragraph", "paragraph", ...],   // 5-9 paragraphs, friendly explainer prose
      "why_it_matters": "2-3 sentences a reader could repeat to a friend",
      "theory_lens": {
        "concept": "the core economic/political-economy idea (e.g. 'Center-periphery & terms of trade')",
        "orthodox": "how the mainstream reads this (1-3 sentences)",
        "heterodox": "how a heterodox economist reads it differently (1-3 sentences)",
        "takeaway": "plain-language bottom line — what YOU think and why (1-2 sentences)"
      },
      "sources": [ {"title": "outlet/source name", "url": "https://..."} ]   // 2-5 real sources you actually used
    }
  ],
  "briefs": [           // 4 to 6 short explainers — smaller but still 'why it matters'
    {
      "headline": "...",
      "region": "Brazil" | "World" | "Brazil & World",
      "body": ["paragraph", "paragraph"],   // 2-3 tight paragraphs
      "why_it_matters": "1-2 sentences",
      "concept": "the one econ/poli-econ idea this story illustrates",
      "sources": [ {"title": "...", "url": "https://..."} ]
    }
  ],
  "glossary": [ {"term": "...", "plain": "a one-line plain-English definition"} ]  // 3-6 terms you used that a curious non-economist might not know
}

Hard rules:
- Cover BOTH Brazil and the wider world. At least one lead or several briefs must be Brazil-focused.
- Every claim with a number or a specific fact must trace to a source in that item's "sources" (use real URLs from your searches).
- Theory must be load-bearing, not decoration: the lens should actually change how you read the story.
- Write in the persona's voice. Do not sound like an AI or a wire-service report.
- Valid JSON only: escape quotes, no trailing commas, no comments in the actual output.
"""


def build_user_prompt(monday: date, sunday: date, label: str) -> str:
    return f"""\
Write this week's issue of *The Long Run*. The week is {label} \
(Monday {monday.isoformat()} to Sunday {sunday.isoformat()}).

First, use the web_search tool to find the most relevant and consequential
economics & politics news from THIS week — both Brazil and international. Search
several times and from different angles. Prioritise:
  - Brazil: monetary policy (Copom/Selic), fiscal policy & the arcabouço, inflation
    (IPCA), the real, Congress/STF, commodities, industry, labour, social policy.
  - World: the Fed/ECB/major central banks, US & China, trade and tariffs, energy
    and commodities, elections and major political shifts, anything that reshapes
    the global configuration Brazil sits inside.
Favour stories with real analytical meat over celebrity-politics noise. Verify the
key facts against primary or reputable sources before you write.

Then write the issue. {SCHEMA_INSTRUCTIONS}"""


def get_client() -> anthropic.Anthropic:
    creds = json.loads(CREDS_PATH.read_text())
    token = creds["claudeAiOauth"]["accessToken"]
    return anthropic.Anthropic(
        auth_token=token,
        default_headers={"anthropic-beta": "oauth-2025-04-20"},
    )


def extract_json(text: str) -> dict:
    """Pull the last ```json fenced block (or the last {...}) and parse it."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = blocks[-1] if blocks else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found in model response.")
        candidate = text[start : end + 1]
    return json.loads(candidate)


def generate(client, model, monday, sunday, label, retries=5) -> dict:
    """Call Claude with web_search; retry with backoff on rate limits/overload.

    The OAuth token shares rate limits with any active Claude Code session, so 429s
    are expected when run alongside one. The weekly cron runs alone and rarely hits this.
    """
    persona = PERSONA_PATH.read_text()
    delay = 30
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=16000,
                system=[{"type": "text", "text": persona, "cache_control": {"type": "ephemeral"}}],
                tools=[{"type": "web_search_20260209", "name": "web_search", "allowed_callers": ["direct"]}],
                messages=[{"role": "user", "content": build_user_prompt(monday, sunday, label)}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            if not text.strip():
                raise RuntimeError(f"Empty response (stop_reason={resp.stop_reason}).")
            return extract_json(text)
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIStatusError) as e:
            last_err = e
            if attempt == retries:
                break
            wait = delay * attempt
            print(f"  [{type(e).__name__}] attempt {attempt}/{retries} — backing off {wait}s")
            time.sleep(wait)
    raise last_err


# ──────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="any date in the target week (YYYY-MM-DD); default = today")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true", help="save JSON only, skip HTML render")
    args = ap.parse_args()

    anchor = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    monday, sunday, slug, label = week_window(anchor)
    num = issue_number(slug)

    print(f"→ Generating issue #{num} for week of {label} (slug {slug}) with {args.model}")
    client = get_client()
    issue = generate(client, args.model, monday, sunday, label)

    # Stamp metadata (don't trust the model with these)
    issue["slug"] = slug
    issue["number"] = num
    issue["date"] = sunday.isoformat()
    issue["week_of"] = label
    issue["publication"] = PUBLICATION
    issue["tagline"] = TAGLINE
    issue.setdefault("leads", [])
    issue.setdefault("briefs", [])
    issue.setdefault("glossary", [])

    DATA_DIR.mkdir(exist_ok=True)
    data_path = DATA_DIR / f"{slug}.json"
    data_path.write_text(json.dumps(issue, ensure_ascii=False, indent=2))
    print(f"  saved {data_path.relative_to(ROOT)} — {len(issue['leads'])} leads, {len(issue['briefs'])} briefs")

    if args.dry_run:
        print("  --dry-run: skipping render")
        return 0

    renderer.render_all(ROOT, PUBLICATION, TAGLINE)
    print("  rendered HTML + updated archive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
