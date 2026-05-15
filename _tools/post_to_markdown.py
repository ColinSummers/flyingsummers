#!/usr/bin/env python3
"""Convert a single WordPress XML item file (as produced by extract_posts.py)
to Markdown with YAML frontmatter.

Usage:
    python3 _tools/post_to_markdown.py xml/2023/07/up-for-sale.xml > post.md
    python3 _tools/post_to_markdown.py xml/pages/who.xml > who.md

Handles WordPress shortcodes: [caption], [gallery], [wpvideo], [youtube],
[vimeo], [audio].  Converts common HTML tags to Markdown equivalents.
"""

import html
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Namespace map (must match extract_posts.py)
# ---------------------------------------------------------------------------
NAMESPACES = {
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "wfw":     "http://wellformedweb.org/CommentAPI/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "wp":      "http://wordpress.org/export/1.2/",
}


def find_text(item, tag):
    el = item.find(tag, NAMESPACES)
    return (el.text or "") if el is not None else ""


# ---------------------------------------------------------------------------
# Shortcode processors — run BEFORE HTML-to-markdown
# ---------------------------------------------------------------------------

def process_caption(content):
    r"""[caption id="..." align="..." width="..."]<a ...><img .../></a> Caption text[/caption]
    -> <figure><img ...><figcaption>Caption text</figcaption></figure>

    We convert to markdown-friendly form: image + italic caption.
    """
    def _replace(m):
        inner = m.group(1).strip()
        # Extract the img tag
        img_match = re.search(r'<img[^>]+>', inner)
        if not img_match:
            return inner
        img_tag = img_match.group(0)
        # Get caption text: everything after the closing </a> or after the img
        # if there's no wrapping <a>
        caption = inner
        # Remove everything up to and including the img (and its wrapper link)
        caption = re.sub(r'.*?<img[^>]+/?>\s*', '', caption)
        caption = re.sub(r'</a>\s*', '', caption).strip()
        # Return as figure-like block that our HTML converter will pick up
        return f'<figure>{img_tag}<figcaption>{caption}</figcaption></figure>'

    return re.sub(
        r'\[caption[^\]]*\](.*?)\[/caption\]',
        _replace,
        content,
        flags=re.DOTALL,
    )


def process_gallery(content):
    """[gallery ids="1,2,3" ...] -> placeholder (images are attachment IDs,
    we can't resolve them here, so leave a marker)."""
    def _replace(m):
        attrs = m.group(1)
        ids_match = re.search(r'ids="([^"]*)"', attrs)
        ids = ids_match.group(1) if ids_match else ""
        return f'\n\n<!-- gallery: ids={ids} -->\n\n'
    return re.sub(r'\[gallery([^\]]*)\]', _replace, content)


def process_wpvideo(content):
    """[wpvideo XXXXXXXX] -> video embed placeholder."""
    def _replace(m):
        video_id = m.group(1).strip()
        return f'\n\n{{{{< wpvideo {video_id} >}}}}\n\n'
    return re.sub(r'\[wpvideo\s+([^\]]+)\]', _replace, content)


def process_youtube(content):
    """[youtube=URL] or [youtube URL] -> markdown link / embed."""
    def _replace(m):
        url = m.group(1).strip().strip("=").strip()
        # Extract video ID for a clean embed reference
        vid_match = re.search(r'(?:v=|youtu\.be/)([\w-]+)', url)
        vid = vid_match.group(1) if vid_match else url
        return f'\n\n{{{{< youtube {vid} >}}}}\n\n'
    return re.sub(r'\[youtube[= ]+([^\]]+)\]', _replace, content, flags=re.IGNORECASE)


def process_vimeo(content):
    """[vimeo URL] or [vimeo 12345] -> embed placeholder."""
    def _replace(m):
        val = m.group(1).strip()
        vid_match = re.search(r'(\d+)', val)
        vid = vid_match.group(1) if vid_match else val
        return f'\n\n{{{{< vimeo {vid} >}}}}\n\n'
    return re.sub(r'\[vimeo\s+([^\]]+)\]', _replace, content, flags=re.IGNORECASE)


def process_audio(content):
    """[audio ...] -> audio tag placeholder."""
    def _replace(m):
        attrs = m.group(1)
        src_match = re.search(r'(?:src|mp3|ogg|wav)="([^"]*)"', attrs)
        src = src_match.group(1) if src_match else ""
        return f'\n\n{{{{< audio "{src}" >}}}}\n\n'
    return re.sub(r'\[audio([^\]]*)\]', _replace, content, flags=re.IGNORECASE)


def process_more(content):
    """<!--more--> -> a horizontal rule (the fold marker)."""
    return content.replace("<!--more-->", "\n\n<!--more-->\n\n")


def process_shortcodes(content):
    """Run all shortcode processors in order."""
    content = process_caption(content)
    content = process_gallery(content)
    content = process_wpvideo(content)
    content = process_youtube(content)
    content = process_vimeo(content)
    content = process_audio(content)
    content = process_more(content)
    return content


# ---------------------------------------------------------------------------
# HTML to Markdown conversion
# ---------------------------------------------------------------------------

def html_to_markdown(content):
    """Convert WordPress HTML content to Markdown.

    This is intentionally a regex-based converter rather than a full DOM parser.
    WordPress content is a mix of raw text (double-newline = paragraph) and
    inline HTML tags; a DOM parser would lose the whitespace structure.
    """
    text = content

    # --- Strip Word-pasted junk classes ---
    text = re.sub(r'<p[^>]*class="Mso[^"]*"[^>]*>', '<p>', text)
    text = re.sub(r'<span[^>]*class="Mso[^"]*"[^>]*>(.*?)</span>', r'\1', text, flags=re.DOTALL)

    # --- Headings (h1-h6) ---
    for level in range(1, 7):
        tag = f'h{level}'
        hashes = '#' * level
        text = re.sub(
            rf'<{tag}[^>]*>(.*?)</{tag}>',
            lambda m, h=hashes: f'\n\n{h} {m.group(1).strip()}\n\n',
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # --- Figures (from our caption processor) ---
    def _figure_replace(m):
        inner = m.group(1)
        img_match = re.search(r'<img[^>]+>', inner)
        caption_match = re.search(r'<figcaption>(.*?)</figcaption>', inner, re.DOTALL)
        if img_match:
            img = img_match.group(0)
            src = re.search(r'src="([^"]*)"', img)
            alt = re.search(r'alt="([^"]*)"', img)
            src_val = src.group(1) if src else ""
            alt_val = alt.group(1) if alt else ""
            # Strip WP resize params
            src_val = re.sub(r'\?w=\d+(&h=\d+)?', '', src_val)
            md = f'![{alt_val}]({src_val})'
            if caption_match:
                cap = caption_match.group(1).strip()
                md += f'\n*{cap}*'
            return f'\n\n{md}\n\n'
        return inner

    text = re.sub(r'<figure[^>]*>(.*?)</figure>', _figure_replace, text, flags=re.DOTALL)

    # --- Images (standalone, not in figures) ---
    def _img_replace(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]*)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        src_val = src.group(1) if src else ""
        alt_val = alt.group(1) if alt else ""
        src_val = re.sub(r'\?w=\d+(&h=\d+)?', '', src_val)
        return f'![{alt_val}]({src_val})'
    text = re.sub(r'<img\s[^>]+/?>', _img_replace, text)

    # --- Links ---
    def _link_replace(m):
        attrs = m.group(1)
        inner = m.group(2)
        href_match = re.search(r'href="([^"]*)"', attrs)
        href = href_match.group(1) if href_match else ""
        # If the link just wraps an image markdown, return the image
        if inner.strip().startswith('!['):
            return inner
        return f'[{inner}]({href})'
    text = re.sub(r'<a\s([^>]*)>(.*?)</a>', _link_replace, text, flags=re.DOTALL)

    # --- Blockquotes ---
    def _blockquote(m):
        inner = m.group(1).strip()
        lines = inner.split('\n')
        quoted = '\n'.join(f'> {line}' for line in lines)
        return f'\n\n{quoted}\n\n'
    text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', _blockquote, text, flags=re.DOTALL)

    # --- Lists ---
    # Unordered
    def _ul(m):
        inner = m.group(1)
        items = re.findall(r'<li[^>]*>(.*?)</li>', inner, re.DOTALL)
        md_items = [f'- {item.strip()}' for item in items]
        return '\n\n' + '\n'.join(md_items) + '\n\n'
    text = re.sub(r'<ul[^>]*>(.*?)</ul>', _ul, text, flags=re.DOTALL)

    # Ordered
    def _ol(m):
        inner = m.group(1)
        items = re.findall(r'<li[^>]*>(.*?)</li>', inner, re.DOTALL)
        md_items = [f'{i+1}. {item.strip()}' for i, item in enumerate(items)]
        return '\n\n' + '\n'.join(md_items) + '\n\n'
    text = re.sub(r'<ol[^>]*>(.*?)</ol>', _ol, text, flags=re.DOTALL)

    # --- Bold / italic / strong / em ---
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)

    # --- Strikethrough ---
    text = re.sub(r'<(?:del|s|strike)[^>]*>(.*?)</(?:del|s|strike)>', r'~~\1~~', text, flags=re.DOTALL)

    # --- Code ---
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', lambda m: f'\n\n```\n{m.group(1).strip()}\n```\n\n', text, flags=re.DOTALL)

    # --- Horizontal rules ---
    text = re.sub(r'<hr\s*/?>', '\n\n---\n\n', text)

    # --- Line breaks ---
    text = re.sub(r'<br\s*/?>', '  \n', text)

    # --- Paragraphs ---
    # Replace <p> tags with double newlines
    text = re.sub(r'<p[^>]*>', '\n\n', text)
    text = re.sub(r'</p>', '\n\n', text)

    # --- Strip remaining HTML tags we haven't handled ---
    text = re.sub(r'</?(?:div|span|table|tr|td|th|thead|tbody|iframe|object|embed|param|center|font)[^>]*>', '', text, flags=re.IGNORECASE)

    # --- Clean up ---
    # Decode HTML entities
    text = html.unescape(text)

    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip leading/trailing whitespace from each line (but preserve blank lines)
    lines = text.split('\n')
    lines = [line.rstrip() for line in lines]
    text = '\n'.join(lines)

    # Strip leading/trailing blank lines
    text = text.strip()

    return text


# ---------------------------------------------------------------------------
# Comment extraction
# ---------------------------------------------------------------------------

def extract_comments(item):
    """Extract comments from the item, return list of dicts."""
    comments = []
    for c in item.findall("wp:comment", NAMESPACES):
        approved = find_text_elem(c, "wp:comment_approved")
        if approved != "1":
            continue
        comments.append({
            "id":     find_text_elem(c, "wp:comment_id"),
            "author": find_text_elem(c, "wp:comment_author"),
            "date":   find_text_elem(c, "wp:comment_date"),
            "content": find_text_elem(c, "wp:comment_content"),
            "parent": find_text_elem(c, "wp:comment_parent"),
        })
    return comments


def find_text_elem(parent, tag):
    el = parent.find(tag, NAMESPACES)
    return (el.text or "") if el is not None else ""


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------

def yaml_escape(s):
    """Escape a string for YAML — wrap in quotes if it contains special chars."""
    if not s:
        return '""'
    if any(c in s for c in ':#{}[]&*?|>!%@`,"\'') or s.startswith(('-', ' ')):
        # Double-quote and escape internal quotes
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def build_frontmatter(item):
    """Build YAML frontmatter dict from an <item> element."""
    title     = find_text(item, "title")
    date      = find_text(item, "wp:post_date")
    creator   = find_text(item, "dc:creator")
    post_type = find_text(item, "wp:post_type")
    slug      = find_text(item, "wp:post_name")
    post_id   = find_text(item, "wp:post_id")
    status    = find_text(item, "wp:status")
    excerpt   = find_text(item, "{%s}encoded" % NAMESPACES["excerpt"])

    # Author display-name map
    author_map = {
        "colinsummers":   "Colin Summers",
        "stingraydoctor": "Adam Summers",
    }
    author = author_map.get(creator, creator)

    # Categories and tags
    categories = []
    tags = []
    for cat in item.findall("category"):
        domain = cat.get("domain", "")
        name = cat.text or ""
        if domain == "category":
            categories.append(name)
        elif domain == "post_tag":
            tags.append(name)

    lines = ["---"]
    lines.append(f"title: {yaml_escape(title)}")
    lines.append(f"date: {yaml_escape(date)}")
    lines.append(f"author: {yaml_escape(author)}")
    lines.append(f"slug: {yaml_escape(slug)}")
    lines.append(f"post_id: {post_id}")
    lines.append(f"type: {post_type}")

    if categories:
        lines.append("categories:")
        for c in categories:
            lines.append(f"  - {yaml_escape(c)}")

    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {yaml_escape(t)}")

    if excerpt:
        lines.append(f"excerpt: {yaml_escape(excerpt)}")

    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: post_to_markdown.py <path-to-xml-file>", file=sys.stderr)
        print("  e.g. python3 _tools/post_to_markdown.py xml/2023/07/up-for-sale.xml", file=sys.stderr)
        sys.exit(1)

    xml_path = Path(sys.argv[1])
    if not xml_path.exists():
        sys.exit(f"File not found: {xml_path}")

    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    # The item is the first (and only) child of our wrapper root
    item = root.find("item")
    if item is None:
        # Might be namespaced differently — try direct children
        items = list(root)
        if items:
            item = items[0]
        else:
            sys.exit("No <item> found in XML file.")

    # Build frontmatter
    frontmatter = build_frontmatter(item)

    # Get content
    content_el = item.find("{%s}encoded" % NAMESPACES["content"])
    raw_content = (content_el.text or "") if content_el is not None else ""

    # Strip Gutenberg block comments, then process shortcodes, then convert
    raw_content = re.sub(r'<!-- /?wp:\w+[^>]*-->\s*', '', raw_content)
    processed = process_shortcodes(raw_content)
    markdown = html_to_markdown(processed)

    # Extract comments
    comments = extract_comments(item)

    # Output
    print(frontmatter)
    print()
    print(markdown)

    if comments:
        print()
        print()
        print("---")
        print()
        print(f"## Comments ({len(comments)})")
        print()
        for c in comments:
            print(f"**{c['author']}** ({c['date']}):")
            print()
            # Convert comment HTML to markdown too
            comment_md = html_to_markdown(c["content"])
            print(comment_md)
            print()


if __name__ == "__main__":
    main()
