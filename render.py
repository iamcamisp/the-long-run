#!/usr/bin/env python3
"""Render *The Long Run* from data/*.json into static HTML + issues.json index.

Bilingual: every issue carries English and Brazilian Portuguese content. Each text
node is emitted in both languages; CSS shows the active one and a floating EN/PT pill
toggles it (saved in localStorage). Standalone:

    python3 render.py
"""

import html
import json
import re
import sys
from pathlib import Path

CATEGORIES = ["Brazil", "Europe", "USA", "International", "Technology"]
CAT_ICON = {"Brazil": "🇧🇷", "Europe": "🇪🇺", "USA": "🇺🇸", "International": "🌍", "Technology": "💻"}
CAT_PT = {"Brazil": "Brasil", "Europe": "Europa", "USA": "EUA", "International": "Internacional", "Technology": "Tecnologia"}
CONTENT_KEYS = ("title", "editors_note", "leads", "briefs", "glossary")
REGION_TO_CATS = {"Brazil": ["Brazil"], "World": ["International"], "Brazil & World": ["Brazil", "International"]}

MONTHS_PT = {
    "January": "janeiro", "February": "fevereiro", "March": "março", "April": "abril",
    "May": "maio", "June": "junho", "July": "julho", "August": "agosto",
    "September": "setembro", "October": "outubro", "November": "novembro", "December": "dezembro",
    "Jan": "jan", "Feb": "fev", "Mar": "mar", "Apr": "abr", "Jun": "jun", "Jul": "jul",
    "Aug": "ago", "Sep": "set", "Oct": "out", "Nov": "nov", "Dec": "dez",
}

# Static UI strings: (en, pt)
UI = {
    "all": ("All", "Tudo"),
    "why": ("Why it matters", "Por que importa"),
    "theory": ("The theory underneath", "A teoria por trás"),
    "mainstream": ("The mainstream view", "A visão ortodoxa"),
    "heterodox": ("The heterodox view", "A visão heterodoxa"),
    "land": ("Where we land:", "Onde ficamos:"),
    "sources": ("Sources", "Fontes"),
    "also": ("Also this week", "Também esta semana"),
    "glossary": ("Plain-English glossary", "Glossário"),
    "all_issues": ("← All issues", "← Todas as edições"),
    "issue": ("Issue", "Edição"),
    "week_of": ("Week of", "Semana de"),
    "idea": ("The idea:", "A ideia:"),
    "latest": ("Latest issue", "Última edição"),
    "read": ("Read this week →", "Ler esta edição →"),
    "past": ("Past issues", "Edições anteriores"),
    "foot_issue": ("explained, not summarised", "explicado, não resumido"),
    "home_blurb": (
        "A weekly read on economics, politics and technology. The facts, then the why, "
        "with the economic theory (orthodox and heterodox) underneath. New issue every Monday.",
        "Uma leitura semanal sobre economia, política e tecnologia. Os fatos, depois o porquê, "
        "com a teoria econômica (ortodoxa e heterodoxa) por trás. Edição nova toda segunda.",
    ),
}


def esc(s) -> str:
    return html.escape(s or "", quote=True)


def bi(en, pt=None) -> str:
    """Inline bilingual span pair. Falls back to EN text if PT missing."""
    en_t = esc(en or "")
    pt_t = esc(pt if (pt is not None and str(pt).strip()) else en or "")
    return f'<span data-lang="en">{en_t}</span><span data-lang="pt">{pt_t}</span>'


def ui(key) -> str:
    en, pt = UI[key]
    return bi(en, pt)


def localize_date(label: str, lang: str) -> str:
    if lang != "pt" or not label:
        return label
    out = label
    for en_m, pt_m in MONTHS_PT.items():
        out = re.sub(rf"\b{en_m}\b", pt_m, out)
    return out


def get_cats(article) -> list:
    cats = article.get("categories") or REGION_TO_CATS.get(article.get("region", ""), [])
    return [c for c in cats if c in CATEGORIES] or ["International"]


def cat_tags(cats) -> str:
    return "".join(
        f'<span class="tag">{CAT_ICON.get(c, "🌍")} {bi(c, CAT_PT.get(c, c))}</span>' for c in cats
    )


def bi_paras(en_list, pt_list) -> str:
    en_list = en_list or []
    pt_list = pt_list or []
    out = []
    for i, e in enumerate(en_list):
        if not (e and str(e).strip()):
            continue
        p = pt_list[i] if i < len(pt_list) else e
        out.append(f"<p>{bi(e, p)}</p>")
    return "\n".join(out)


def sources_block(sources) -> str:
    if not sources:
        return ""
    items = "".join(
        f'<li><a href="{esc(s.get("url",""))}" target="_blank" rel="noopener">{esc(s.get("title","source"))}</a></li>'
        for s in sources if s.get("url")
    )
    return f'<div class="sources"><span class="sources-label">{ui("sources")}</span><ul>{items}</ul></div>' if items else ""


def theory_box(en_lens, pt_lens) -> str:
    en_lens = en_lens or {}
    pt_lens = pt_lens or {}
    if not en_lens:
        return ""
    rows = ""
    if en_lens.get("orthodox"):
        rows += f'<div class="lens-row"><span class="lens-name">{ui("mainstream")}</span><p>{bi(en_lens.get("orthodox"), pt_lens.get("orthodox"))}</p></div>'
    if en_lens.get("heterodox"):
        rows += f'<div class="lens-row"><span class="lens-name">{ui("heterodox")}</span><p>{bi(en_lens.get("heterodox"), pt_lens.get("heterodox"))}</p></div>'
    takeaway = ""
    if en_lens.get("takeaway"):
        takeaway = f'<p class="lens-takeaway"><strong>{ui("land")}</strong> {bi(en_lens.get("takeaway"), pt_lens.get("takeaway"))}</p>'
    return f"""
    <aside class="theory">
      <span class="theory-kicker">{ui("theory")}</span>
      <h4>{bi(en_lens.get("concept"), pt_lens.get("concept"))}</h4>
      {rows}
      {takeaway}
    </aside>"""


def why_box(en_text, pt_text) -> str:
    if not en_text:
        return ""
    return f'<div class="why"><span class="why-label">{ui("why")}</span><p>{bi(en_text, pt_text)}</p></div>'


def lead_html(en_a, pt_a) -> str:
    cats = get_cats(en_a)
    return f"""
  <article class="lead" data-cats="{' '.join(cats)}">
    <div class="tag-row">{cat_tags(cats)}</div>
    <h2>{bi(en_a.get("headline"), pt_a.get("headline"))}</h2>
    <p class="dek">{bi(en_a.get("dek"), pt_a.get("dek"))}</p>
    <div class="body">{bi_paras(en_a.get("body"), pt_a.get("body"))}</div>
    {why_box(en_a.get("why_it_matters"), pt_a.get("why_it_matters"))}
    {theory_box(en_a.get("theory_lens"), pt_a.get("theory_lens"))}
    {sources_block(en_a.get("sources"))}
  </article>"""


def brief_html(en_a, pt_a) -> str:
    cats = get_cats(en_a)
    concept = ""
    if en_a.get("concept"):
        concept = f'<span class="concept">{ui("idea")} {bi(en_a.get("concept"), pt_a.get("concept"))}</span>'
    return f"""
  <article class="brief" data-cats="{' '.join(cats)}">
    <div class="brief-head"><div class="tag-row">{cat_tags(cats)}</div>{concept}</div>
    <h3>{bi(en_a.get("headline"), pt_a.get("headline"))}</h3>
    <div class="body">{bi_paras(en_a.get("body"), pt_a.get("body"))}</div>
    {why_box(en_a.get("why_it_matters"), pt_a.get("why_it_matters"))}
    {sources_block(en_a.get("sources"))}
  </article>"""


def glossary_html(en_g, pt_g) -> str:
    en_g = en_g or []
    pt_g = pt_g or []
    items = ""
    for i, g in enumerate(en_g):
        if not g.get("term"):
            continue
        p = pt_g[i] if i < len(pt_g) else g
        items += f'<div class="gloss-item"><dt>{bi(g.get("term"), p.get("term"))}</dt><dd>{bi(g.get("plain"), p.get("plain"))}</dd></div>'
    return f'<section class="glossary"><h3>{ui("glossary")}</h3><dl>{items}</dl></section>' if items else ""


def pills_bar() -> str:
    btns = f'<button class="pill active" data-cat="all">{ui("all")}</button>'
    btns += "".join(
        f'<button class="pill" data-cat="{c}">{CAT_ICON[c]} {bi(c, CAT_PT[c])}</button>' for c in CATEGORIES
    )
    return f'<nav class="pills" id="pills" aria-label="Filter by topic">{btns}</nav>'


LANG_SWITCH = """
  <div class="lang-switch" id="lang-switch" aria-label="Language">
    <button data-set="en">EN</button><button data-set="pt">PT</button>
  </div>"""

LANG_JS = """
<script>
(function(){
  var saved = localStorage.getItem('lr-lang') || 'en';
  var btns = Array.prototype.slice.call(document.querySelectorAll('#lang-switch button'));
  function set(l){
    document.documentElement.setAttribute('lang', l);
    localStorage.setItem('lr-lang', l);
    btns.forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-set') === l); });
  }
  btns.forEach(function(b){ b.addEventListener('click', function(){ set(b.getAttribute('data-set')); }); });
  set(saved);
})();
</script>"""

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
    if(arts.filter(function(a){ return catsOf(a).indexOf(cat) > -1; }).length === 0){
      p.disabled = true; p.classList.add('empty');
    }
  });
  function apply(cat){
    arts.forEach(function(a){
      a.style.display = (cat === 'all' || catsOf(a).indexOf(cat) > -1) ? '' : 'none';
    });
    if(briefsSection){
      var any = arts.some(function(a){ return a.classList.contains('brief') && a.style.display !== 'none'; });
      briefsSection.querySelector('.section-rule').style.display = any ? '' : 'none';
    }
    pills.forEach(function(p){ p.classList.toggle('active', p.getAttribute('data-cat') === cat); });
  }
  pills.forEach(function(p){ p.addEventListener('click', function(){ if(!p.disabled) apply(p.getAttribute('data-cat')); }); });
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
    if(rows.filter(function(r){ return catsOf(r).indexOf(cat) > -1; }).length === 0){
      p.disabled = true; p.classList.add('empty');
    }
  });
  function apply(cat){
    rows.forEach(function(r){ r.style.display = (cat === 'all' || catsOf(r).indexOf(cat) > -1) ? '' : 'none'; });
    pills.forEach(function(p){ p.classList.toggle('active', p.getAttribute('data-cat') === cat); });
  }
  pills.forEach(function(p){ p.addEventListener('click', function(){ if(!p.disabled) apply(p.getAttribute('data-cat')); }); });
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


def split_content(issue):
    """Return (en, pt, tagline_en, tagline_pt) handling new and legacy data."""
    tag = issue.get("tagline")
    if isinstance(tag, dict):
        tag_en, tag_pt = tag.get("en", ""), tag.get("pt", tag.get("en", ""))
    else:
        tag_en = tag_pt = tag or ""
    if "content" in issue:
        c = issue["content"]
        return c.get("en", {}), c.get("pt", c.get("en", {})), tag_en, tag_pt
    flat = {k: issue.get(k) for k in CONTENT_KEYS}
    return flat, flat, tag_en, tag_pt


def render_issue_page(issue, pub) -> str:
    en, pt, tag_en, tag_pt = split_content(issue)
    en_leads, pt_leads = en.get("leads", []), pt.get("leads", [])
    en_briefs, pt_briefs = en.get("briefs", []), pt.get("briefs", [])

    leads = "\n".join(lead_html(e, pt_leads[i] if i < len(pt_leads) else {}) for i, e in enumerate(en_leads))
    briefs = "".join(brief_html(e, pt_briefs[i] if i < len(pt_briefs) else {}) for i, e in enumerate(en_briefs))
    briefs_section = (
        f'<section class="briefs" id="briefs-section"><h2 class="section-rule">{ui("also")}</h2>'
        f'<div class="brief-grid">{briefs}</div></section>'
        if briefs else ""
    )
    title = f'{esc(en.get("title") or pub)} · {pub} #{issue.get("number","")}'
    desc = (en.get("editors_note") or tag_en)[:200]
    week_en = esc(issue.get("week_of", ""))
    week_pt = esc(localize_date(issue.get("week_of", ""), "pt"))
    return f"""{page_head(title, desc, css="../style.css")}
  {LANG_SWITCH}
  <header class="masthead">
    <a class="mast-name" href="../index.html">{esc(pub)}</a>
    <p class="mast-tag">{bi(tag_en, tag_pt)}</p>
  </header>
  <main class="issue">
    <div class="issue-meta">
      <span>{ui("issue")} #{esc(str(issue.get("number","")))}</span>
      <span>{ui("week_of")} <span data-lang="en">{week_en}</span><span data-lang="pt">{week_pt}</span></span>
    </div>
    <h1 class="issue-title">{bi(en.get("title"), pt.get("title"))}</h1>
    <p class="editors-note">{bi(en.get("editors_note"), pt.get("editors_note"))}</p>
    {pills_bar()}
    {leads}
    {briefs_section}
    {glossary_html(en.get("glossary"), pt.get("glossary"))}
    <footer class="issue-foot">
      <a href="../index.html">{ui("all_issues")}</a>
      <span>{esc(pub)} · {ui("foot_issue")}</span>
    </footer>
  </main>
  {ISSUE_FILTER_JS}
  {LANG_JS}
</body>
</html>"""


def render_index(issues, pub, tag_en, tag_pt) -> str:
    issues = sorted(issues, key=lambda i: i["slug"], reverse=True)
    if not issues:
        body = '<p class="empty">First issue lands soon.</p>'
    else:
        l = issues[0]
        feat = f"""
    <a class="feature" href="issues/{esc(l['slug'])}.html" data-cats="{' '.join(l.get('categories', []))}">
      <span class="feature-kicker">{ui("latest")} · #{esc(str(l.get('number','')))} · <span data-lang="en">{esc(l.get('week_of',''))}</span><span data-lang="pt">{esc(localize_date(l.get('week_of',''),'pt'))}</span></span>
      <h2>{bi(l.get('title_en'), l.get('title_pt'))}</h2>
      <p>{bi(l.get('note_en'), l.get('note_pt'))}</p>
      <span class="feature-go">{ui("read")}</span>
    </a>"""
        rows = ""
        for i in issues[1:]:
            rows += f"""
      <a class="archive-row" href="issues/{esc(i['slug'])}.html" data-cats="{' '.join(i.get('categories', []))}">
        <span class="arch-num">#{esc(str(i.get('number','')))}</span>
        <span class="arch-title">{bi(i.get('title_en'), i.get('title_pt'))}</span>
        <span class="arch-date"><span data-lang="en">{esc(i.get('week_of',''))}</span><span data-lang="pt">{esc(localize_date(i.get('week_of',''),'pt'))}</span></span>
      </a>"""
        archive = f'<section class="archive"><h3>{ui("past")}</h3>{rows}</section>' if rows else ""
        body = feat + archive
    return f"""{page_head(pub, tag_en)}
  {LANG_SWITCH}
  <header class="masthead home">
    <span class="mast-name">{esc(pub)}</span>
    <p class="mast-tag">{bi(tag_en, tag_pt)}</p>
  </header>
  <main class="home-main">
    {pills_bar()}
    {body}
    <footer class="home-foot"><p>{ui("home_blurb")}</p></footer>
  </main>
  {HOME_FILTER_JS}
  {LANG_JS}
</body>
</html>"""


def render_all(root: Path, pub: str, tagline):
    root = Path(root)
    data_dir = root / "data"
    issues_dir = root / "issues"
    issues_dir.mkdir(exist_ok=True)
    tag_en = tagline.get("en", "") if isinstance(tagline, dict) else (tagline or "")
    tag_pt = tagline.get("pt", tag_en) if isinstance(tagline, dict) else tag_en

    index = []
    for f in sorted(data_dir.glob("*.json")):
        issue = json.loads(f.read_text())
        (issues_dir / f"{issue['slug']}.html").write_text(render_issue_page(issue, pub))
        en, pt, _, _ = split_content(issue)
        cats = []
        for a in (en.get("leads", []) + en.get("briefs", [])):
            for c in get_cats(a):
                if c not in cats:
                    cats.append(c)
        index.append({
            "slug": issue["slug"],
            "number": issue.get("number"),
            "date": issue.get("date"),
            "week_of": issue.get("week_of"),
            "title_en": en.get("title"),
            "title_pt": pt.get("title"),
            "note_en": en.get("editors_note"),
            "note_pt": pt.get("editors_note"),
            "categories": [c for c in CATEGORIES if c in cats],
            "lead_count": len(en.get("leads", [])),
            "brief_count": len(en.get("briefs", [])),
        })

    (root / "issues.json").write_text(json.dumps(
        {"publication": pub, "tagline": {"en": tag_en, "pt": tag_pt}, "issues": index}, ensure_ascii=False, indent=2))
    (root / "index.html").write_text(render_index(index, pub, tag_en, tag_pt))


if __name__ == "__main__":
    here = Path(__file__).parent
    idx = json.loads((here / "issues.json").read_text()) if (here / "issues.json").exists() else {}
    pub = idx.get("publication", "The Long Run")
    tag = idx.get("tagline", {"en": "Economics, politics & technology, explained.", "pt": "Economia, política e tecnologia, explicadas."})
    render_all(here, pub, tag)
    print("rendered.")
