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
TAGLINE = "Economics, politics & technology, explained. Once a week, with the theory underneath."

# The filter pills on the site. Each article is tagged with one or more of these.
CATEGORIES = ["Brazil", "Europe", "USA", "International", "Technology"]


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
  "leads": [            // 1 to 2 deep-dive articles, the big stories of the week
    {
      "headline": "punchy, specific, not clickbait",
      "dek": "one sentence that says what the piece argues",
      "categories": ["Brazil"],   // 1 to 2 of: Brazil, Europe, USA, International, Technology
      "body": ["paragraph", "paragraph", ...],   // 5-9 paragraphs of friendly explainer prose
      "why_it_matters": "2-3 sentences a reader could repeat to a friend",
      "theory_lens": {
        "concept": "the core economic or political economy idea (for example 'the center and periphery model')",
        "orthodox": "how the mainstream reads this (1-3 sentences)",
        "heterodox": "how a heterodox economist reads it differently (1-3 sentences)",
        "takeaway": "the plain bottom line, what YOU think and why (1-2 sentences)"
      },
      "sources": [ {"title": "outlet/source name", "url": "https://..."} ]   // 2-5 real sources you actually used
    }
  ],
  "briefs": [           // 4 to 6 short explainers, smaller but still with a 'why it matters'
    {
      "headline": "...",
      "categories": ["Technology"],   // 1 to 2 of: Brazil, Europe, USA, International, Technology
      "body": ["paragraph", "paragraph"],   // 2-3 tight paragraphs
      "why_it_matters": "1-2 sentences",
      "concept": "the one econ or political economy idea this story illustrates",
      "sources": [ {"title": "...", "url": "https://..."} ]
    }
  ],
  "glossary": [ {"term": "...", "plain": "a one-line plain definition"} ]  // 3-6 terms you used that a curious non-economist might not know
}

Categories (use ONLY these, 1-2 per article, choose the best fit):
  - "Brazil"        anything centred on Brazil.
  - "Europe"        the euro area, the ECB, the EU, individual European countries.
  - "USA"           the United States, the Fed, US politics and policy.
  - "International"  global/cross-border stories, China, emerging markets, trade,
                     commodities, multilateral bodies, or anything not tied to one
                     of the regions above.
  - "Technology"    AI, chips, platforms, digital policy and the economics of tech.
                     Tag a story Technology AND its region when both fit (e.g. a US
                     chip-export story is ["USA", "Technology"]).

Hard rules:
- Spread coverage across the categories. At least one Brazil item every issue, and
  include at least one Technology item (the tech-and-economy angle).
- Every claim with a number or a specific fact must trace to a source in that item's
  "sources" (use real URLs from your searches).
- Theory must be load-bearing, not decoration: the lens should change how you read it.
- Write in the persona's voice. Do not sound like AI or like a wire report.
- NEVER use em dashes. Use commas, periods, parentheses, or colons.
- Do NOT coin complex hyphenated compound words. Write them out in plain words.
- Valid JSON only: escape quotes, no trailing commas, no comments in the actual output.
"""


def build_user_prompt(start: date, end: date, label: str, today_only: bool = False) -> str:
    if today_only:
        scope = (
            f"Write a special TODAY edition of *The Long Run* for {label} "
            f"({start.isoformat()}).\n\n"
            f"First, use the web_search tool to find the most relevant and consequential "
            f"economics, politics & technology news from TODAY and the last day or two "
            f"({start.isoformat()}). Search several times and from different angles. "
            f"A single day may be quiet, so it is fine to run fewer briefs (2-4) and a "
            f"single lead if only one story really earns the depth. Quality over filling slots. "
            f"Prioritise:"
        )
    else:
        scope = (
            f"Write this week's issue of *The Long Run*. The week is {label} "
            f"(Monday {start.isoformat()} to Sunday {end.isoformat()}).\n\n"
            f"First, use the web_search tool to find the most relevant and consequential "
            f"economics, politics & technology news from THIS week, both Brazil and "
            f"international. Search several times and from different angles. Prioritise:"
        )
    return f"""\
{scope}
  - Brazil: monetary policy (Copom and the Selic), fiscal policy and the spending
    framework, inflation (the IPCA), the real, Congress and the STF, commodities,
    industry, labour, social policy.
  - USA: the Fed, US politics and policy, the dollar, tariffs.
  - Europe: the ECB, the euro area, the EU, major European elections and policy.
  - International: China, emerging markets, global trade, energy and commodities,
    multilateral bodies, anything that reshapes the world Brazil sits inside.
  - Technology: AI, semiconductors, platforms and big tech, digital regulation,
    and what they mean for productivity, jobs, market power, and geopolitics.
Favour stories with real analytical meat over celebrity politics noise. Verify the
key facts against primary or reputable sources before you write.

Then write the issue. {SCHEMA_INSTRUCTIONS}"""


def get_client() -> anthropic.Anthropic:
    creds = json.loads(CREDS_PATH.read_text())
    token = creds["claudeAiOauth"]["accessToken"]
    return anthropic.Anthropic(
        auth_token=token,
        default_headers={"anthropic-beta": "oauth-2025-04-20"},
    )


# Common hyphenated compounds the model coins despite instructions. Mapped to the
# plain form. Keeps real fixed terms / proper nouns alone (handled by not listing them).
DEHYPHEN = {
    "wage-setting": "wage setting",
    "price-setting": "price setting",
    "consumer-price": "consumer price",
    "central-bank": "central bank",
    "year-on-year": "year on year",
    "inflation-targeting": "inflation targeting",
    "interest-rate": "interest rate",
    "long-run": "long run",
    "short-run": "short run",
    "second-order": "second order",
    "first-order": "first order",
    "supply-chain": "supply chain",
    "lock-in": "lock in",
    "decision-making": "decision making",
    "rate-setting": "rate setting",
}


def sanitize_text(s: str) -> str:
    """Strip web_search citation markup and apply the house style (no em dashes,
    no coined hyphenated compounds). Safe to run on any string field."""
    if not isinstance(s, str) or not s:
        return s
    # 1) remove leaked <cite ...>...</cite> markup, keep the inner text
    s = re.sub(r"</?cite[^>]*>", "", s)
    # 2) em dash / en dash -> comma pause (collapse surrounding spaces)
    s = re.sub(r"\s*[—–]\s*", ", ", s)
    # 3) de-hyphenate known coined compounds (case-insensitive, preserve nothing fancy)
    for bad, good in DEHYPHEN.items():
        s = re.sub(rf"\b{re.escape(bad)}\b", good, s, flags=re.IGNORECASE)
    # 4) tidy artefacts: ", ," / space before comma / doubled spaces
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def clean_issue(obj):
    """Recursively sanitize every string in the issue, EXCEPT source URLs."""
    if isinstance(obj, dict):
        return {k: (v if k == "url" else clean_issue(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_issue(v) for v in obj]
    if isinstance(obj, str):
        return sanitize_text(obj)
    return obj


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


def generate(client, model, start, end, label, today_only=False, retries=8) -> dict:
    """Call Claude with web_search; retry with backoff on rate limits/overload.

    The OAuth token shares rate limits with any active Claude Code session, so 429s
    are expected when run alongside one. Honour Retry-After when the server sends it,
    otherwise back off exponentially up to ~5 min between attempts. The weekly cron
    runs with no live session and rarely hits this.
    """
    persona = PERSONA_PATH.read_text()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=16000,
                system=[{"type": "text", "text": persona, "cache_control": {"type": "ephemeral"}}],
                tools=[{"type": "web_search_20260209", "name": "web_search", "allowed_callers": ["direct"]}],
                messages=[{"role": "user", "content": build_user_prompt(start, end, label, today_only)}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            if not text.strip():
                raise RuntimeError(f"Empty response (stop_reason={resp.stop_reason}).")
            return extract_json(text)
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIStatusError) as e:
            last_err = e
            if attempt == retries:
                break
            wait = 60 * (2 ** (attempt - 1))            # 60,120,240,480 -> capped
            retry_after = getattr(getattr(e, "response", None), "headers", {})
            try:
                ra = float(retry_after.get("retry-after")) if retry_after else None
                if ra:
                    wait = ra + 5
            except (TypeError, ValueError):
                pass
            wait = min(wait, 300)
            print(f"  [{type(e).__name__}] attempt {attempt}/{retries} — backing off {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise last_err


# ──────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="any date in the target week (YYYY-MM-DD); default = today")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true", help="save JSON only, skip HTML render")
    ap.add_argument("--today", action="store_true", help="TODAY edition: scope to today's news only")
    args = ap.parse_args()

    anchor = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()

    if args.today:
        start = end = anchor
        slug = anchor.isoformat()
        label = anchor.strftime("%B %-d, %Y")
        scope_word = f"TODAY edition ({label})"
    else:
        start, end, slug, label = week_window(anchor)
        scope_word = f"week of {label}"
    num = issue_number(slug)

    print(f"→ Generating issue #{num} — {scope_word} (slug {slug}) with {args.model}")
    client = get_client()
    issue = generate(client, args.model, start, end, label, today_only=args.today)
    issue = clean_issue(issue)  # strip citation markup + enforce house style

    # Stamp metadata (don't trust the model with these)
    issue["slug"] = slug
    issue["number"] = num
    issue["date"] = end.isoformat()
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
