#!/usr/bin/env python3
"""Generate static HTML article pages for Malaysia Encyclopedia from Supabase."""

import os
import json
import urllib.request
import urllib.parse
import urllib.error
import html
import re
from pathlib import Path
from datetime import date

# Config — keys loaded from environment (source ~/.openclaw/.env before running)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://yitmabzsxfgbchhhjjef.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
BASE_URL = "https://malaysia-encyclopedia.vercel.app"
SITE_NAME = "馬來西亞百科"
REPO_DIR = Path(__file__).resolve().parent
TODAY = date.today().isoformat()  # was hardcoded "2026-06-01" from the original one-off run; fixed 2026-07-26 so reruns stamp the real generation date

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_SECRET_KEY env var not set. Run: source ~/.openclaw/.env")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

def fetch_articles(lang: str) -> list:
    """Fetch published MY articles for given lang."""
    params = urllib.parse.urlencode({
        "region": "eq.MY",
        "status": "eq.published",
        "lang": f"eq.{lang}",
        "select": "slug,title,body_html,faqs,verification_sources,lang,word_count,created_at",
        "limit": "300",
    })
    url = f"{SUPABASE_URL}/rest/v1/insights?{params}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data
    except Exception as e:
        print(f"  Error fetching lang={lang}: {e}")
        return []

def get_faq_value(faq: dict, key: str) -> str:
    """Safely get faq question or answer using multiple key names."""
    if key == "question":
        return faq.get("question") or faq.get("q") or ""
    else:
        return faq.get("answer") or faq.get("a") or ""

def build_schema_json(article: dict, url_path: str, lang: str) -> str:
    """Build JSON-LD schema block."""
    slug = article["slug"]
    title = article.get("title") or slug
    verification_sources = article.get("verification_sources") or []
    faqs = article.get("faqs") or []

    # Build isBasedOn
    is_based_on = []
    if isinstance(verification_sources, list):
        for src in verification_sources[:5]:
            if isinstance(src, dict):
                src_url = src.get("url") or src.get("link") or ""
                src_name = src.get("name") or src.get("title") or src_url
                if src_url:
                    is_based_on.append({"@type": "WebPage", "url": src_url, "name": src_name})
            elif isinstance(src, str) and src.startswith("http"):
                is_based_on.append({"@type": "WebPage", "url": src})

    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "datePublished": TODAY,
        "dateModified": TODAY,
        "inLanguage": lang,
        "author": {"@type": "Organization", "name": SITE_NAME},
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": BASE_URL,
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": f"{BASE_URL}/{url_path}/",
        },
    }
    if is_based_on:
        article_schema["isBasedOn"] = is_based_on

    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "首頁",
                "item": BASE_URL,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": SITE_NAME,
                "item": BASE_URL,
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": title,
                "item": f"{BASE_URL}/{url_path}/",
            },
        ],
    }

    schemas = [article_schema, breadcrumb_schema]

    if faqs and isinstance(faqs, list):
        faq_entities = []
        for faq in faqs:
            if not isinstance(faq, dict):
                continue
            q = get_faq_value(faq, "question")
            a = get_faq_value(faq, "answer")
            if q and a:
                faq_entities.append({
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": a},
                })
        if faq_entities:
            schemas.append({
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": faq_entities,
            })

    parts = "\n".join(
        f'  <script type="application/ld+json">\n  {json.dumps(s, ensure_ascii=False, indent=2)}\n  </script>'
        for s in schemas
    )
    return parts

def build_faq_html(faqs: list) -> str:
    """Build FAQ section HTML."""
    if not faqs or not isinstance(faqs, list):
        return ""
    items = []
    for faq in faqs:
        if not isinstance(faq, dict):
            continue
        q = get_faq_value(faq, "question")
        a = get_faq_value(faq, "answer")
        if q and a:
            items.append(
                f'    <div class="faq-item">\n'
                f'      <h3 class="faq-q">{html.escape(q)}</h3>\n'
                f'      <div class="faq-a">{html.escape(a)}</div>\n'
                f'    </div>'
            )
    if not items:
        return ""
    inner = "\n".join(items)
    return f'  <section class="faq-section">\n    <h2>常見問題</h2>\n{inner}\n  </section>\n'

def build_html(article: dict, url_path: str, lang: str) -> str:
    """Build full HTML page for an article."""
    slug = article["slug"]
    title = article.get("title") or slug
    body_html = article.get("body_html") or f"<p>{html.escape(title)}</p>"
    faqs = article.get("faqs") or []

    schema_block = build_schema_json(article, url_path, lang)
    faq_html = build_faq_html(faqs)

    # Lang attribute
    lang_attr_map = {"zh": "zh-Hant", "en": "en", "ms": "ms"}
    lang_attr = lang_attr_map.get(lang, "zh-Hant")

    encoded_slug = urllib.parse.quote(slug, safe='')

    return f"""<!DOCTYPE html>
<html lang="{lang_attr}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)} — {SITE_NAME}</title>
  <meta name="description" content="{html.escape(title[:150])}">
  <link rel="llms-txt" href="{BASE_URL}/llms.txt">
  <link rel="canonical" href="{BASE_URL}/{url_path}/">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
{schema_block}
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Source Sans 3', 'Noto Serif TC', sans-serif;
      background: #fafaf7;
      color: #1a1a1a;
      line-height: 1.8;
    }}
    header {{
      background: linear-gradient(135deg, #cc0001 0%, #f4a620 100%);
      color: #fff;
      padding: 2rem;
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }}
    header h1 {{
      font-family: 'Noto Serif TC', serif;
      font-size: 1.5rem;
      font-weight: 700;
    }}
    header a {{
      color: rgba(255,255,255,0.85);
      text-decoration: none;
      font-size: 0.9rem;
    }}
    header a:hover {{ color: #fff; text-decoration: underline; }}
    .breadcrumb {{
      background: #1a1a1a;
      padding: 0.6rem 2rem;
      font-size: 0.85rem;
      color: #aaa;
    }}
    .breadcrumb a {{ color: #f4a620; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    .breadcrumb span {{ margin: 0 0.4rem; }}
    main {{
      max-width: 860px;
      margin: 2.5rem auto;
      padding: 0 1.5rem;
    }}
    h1.article-title {{
      font-family: 'Noto Serif TC', serif;
      font-size: 2rem;
      font-weight: 700;
      margin-bottom: 1.5rem;
      color: #1a1a1a;
      border-bottom: 3px solid #cc0001;
      padding-bottom: 0.75rem;
    }}
    .article-body h2 {{
      font-family: 'Noto Serif TC', serif;
      font-size: 1.35rem;
      font-weight: 700;
      margin: 2rem 0 1rem;
      color: #cc0001;
    }}
    .article-body h3 {{
      font-size: 1.1rem;
      font-weight: 600;
      margin: 1.5rem 0 0.75rem;
    }}
    .article-body p {{
      margin-bottom: 1rem;
      color: #333;
    }}
    .article-body ul, .article-body ol {{
      margin: 1rem 0 1rem 1.5rem;
      color: #333;
    }}
    .article-body li {{ margin-bottom: 0.4rem; }}
    .article-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1.5rem 0;
      font-size: 0.9rem;
    }}
    .article-body table th, .article-body table td {{
      border: 1px solid #ddd;
      padding: 0.6rem 0.8rem;
      text-align: left;
    }}
    .article-body table th {{ background: #f4a620; color: #fff; }}
    .faq-section {{
      margin-top: 3rem;
      border-top: 3px solid #cc0001;
      padding-top: 1.5rem;
    }}
    .faq-section h2 {{
      font-family: 'Noto Serif TC', serif;
      font-size: 1.35rem;
      font-weight: 700;
      margin-bottom: 1.5rem;
      color: #1a1a1a;
    }}
    .faq-item {{
      background: #fff;
      border-left: 4px solid #f4a620;
      border-radius: 0 8px 8px 0;
      padding: 1rem 1.25rem;
      margin-bottom: 1rem;
      box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    }}
    .faq-q {{
      font-size: 1rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
      color: #1a1a1a;
    }}
    .faq-a {{
      font-size: 0.92rem;
      color: #444;
      line-height: 1.7;
    }}
    footer {{
      background: #1a1a1a;
      color: #aaa;
      padding: 2rem;
      text-align: center;
      font-size: 0.85rem;
      margin-top: 4rem;
    }}
    footer a {{ color: #f4a620; text-decoration: none; }}
  </style>
</head>
<body>
<header>
  <div>
    <a href="{BASE_URL}/">← 返回首頁</a><br>
    <h1>🇲🇾 {SITE_NAME}</h1>
  </div>
</header>
<nav class="breadcrumb">
  <a href="{BASE_URL}/">首頁</a>
  <span>›</span>
  <a href="{BASE_URL}/">{SITE_NAME}</a>
  <span>›</span>
  {html.escape(title)}
</nav>
<main>
  <h1 class="article-title">{html.escape(title)}</h1>
  <div class="article-body">
    {body_html}
  </div>
{faq_html}</main>
<footer>
  <p>
    <strong>{SITE_NAME} (Malaysia Encyclopedia)</strong><br>
    <a href="{BASE_URL}/llms.txt">llms.txt</a> ·
    深度解析馬來西亞飲食文化、日本料理在地化、娛樂產業與主題樂園<br>
    © 2026 Malaysia Encyclopedia · CC BY 4.0
  </p>
</footer>
<img src="https://client-ai-tracker.inariglobal.workers.dev/malaysia-encyclopedia/pixel.gif?p={encoded_slug}" width="1" height="1" style="display:none" alt="">
</body>
</html>"""

def update_sitemap(url_paths: list) -> None:
    """Update sitemap.xml with all article URLs.

    Merges with any pre-existing sitemap.xml entries instead of replacing
    wholesale: this run only re-fetches insights that are CURRENTLY
    status=published in Supabase, but earlier runs (2026-06-01) generated
    static pages for lang=en/ms insights that have since been unpublished
    in the DB while their static HTML files remain deployed on disk/Vercel.
    A naive overwrite would silently drop ~158 already-indexed URLs from
    discovery. We union instead so this rerun is strictly additive.
    """
    sitemap_path = REPO_DIR / "sitemap.xml"

    existing_paths = set()
    if sitemap_path.exists():
        existing_xml = sitemap_path.read_text(encoding="utf-8")
        for m in re.finditer(r"<loc>" + re.escape(BASE_URL) + r"/([^<]+)/</loc>", existing_xml):
            existing_paths.add(m.group(1))

    merged_paths = existing_paths | set(url_paths)

    urls = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            '  <url>',
            f'    <loc>{BASE_URL}/</loc>',
            '    <changefreq>daily</changefreq>',
            '    <priority>1.0</priority>',
            f'    <lastmod>{TODAY}</lastmod>',
            '  </url>']

    for path in sorted(merged_paths):
        urls += [
            '  <url>',
            f'    <loc>{BASE_URL}/{path}/</loc>',
            '    <changefreq>weekly</changefreq>',
            '    <priority>0.8</priority>',
            f'    <lastmod>{TODAY}</lastmod>',
            '  </url>',
        ]

    urls.append('</urlset>')
    sitemap_path.write_text("\n".join(urls) + "\n", encoding="utf-8")
    print(f"  Sitemap updated: {len(merged_paths)} article URLs ({len(url_paths)} from this run + {len(merged_paths - set(url_paths))} preserved from prior runs)")


_TAG_RE = re.compile(r"<[^>]+>")


def build_feed_xml(feed_items: list) -> str:
    """WP-11 (2026-08-29): malaysia-encyclopedia has never had a feed.xml —
    generate_articles.py only ever wrote sitemap.xml (see update_sitemap()
    above). This is a net-new RSS 2.0 feed, not a fix to an existing one.

    feed_items: list of dicts with keys title/url_path/body_html/created_at,
    collected during main()'s per-article loop (this run's zh/en/ms output
    only — same "this run" scope as url_paths in update_sitemap(), not a
    merge with prior runs, since feed.xml is meant to reflect recent items
    not a full historical index like the sitemap).
    """
    items_xml = ""
    for it in sorted(feed_items, key=lambda x: x.get("created_at") or "", reverse=True)[:30]:
        title_esc = html.escape(it["title"])
        plain_body = _TAG_RE.sub(" ", it.get("body_html") or "")
        desc_esc = html.escape(" ".join(plain_body.split())[:300])
        link = f"{BASE_URL}/{it['url_path']}/"
        pub_date = (it.get("created_at") or "")[:10] or TODAY
        items_xml += f"""    <item>
      <title>{title_esc}</title>
      <link>{link}</link>
      <description>{desc_esc}</description>
      <pubDate>{pub_date}</pubDate>
      <guid>{link}</guid>
    </item>\n"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{SITE_NAME} — Malaysia Encyclopedia</title>
    <link>{BASE_URL}</link>
    <description>深度解析馬來西亞飲食文化、日本料理在地化、娛樂產業與主題樂園</description>
    <language>zh-TW</language>
    <lastBuildDate>{TODAY}</lastBuildDate>
    <atom:link href="{BASE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{items_xml}  </channel>
</rss>"""


def build_atom_xml(feed_items: list) -> str:
    """Build the native Atom document served at /atom.xml."""
    updated = f"{TODAY}T00:00:00Z"
    entries_xml = ""
    for it in sorted(feed_items, key=lambda x: x.get("created_at") or "", reverse=True)[:30]:
        title_esc = html.escape(it["title"])
        plain_body = _TAG_RE.sub(" ", it.get("body_html") or "")
        summary_esc = html.escape(" ".join(plain_body.split())[:300])
        link = f"{BASE_URL}/{it['url_path']}/"
        entries_xml += f"""  <entry>
    <title>{title_esc}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{updated}</updated>
    <summary>{summary_esc}</summary>
  </entry>\n"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{SITE_NAME} — Malaysia Encyclopedia</title>
  <link href="{BASE_URL}/"/>
  <link href="{BASE_URL}/atom.xml" rel="self" type="application/atom+xml"/>
  <id>{BASE_URL}/</id>
  <updated>{updated}</updated>
{entries_xml}</feed>
"""


def main():
    counts = {"zh": 0, "en": 0, "ms": 0}
    all_url_paths = []
    feed_items = []

    for lang in ["zh", "en", "ms"]:
        print(f"\nFetching lang={lang}...")
        articles = fetch_articles(lang)
        print(f"  Got {len(articles)} articles")

        for article in articles:
            slug = article.get("slug")
            if not slug:
                continue

            # Determine URL path based on lang
            # If slug already ends with -<lang> suffix, use slug as-is (no double suffix)
            if lang == "zh" or slug.endswith(f"-{lang}"):
                url_path = slug
            else:
                url_path = f"{slug}-{lang}"

            # Create directory
            page_dir = REPO_DIR / url_path
            page_dir.mkdir(parents=True, exist_ok=True)

            # Generate HTML
            page_html = build_html(article, url_path, lang)
            (page_dir / "index.html").write_text(page_html, encoding="utf-8")

            all_url_paths.append(url_path)
            feed_items.append({
                "title": article.get("title") or slug,
                "url_path": url_path,
                "body_html": article.get("body_html") or "",
                "created_at": article.get("created_at") or "",
            })
            counts[lang] += 1

        print(f"  Generated {counts[lang]} pages for lang={lang}")

    # Update sitemap
    print("\nUpdating sitemap.xml...")
    update_sitemap(all_url_paths)

    # WP-11 (2026-08-29): feed.xml never existed for malaysia-encyclopedia —
    # net-new, generated from this run's articles only (see build_feed_xml
    # docstring for why this doesn't merge with prior runs like the sitemap does).
    print("\nWriting feed.xml, rss.xml and atom.xml...")
    rss_xml = build_feed_xml(feed_items)
    (REPO_DIR / "feed.xml").write_text(rss_xml, encoding="utf-8")
    (REPO_DIR / "rss.xml").write_text(rss_xml, encoding="utf-8")
    (REPO_DIR / "atom.xml").write_text(build_atom_xml(feed_items), encoding="utf-8")
    print(f"  feeds written: {min(len(feed_items), 30)} items")

    total = sum(counts.values())
    print(f"\nDone! Total pages generated: {total}")
    print(f"  zh={counts['zh']}, en={counts['en']}, ms={counts['ms']}")

    # Count subdirs
    subdirs = [d for d in REPO_DIR.iterdir() if d.is_dir() and not d.name.startswith('.')]
    print(f"  Total article subdirectories: {len(subdirs)}")

if __name__ == "__main__":
    main()
