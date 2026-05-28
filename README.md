# The Long Run

A weekly newspaper that explains economics & politics — the facts of the week, then
the *why* and the consequences, with the economic theory (orthodox **and** heterodox)
underneath. Written in a friendly, plain voice — not AI-flavoured, not wire-service dry.

**Live:** https://iamcamisp.github.io/the-long-run/

## How it works

```
persona.md          ← the economist/political-scientist voice & method (the "skill")
generate_issue.py   ← web_search for the week's news → write the issue as JSON (Claude API)
render.py           ← data/*.json → issues/<slug>.html + index.html + issues.json
update_and_push.sh  ← weekly cron: generate → commit → push
data/<slug>.json    ← raw structured issue (editable by hand, then re-render)
issues/<slug>.html  ← rendered pages (generated — don't edit directly)
```

Each issue: 1–2 lead deep dives + 4–6 short explainers + a plain-English glossary.
Every article carries a **Why it matters** box; leads also carry a **theory underneath**
box contrasting the mainstream and heterodox readings.

## Run it

```bash
python3 generate_issue.py                  # this week's issue (Monday-anchored)
python3 generate_issue.py --date 2026-05-25
python3 generate_issue.py --dry-run        # generate JSON only, skip render
python3 generate_issue.py --model claude-opus-4-8   # deeper (slower/heavier)
python3 render.py                          # re-render everything from data/*.json
```

Auth: Claude Code OAuth token from `~/.claude/.credentials.json` (no API key needed).
Shares rate limits with active Claude Code sessions — default model is Sonnet 4.6.

## Editing an issue by hand

Edit `data/<slug>.json`, then `python3 render.py`, commit, push. The schema is in
`generate_issue.py` (`SCHEMA_INSTRUCTIONS`).

## Automation

Weekly cron runs `update_and_push.sh` on Mondays. Output logged to `refresh.log`.
