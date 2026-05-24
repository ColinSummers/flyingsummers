#!/usr/bin/env python3
"""One-time migration: posts/slug.html → YYYY/MM/DD/slug/index.html

Matches the WordPress date-based permalink structure so old URLs keep working.
Updates all internal links in post files, index pages, and generates sitemap.xml.
"""
import re, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
POSTS_DIR = BASE / 'posts'


def main():
    slug_to_date = {}
    for f in sorted(POSTS_DIR.glob('*.html')):
        content = f.read_text()
        m = re.search(r'<time datetime="(\d{4}-\d{2}-\d{2})">', content)
        if m:
            slug_to_date[f.stem] = m.group(1)
        else:
            print(f"WARNING: no date in {f.name}, skipping")

    print(f"Found {len(slug_to_date)} posts")

    def post_url(slug):
        y, m, d = slug_to_date[slug].split('-')
        return f'/{y}/{m}/{d}/{slug}/'

    def post_dir(slug):
        y, m, d = slug_to_date[slug].split('-')
        return BASE / y / m / d / slug

    # --- Move posts to date-based directories ---
    for slug in slug_to_date:
        src = POSTS_DIR / f'{slug}.html'
        content = src.read_text()

        # Posts move from 1 level deep (posts/) to 4 levels deep (YYYY/MM/DD/slug/).
        # Switch to root-relative paths instead of ../
        content = content.replace('href="../style.css"', 'href="/style.css"')
        content = content.replace('href="../">', 'href="/">')
        content = re.sub(r'href="\.\./pages/', 'href="/pages/', content)
        content = re.sub(r'href="\.\./categories/', 'href="/categories/', content)

        # Prev/next nav: href="other-slug.html" → href="/YYYY/MM/DD/other-slug/"
        for other_slug in slug_to_date:
            content = content.replace(
                f'href="{other_slug}.html"',
                f'href="{post_url(other_slug)}"'
            )

        dest = post_dir(slug)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / 'index.html').write_text(content)
        print(f"  {slug} -> {dest.relative_to(BASE)}/")

    # --- Update index.html and page/*.html ---
    index_files = [BASE / 'index.html']
    page_dir = BASE / 'page'
    if page_dir.exists():
        index_files.extend(sorted(page_dir.glob('*.html')))

    for html_file in index_files:
        content = html_file.read_text()
        for slug in slug_to_date:
            url = post_url(slug)
            content = content.replace(f'"posts/{slug}.html"', f'"{url}"')
            content = content.replace(f'"../posts/{slug}.html"', f'"{url}"')
        html_file.write_text(content)
        print(f"Updated {html_file.relative_to(BASE)}")

    # --- Generate sitemap.xml ---
    site = 'https://flyingsummers.com'
    urls = [f'  <url><loc>{site}/</loc></url>']

    for slug in sorted(slug_to_date, key=lambda s: slug_to_date[s]):
        date = slug_to_date[slug]
        urls.append(f'  <url><loc>{site}{post_url(slug)}</loc><lastmod>{date}</lastmod></url>')

    pages_dir = BASE / 'pages'
    if pages_dir.exists():
        for pg in sorted(pages_dir.glob('*.html')):
            urls.append(f'  <url><loc>{site}/pages/{pg.name}</loc></url>')

    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + '\n'.join(urls) + '\n</urlset>\n')
    (BASE / 'sitemap.xml').write_text(sitemap)
    print(f"Generated sitemap.xml ({len(urls)} URLs)")

    # --- Clean up old posts/ directory ---
    shutil.rmtree(POSTS_DIR)
    print(f"Removed old posts/ directory")

    print("\nDone! Verify with: python3 -m http.server")


if __name__ == '__main__':
    main()
