#!/usr/bin/env python3
"""Regenerate the 6 main pages (who, what, where, when, why, how) from
the WordPress XML export, running content through the same cleanup
pipeline that convert_batch.py uses for posts.

Usage: python3 _tools/regenerate_pages.py
"""
import xml.etree.ElementTree as ET
import html
import sys
from pathlib import Path

# Allow importing convert_batch from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_batch import convert_content, load_attachments

BASE = Path(__file__).resolve().parent.parent
XML_PATH = BASE / 'blog-archive-2026-05-15.xml'
PAGES_DIR = BASE / 'pages'

TARGET_SLUGS = {'who', 'what', 'where', 'when', 'why', 'how'}


def parse_pages(xml_path):
    """Extract published pages matching TARGET_SLUGS from the WP export."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {
        'wp': 'http://wordpress.org/export/1.2/',
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'dc': 'http://purl.org/dc/elements/1.1/',
    }
    channel = root.find('channel')
    pages = {}
    for item in channel.findall('item'):
        pt = item.find('wp:post_type', ns)
        if pt is None or pt.text != 'page':
            continue
        status = item.find('wp:status', ns).text
        if status != 'publish':
            continue
        slug = item.find('wp:post_name', ns).text
        if slug not in TARGET_SLUGS:
            continue
        title = item.find('title').text or slug.capitalize()
        content = item.find('content:encoded', ns).text or ''
        pages[slug] = {'title': title, 'slug': slug, 'content': content}
    return pages


def make_page_html(page, attachments):
    """Generate full HTML for a static page."""
    title = html.escape(page['title'])
    content_html = convert_content(page['content'], attachments)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} | Flying Summers Brothers</title>
  <link rel="stylesheet" href="../style.css" />
</head>
<body>
  <div class="sky-bg"></div>
  <nav class="navbar">
    <div class="navbar-inner">
      <a class="navbar-brand" href="../">Flying Summers Brothers</a>
      <input type="checkbox" id="nav-toggle" class="nav-toggle" />
      <label for="nav-toggle" class="nav-toggle-label"></label>
      <ul class="nav-links">
        <li><a href="who.html">Who</a></li>
        <li><a href="what.html">What</a></li>
        <li><a href="where.html">Where</a></li>
        <li><a href="why.html">Why</a></li>
        <li><a href="how.html">How</a></li>
      </ul>
    </div>
  </nav>
  <main>
    <div class="page-content card">
      <h1>{title}</h1>
      {content_html}
    </div>
  </main>
  <footer>
    <p>&copy; Colin &amp; Adam Summers. Two brothers, one sky.</p>
  </footer>
</body>
</html>
'''


def main():
    attachments = load_attachments()
    pages = parse_pages(XML_PATH)

    missing = TARGET_SLUGS - set(pages.keys())
    if missing:
        print(f"WARNING: could not find pages for slugs: {', '.join(sorted(missing))}")

    PAGES_DIR.mkdir(exist_ok=True)
    for slug in sorted(pages):
        page = pages[slug]
        page_html = make_page_html(page, attachments)
        path = PAGES_DIR / f'{slug}.html'
        with open(path, 'w') as f:
            f.write(page_html)
        print(f"  wrote {path.relative_to(BASE)}")

    print(f"Regenerated {len(pages)} pages.")


if __name__ == '__main__':
    main()
