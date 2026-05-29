#!/usr/bin/env python3
"""Render *The Long Run* from data/*.json into static HTML + issues.json index.

Usable standalone (re-render everything after editing JSON or templates):
    python3 render.py
"""

import html
import json
import sys
from pathlib import Path

CATEGORIES = ["Brazil", "Europe", "USA", "International", "Technology"]
CAT_ICON = {
    "Brazil": "🇧🇷",
    "Europe": "🇪🇺",
    "USA": "🇺🇸",
    "International": "🌍",
    "Technology": "💻",
}
# Back-compat for any old data that used a single "region" string.
REGION_TO_CATS = {"Brazil": ["Brazil"], "World": ["International"], "Brazil & World": ["Brazil", "International"]}


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def get_cats(article) -> list:
    cats = article.get("categories")
    if not cats:
        cats = REGION_TO_CATS.get(article.get("region", ""), [])
    return [c for c in cats if c in CATEGORIES] or ["International"]


def cats_attr(cats) -> str:
    return " ".join(cats)


def paras(body) -> str:
    if isinstance(body, str):
        body = [body]
    return "\n".join(f"<p>{esc(p)}</p>" for p in (body or []) if p and p.strip())


def cat_tags(cats) -> str:
    return "".join(f'<span class="tag">{CAT_ICON.get(c, "🌍")} {esc(c)}</span>' for c in cats)


def sources_block(sources) -> str:
    if not sources:
        return ""
    items = "".join(
        f'<li><a href="{esc(s.get("url",""))}" target="_blank" rel="noopener">{esc(s.get("title","source"))}</a></li>'
        for s in sources if s.get("url")
    )
    return f'<div class="sources"><span class="sources-label">Sources</span><ul>{items}</ul></div>' if items else ""


def theory_box(lens) -> str:
    if not lens:
        return ""
    concept = esc(lens.get("concept", "The theory underneath"))
    rows = ""
    if lens.get("orthodox"):
        rows += f'<div class="lens-row"><span class="lens-name">The mainstream view</span><p>{esc(lens["orthodox"])}</p></div>'
    if lens.get("heterodox"):
        rows += f'<div class="lens-row"><span class="lens-name">The heterodox view</span><p>{esc(lens["heterodox"])}</p></div>'
    takeaway = f'<p class="lens-takeaway"><strong>Where we land:</strong> {esc(lens["takeaway"])}</p>' if lens.get("takeaway") else ""
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
    cats = get_cats(a)
    return f"""
  <article class="lead" data-cats="{cats_attr(cats)}">
    <div class="tag-row">{cat_tags(cats)}</div>
    <h2>{esc(a.get("headline",""))}</h2>
    <p class="dek">{esc(a.get("dek",""))}</p>
    <div class="body">{paras(a.get("body"))}</div>
    {why_box(a.get("why_it_matters"))}
    {theory_box(a.get("theory_lens"))}
    {sources_block(a.get("sources"))}
  </article>"""


def brief_html(a) -> str:
    cats = get_cats(a)
    concept = f'<span class="concept">The idea: {esc(a["concept"])}</span>' if a.get("concept") else ""
    return f"""
  <article class="brief" data-cats="{cats_attr(cats)}">
    <div class="brief-head"><div class="tag-row">{cat_tags(cats)}</div>{concept}</div>
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
    return f'<section class="glossary"><h3>Plain-English glossary</h3><dl>{items}</dl></section>' if items else ""


def pills_bar() -> str:
    btns = '<button class="pill active" data-cat="all">All</button>'
    btns += "".join(
        f'<button class="pill" data-cat="{c}">{CAT_ICON[c]} {c}</button>' for c in CATEGORIES
    )
    return f'<nav class="pills" id="pills" aria-label="Filter by topic">{btns}</nav>'


ISSUE_FILTER_JS = """
<script>
(function(){
  var pills = Array.prototype.slice.call(document.querySelectorAll('#pills .pill'));
  var arts = Array.prototype.slice.call(document.querySelectorAll('[data-cats]'));
  var briefsSection = document.getElementById('briefs-section');
  function catsOf(el){ return el.getAttribute('data-cats').split(' ').filter(Boolean); }
  pills.forEach(function(p){
    var cat = p.getAttribute('data-cat');
    if(cat === 'all') return;
    var n = arts.filter(function(a){ return catsOf(a).indexOf(cat) > -1; }).length;
    if(n === 0){ p.disabled = true; p.classList.add('empty'); }
  });
  function apply(cat){
    arts.forEach(function(a){
      var show = cat === 'all' || catsOf(a).indexOf(cat) > -1;
      a.style.display = show ? '' : 'none';
    });
    if(briefsSection){
      var anyBrief = arts.some(function(a){
        return a.classList.contains('brief') && a.style.display !== 'none';
      });
      briefsSection.querySelector('.section-rule').style.display = anyBrief ? '' : 'none';
    }
    pills.forEach(function(p){ p.classList.toggle('active', p.getAttribute('data-cat') === cat); });
  }
  pills.forEach(function(p){
    p.addEventListener('click', function(){ if(!p.disabled) apply(p.getAttribute('data-cat')); });
  });
})();
</script>"""


HOME_FILTER_JS = """
<script>
(function(){
  var pills = Array.prototype.slice.call(document.querySelectorAll('#pills .pill'));
  var rows = Array.prototype.slice.call(document.querySelectorAll('[data-cats]'));
  function catsOf(el){ return el.getAttribute('data-cats').split(' ').filter(Boolean); }
  pills.forEach(function(p){
    var cat = p.getAttribute('data-cat');
    if(cat === 'all') return;
    var n = rows.filter(function(r){ return catsOf(r).indexOf(cat) > -1; }).length;
    if(n === 0){ p.disabled = true; p.classList.add('empty'); }
  });
  function apply(cat){
    rows.forEach(function(r){
      var show = cat === 'all' || catsOf(r).indexOf(cat) > -1;
      r.style.display = show ? '' : 'none';
    });
    pills.forEach(function(p){ p.classList.toggle('active', p.getAttribute('data-cat') === cat); });
  }
  pills.forEach(function(p){
    p.addEventListener('click', function(){ if(!p.disabled) apply(p.getAttribute('data-cat')); });
  });
})();
</script>"""


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
    briefs_section = (
        f'<section class="briefs" id="briefs-section"><h2 class="section-rule">Also this week</h2>'
        f'<div class="brief-grid">{briefs}</div></section>'
        if briefs else ""
    )
    title = f'{esc(issue.get("title") or pub)} · {pub} #{issue.get("number","")}'
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
    {pills_bar()}
    {leads}
    {briefs_section}
    {glossary_html(issue.get("glossary"))}
    <footer class="issue-foot">
      <a href="../index.html">← All issues</a>
      <span>{esc(pub)} · explained, not summarised</span>
    </footer>
  </main>
  {ISSUE_FILTER_JS}
</body>
</html>"""


def render_index(issues, pub, tagline) -> str:
    issues = sorted(issues, key=lambda i: i["slug"], reverse=True)
    if not issues:
        body = '<p class="empty">First issue lands soon.</p>'
    else:
        latest = issues[0]
        feat = f"""
    <a class="feature" href="issues/{esc(latest['slug'])}.html" data-cats="{cats_attr(latest.get('categories', []))}">
      <span class="feature-kicker">Latest issue · #{esc(str(latest.get('number','')))} · {esc(latest.get('week_of',''))}</span>
      <h2>{esc(latest.get('title',''))}</h2>
      <p>{esc(latest.get('editors_note',''))}</p>
      <span class="feature-go">Read this week →</span>
    </a>"""
        rows = ""
        for i in issues[1:]:
            rows += f"""
      <a class="archive-row" href="issues/{esc(i['slug'])}.html" data-cats="{cats_attr(i.get('categories', []))}">
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
    {pills_bar()}
    {body}
    <footer class="home-foot">
      <p>A weekly read on economics, politics and technology. The facts, then the
      <em>why</em>, with the economic theory (orthodox and heterodox) underneath.
      New issue every Monday.</p>
    </footer>
  </main>
  {HOME_FILTER_JS}
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
        cats = []
        for a in issue.get("leads", []) + issue.get("briefs", []):
            for c in get_cats(a):
                if c not in cats:
                    cats.append(c)
        issues.append({
            "slug": issue["slug"],
            "number": issue.get("number"),
            "date": issue.get("date"),
            "week_of": issue.get("week_of"),
            "title": issue.get("title"),
            "editors_note": issue.get("editors_note"),
            "categories": [c for c in CATEGORIES if c in cats],
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
    tag = idx.get("tagline", "Economics, politics & technology, explained.")
    render_all(here, pub, tag)
    print("rendered.")
