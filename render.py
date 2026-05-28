#!/usr/bin/env python3
"""Render *The Long Run* from data/*.json into static HTML + issues.json index.

Usable standalone (re-render everything after editing JSON or templates):
    python3 render.py
"""

import html
import json
import sys
from datetime import date
from pathlib import Path

REGION_FLAG = {"Brazil": "🇧🇷", "World": "🌍", "Brazil & World": "🌐"}


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def paras(body) -> str:
    if isinstance(body, str):
        body = [body]
    return "\n".join(f"<p>{esc(p)}</p>" for p in (body or []) if p and p.strip())


def region_tag(region: str) -> str:
    flag = REGION_FLAG.get(region, "🌐")
    return f'<span class="tag">{flag} {esc(region or "World")}</span>'


def sources_block(sources) -> str:
    if not sources:
        return ""
    items = "".join(
        f'<li><a href="{esc(s.get("url",""))}" target="_blank" rel="noopener">{esc(s.get("title","source"))}</a></li>'
        for s in sources if s.get("url")
    )
    if not items:
        return ""
    return f'<div class="sources"><span class="sources-label">Sources</span><ul>{items}</ul></div>'


def theory_box(lens) -> str:
    if not lens:
        return ""
    concept = esc(lens.get("concept", "The theory underneath"))
    rows = ""
    if lens.get("orthodox"):
        rows += f'<div class="lens-row"><span class="lens-name">The mainstream view</span><p>{esc(lens["orthodox"])}</p></div>'
    if lens.get("heterodox"):
        rows += f'<div class="lens-row"><span class="lens-name">The heterodox view</span><p>{esc(lens["heterodox"])}</p></div>'
    takeaway = ""
    if lens.get("takeaway"):
        takeaway = f'<p class="lens-takeaway"><strong>Where we land:</strong> {esc(lens["takeaway"])}</p>'
    return f"""
    <aside class="theory">
      <span class="theory-kicker">The theory underneath</span>
      <h4>{concept}</h4>
      {rows}
      {takeaway}
    </aside>"""


def why_box(text) -> str:
    if not text:
        return ""
    return f'<div class="why"><span class="why-label">Why it matters</span><p>{esc(text)}</p></div>'


def lead_html(a) -> str:
    return f"""
  <article class="lead">
    {region_tag(a.get("region"))}
    <h2>{esc(a.get("headline",""))}</h2>
    <p class="dek">{esc(a.get("dek",""))}</p>
    <div class="body">{paras(a.get("body"))}</div>
    {why_box(a.get("why_it_matters"))}
    {theory_box(a.get("theory_lens"))}
    {sources_block(a.get("sources"))}
  </article>"""


def brief_html(a) -> str:
    concept = ""
    if a.get("concept"):
        concept = f'<span class="concept">The idea: {esc(a["concept"])}</span>'
    return f"""
  <article class="brief">
    <div class="brief-head">{region_tag(a.get("region"))}{concept}</div>
    <h3>{esc(a.get("headline",""))}</h3>
    <div class="body">{paras(a.get("body"))}</div>
    {why_box(a.get("why_it_matters"))}
    {sources_block(a.get("sources"))}
  </article>"""


def glossary_html(glossary) -> str:
    if not glossary:
        return ""
    items = "".join(
        f'<div class="gloss-item"><dt>{esc(g.get("term",""))}</dt><dd>{esc(g.get("plain",""))}</dd></div>'
        for g in glossary if g.get("term")
    )
    if not items:
        return ""
    return f"""
  <section class="glossary">
    <h3>Plain-English glossary</h3>
    <dl>{items}</dl>
  </section>"""


def page_head(title, desc, css="style.css") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Newsreader:ital,opsz@0,6..72;1,6..72&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{css}">
</head>
<body>"""


def render_issue_page(issue, pub, tagline) -> str:
    leads = "\n".join(lead_html(a) for a in issue.get("leads", []))
    briefs = "".join(brief_html(a) for a in issue.get("briefs", []))
    briefs_section = f'<section class="briefs"><h2 class="section-rule">Also this week</h2><div class="brief-grid">{briefs}</div></section>' if briefs else ""
    title = f'{esc(issue.get("title") or pub)} — {pub} #{issue.get("number","")}'
    desc = (issue.get("editors_note") or tagline)[:200]
    return f"""{page_head(title, desc, css="../style.css")}
  <header class="masthead">
    <a class="mast-name" href="../index.html">{esc(pub)}</a>
    <p class="mast-tag">{esc(tagline)}</p>
  </header>
  <main class="issue">
    <div class="issue-meta">
      <span>Issue #{esc(str(issue.get("number","")))}</span>
      <span>Week of {esc(issue.get("week_of",""))}</span>
    </div>
    <h1 class="issue-title">{esc(issue.get("title",""))}</h1>
    <p class="editors-note">{esc(issue.get("editors_note",""))}</p>
    {leads}
    {briefs_section}
    {glossary_html(issue.get("glossary"))}
    <footer class="issue-foot">
      <a href="../index.html">← All issues</a>
      <span>{esc(pub)} · explained, not summarised</span>
    </footer>
  </main>
</body>
</html>"""


def render_index(issues, pub, tagline) -> str:
    issues = sorted(issues, key=lambda i: i["slug"], reverse=True)
    if not issues:
        body = '<p class="empty">First issue lands soon.</p>'
    else:
        latest = issues[0]
        feat = f"""
    <a class="feature" href="issues/{esc(latest['slug'])}.html">
      <span class="feature-kicker">Latest issue · #{esc(str(latest.get('number','')))} · {esc(latest.get('week_of',''))}</span>
      <h2>{esc(latest.get('title',''))}</h2>
      <p>{esc(latest.get('editors_note',''))}</p>
      <span class="feature-go">Read this week →</span>
    </a>"""
        rows = ""
        for i in issues[1:]:
            rows += f"""
      <a class="archive-row" href="issues/{esc(i['slug'])}.html">
        <span class="arch-num">#{esc(str(i.get('number','')))}</span>
        <span class="arch-title">{esc(i.get('title',''))}</span>
        <span class="arch-date">{esc(i.get('week_of',''))}</span>
      </a>"""
        archive = f'<section class="archive"><h3>Past issues</h3>{rows}</section>' if rows else ""
        body = feat + archive
    return f"""{page_head(pub, tagline)}
  <header class="masthead home">
    <span class="mast-name">{esc(pub)}</span>
    <p class="mast-tag">{esc(tagline)}</p>
  </header>
  <main class="home-main">
    {body}
    <footer class="home-foot">
      <p>A weekly read on economics &amp; politics — the facts, then the <em>why</em>,
      with the economic theory (orthodox and heterodox) underneath. New issue every Monday.</p>
    </footer>
  </main>
</body>
</html>"""


def render_all(root: Path, pub: str, tagline: str):
    root = Path(root)
    data_dir = root / "data"
    issues_dir = root / "issues"
    issues_dir.mkdir(exist_ok=True)

    issues = []
    for f in sorted(data_dir.glob("*.json")):
        issue = json.loads(f.read_text())
        (issues_dir / f"{issue['slug']}.html").write_text(render_issue_page(issue, pub, tagline))
        issues.append({
            "slug": issue["slug"],
            "number": issue.get("number"),
            "date": issue.get("date"),
            "week_of": issue.get("week_of"),
            "title": issue.get("title"),
            "editors_note": issue.get("editors_note"),
            "lead_count": len(issue.get("leads", [])),
            "brief_count": len(issue.get("briefs", [])),
        })

    (root / "issues.json").write_text(json.dumps(
        {"publication": pub, "tagline": tagline, "issues": issues}, ensure_ascii=False, indent=2))
    (root / "index.html").write_text(render_index(issues, pub, tagline))


if __name__ == "__main__":
    here = Path(__file__).parent
    idx = json.loads((here / "issues.json").read_text()) if (here / "issues.json").exists() else {}
    pub = idx.get("publication", "The Long Run")
    tag = idx.get("tagline", "Economics & politics, explained.")
    render_all(here, pub, tag)
    print("rendered.")
