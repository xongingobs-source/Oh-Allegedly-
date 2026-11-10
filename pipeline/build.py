"""Static site builder: content/*.json  →  _site/ (plain HTML, deploy anywhere)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .writer import slugify
from .youtube import fmt_ts, parse_time


def load_articles(folder: Path) -> list[dict]:
    arts = []
    for f in sorted(folder.glob("*.json")):
        try:
            a = json.loads(f.read_text())
            a.setdefault("slug", f.stem)
            arts.append(a)
        except Exception as e:  # noqa: BLE001
            print(f"[build] skipping bad file {f.name}: {e}")
    arts.sort(key=lambda a: a.get("published") or "", reverse=True)
    return arts


def ago(iso: str) -> str:
    delta = datetime.now(timezone.utc) - parse_time(iso)
    s = int(delta.total_seconds())
    if s < 60: return "just now"
    if s < 3600: return f"{s // 60} min ago"
    if s < 86400: return f"{s // 3600} hr ago"
    if s < 86400 * 7: return f"{s // 86400} d ago"
    return parse_time(iso).strftime("%d %b %Y")


def build_site(cfg: dict, root: Path, out: Path | None = None):
    out = out or root / "_site"
    site = cfg["site"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(root / "static", out / "static")

    env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape(["html", "xml"]))
    env.filters["ago"] = ago
    env.filters["ts"] = fmt_ts
    env.filters["slug"] = slugify
    env.filters["nice_date"] = lambda iso: parse_time(iso).strftime("%A %d %B %Y, %H:%M UTC")

    articles = load_articles(root / "content" / "articles")
    now = datetime.now(timezone.utc)
    win = site.get("breaking_window_hours", 6) * 3600
    md = markdown.Markdown(extensions=["extra", "sane_lists"])
    for a in articles:
        a["fresh"] = (now - parse_time(a["published"])).total_seconds() < win
        a["breaking"] = a.get("is_breaking") and a["fresh"]
        a["body_html"] = md.reset().convert(a.get("body_markdown", ""))
        a["section_slug"] = slugify(a.get("category", "news"))

    live_path = root / "data" / "live.json"
    live = json.loads(live_path.read_text()) if live_path.exists() else {"streams": []}
    digests = load_articles(root / "content" / "digests") if (root / "content" / "digests").exists() else []
    digests.sort(key=lambda d: d.get("date", ""), reverse=True)
    by_slug = {a["slug"]: a for a in articles}

    sections = []
    for cat in cfg["newsroom"]["categories"]:
        items = [a for a in articles if a.get("category") == cat]
        sections.append({"name": cat, "slug": slugify(cat), "items": items})

    common = dict(site=site, sections=sections, live=live["streams"], now=now,
                  ticker=[a for a in articles[:12]], build_time=now.isoformat())

    def render(tpl, path, depth, **ctx):
        dest = out / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(tpl).render(root="../" * depth, **common, **ctx))

    # Home
    render("index.html", "index.html", 0, articles=articles[: site.get("stories_on_homepage", 30)],
           digest=digests[0] if digests else None, by_slug=by_slug)

    # Stories
    for a in articles:
        related = [b for b in articles if b is not a and (b.get("category") == a.get("category")
                   or set(b.get("tags", [])) & set(a.get("tags", [])))][:4]
        render("article.html", f"story/{a['slug']}/index.html", 2, a=a, related=related)

    # Sections
    for s in sections:
        render("section.html", f"section/{s['slug']}/index.html", 2, section=s)

    # Daily briefing archive
    render("briefing.html", "briefing/index.html", 1, digests=digests[:30], by_slug=by_slug)

    # Machine-readable outputs
    (out / "live.json").write_text(json.dumps(live))
    (out / "search.json").write_text(json.dumps([
        {"s": a["slug"], "h": a["headline"], "d": a["dek"], "c": a.get("category"), "t": a.get("tags", [])}
        for a in articles]))
    base = site["base_url"].rstrip("/")
    items = "".join(
        f"<item><title>{escape(a['headline'])}</title><link>{base}/story/{a['slug']}/</link>"
        f"<guid>{base}/story/{a['slug']}/</guid><pubDate>{format_datetime(parse_time(a['published']))}</pubDate>"
        f"<description>{escape(a['dek'])}</description></item>" for a in articles[:50])
    (out / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(site["name"])}</title>'
        f"<link>{base}/</link><description>{escape(site['tagline'])}</description>{items}</channel></rss>")
    urls = [f"{base}/"] + [f"{base}/story/{a['slug']}/" for a in articles] + [f"{base}/section/{s['slug']}/" for s in sections]
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    (out / ".nojekyll").write_text("")
    print(f"[build] {len(articles)} stories → {out}")
