#!/usr/bin/env python3
"""Extract individual WordPress posts/pages from a WP export XML into per-file XMLs.

Posts  -> xml/YYYY/MM/slug.xml
Pages  -> xml/pages/slug.xml

Each output file is a standalone, valid XML document with the <item> wrapped in
a <wordpress-item> root that carries the original WP-export namespaces so the
content can be parsed back with the same tools.
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Namespace map used throughout the WP export
# ---------------------------------------------------------------------------
NAMESPACES = {
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "wfw":     "http://wellformedweb.org/CommentAPI/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "wp":      "http://wordpress.org/export/1.2/",
}

# Register every namespace so ET.write doesn't invent ns0/ns1/... prefixes
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def find_text(item, tag):
    """Find text of a namespaced child, return '' if missing."""
    el = item.find(tag, NAMESPACES)
    return (el.text or "") if el is not None else ""


def write_item(item, dest_path):
    """Wrap an <item> element in a root and write it as a standalone XML file."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Build a wrapper root.  Namespaces are handled by ET.register_namespace()
    # which was called at module level — no need to add xmlns: attributes
    # manually (that causes duplicates).
    root = ET.Element("wordpress-item")
    root.append(item)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(dest_path), encoding="unicode", xml_declaration=True)
    # Add trailing newline
    with open(dest_path, "a") as f:
        f.write("\n")


def main():
    # Paths
    xml_export = Path(
        "/Users/colin/Sites/github_pages/flyingsummers/"
        "wordpress-2026-05-15-14_20_39/"
        "flyingsummers.wordpress.com.2026-05-15.000.xml"
    )
    dest_root = Path("/Users/colin/Sites/github_pages/flyingsummers/xml")

    if not xml_export.exists():
        sys.exit(f"Export file not found: {xml_export}")

    print(f"Parsing {xml_export.name} ...")
    tree = ET.parse(str(xml_export))
    root = tree.getroot()

    channel = root.find("channel")
    if channel is None:
        sys.exit("No <channel> element found in export XML.")

    posts_written = 0
    pages_written = 0
    skipped = {"draft": 0, "attachment": 0, "other": 0}

    for item in channel.findall("item"):
        post_type   = find_text(item, "wp:post_type")
        status      = find_text(item, "wp:status")
        slug        = find_text(item, "wp:post_name")
        post_date   = find_text(item, "wp:post_date")  # "YYYY-MM-DD HH:MM:SS"

        if not slug:
            # Some items (especially attachments) may lack a useful slug
            skipped["other"] += 1
            continue

        if post_type == "post" and status == "publish":
            # Parse year/month from post_date
            parts = post_date.split("-")
            if len(parts) < 2:
                print(f"  WARNING: bad date '{post_date}' for slug '{slug}', skipping")
                skipped["other"] += 1
                continue
            year, month = parts[0], parts[1]
            dest = dest_root / year / month / f"{slug}.xml"
            write_item(item, dest)
            posts_written += 1

        elif post_type == "page" and status == "publish":
            dest = dest_root / "pages" / f"{slug}.xml"
            write_item(item, dest)
            pages_written += 1

        elif post_type == "attachment":
            skipped["attachment"] += 1

        elif status != "publish":
            skipped["draft"] += 1

        else:
            skipped["other"] += 1

    # Summary
    print()
    print("=== Extraction Summary ===")
    print(f"  Published posts extracted: {posts_written}")
    print(f"  Published pages extracted: {pages_written}")
    print(f"  Skipped attachments:       {skipped['attachment']}")
    print(f"  Skipped drafts/private:    {skipped['draft']}")
    print(f"  Skipped other:             {skipped['other']}")
    print(f"  Output directory:          {dest_root}")
    print()

    # Show year breakdown for posts
    year_counts = {}
    for p in sorted(dest_root.glob("20*/*/*.xml")):
        y = p.parent.parent.name
        year_counts[y] = year_counts.get(y, 0) + 1
    if year_counts:
        print("Posts by year:")
        for y in sorted(year_counts):
            print(f"  {y}: {year_counts[y]}")


if __name__ == "__main__":
    main()
