# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static HTML/CSS blog for flyingsummers.com — an aviation blog by Colin and Adam Summers ("Adam and Colin take to the sky"). Originally a WordPress.com blog (2005–2023, 302 published posts), being converted to a static site for GitHub Pages. Visual sibling to mightycheese.com and otlstudio.com.

## Development

There is no build system, package manager, or dev server. The site is pure static HTML/CSS with no JavaScript. Files are served as-is.

To preview locally: `python3 -m http.server`

## Architecture

- **style.css** — Single site-wide stylesheet (CSS variables, flexbox layout, responsive, CSS-only hamburger menu)
- **index.html** — Blog home: paginated reverse-chronological post listing with excerpts
- **posts/** — Individual post HTML files, named by slug (e.g., `composite-airplane-check-ride.html`)
- **pages/** — Static pages (who.html, what.html, where.html, when.html, why.html, how.html, books.html, glossary.html, etc.)
- **categories/** — Category index pages (flight.html, trip.html, training.html, reading.html, just-words.html)
- **archive/** — Year-based archive pages (2005.html, 2006.html, ..., 2023.html)
- **images/** — All post images, organized by year/month mirroring WordPress upload structure
- **media/** — Site-level images (header, logo, favicon)
- **_tools/** — Conversion and maintenance scripts
  - `convert.py` — WordPress XML export → static HTML converter
  - `download_images.py` — Bulk download images from WordPress.com
- **CNAME** — GitHub Pages custom domain config for flyingsummers.com

## Content Source

The WordPress export file is in `wordpress-2026-05-15-14_20_39/` (gitignored). It contains:
- 302 published posts (2005–2023)
- 22 published pages
- 1,482 image attachments (hosted at flyingsummers.com/wp-content/uploads/)
- 174 comments across 61 posts
- 2 authors: Colin Summers (colinsummers) and Adam Summers (stingraydoctor)
- 6 categories: Flight, Trip, Training, Reading, Just Words, Uncategorized
- 7 tags: clean, crash, crash safety, Flight, help, safety, saftey

### WordPress content patterns to handle
- `[caption]` shortcodes (554 uses) — image with caption text
- `[gallery]` shortcodes (92 uses) — multi-image gallery grids
- `[wpvideo]` shortcodes (16 uses) — WordPress.com hosted video
- `[youtube]` / `[vimeo]` embeds — third-party video
- `[audio]` shortcode (1 use)
- `<!--more-->` tags — excerpt/fold markers
- Inline HTML (`<p class="MsoNormal">`, etc.) — Word-pasted formatting to clean up
- Images referenced via `?w=300` style WordPress resize parameters

## Conventions

- HTML5 doctype with UTF-8 encoding
- Responsive viewport (`width=device-width, initial-scale=1.0`)
- Single stylesheet: `style.css` (linked with relative paths based on directory depth)
- All pages share a common navbar and footer template
- No JavaScript is used anywhere on the site
- Design follows sibling-site patterns: CSS custom properties, sticky navbar, CSS-only hamburger menu, max-width content area, flexbox/grid layout
- Aviation-themed color palette (sky blue accents against clean whites/grays, consistent with the mightycheese gold and otlstudio red accent pattern)

## Adding New Posts

Colin will provide a `.md` file with frontmatter. Claude converts it to an HTML post page, adds the entry to the blog index, category page, and archive page. Images referenced in the markdown should be placed in `images/` with paths updated in the HTML.

## Deployment

GitHub Pages — no build step needed. Push to main to deploy.

---

## Migration Plan

### Phase 1: Foundation (static site shell)
1. Design the color palette and CSS theme as a visual sibling to mightycheese/otlstudio
2. Build `style.css` with all shared patterns (navbar, hamburger, footer, responsive grid)
3. Create the navbar/footer template used by all pages
4. Build placeholder `index.html` (blog home)
5. Build static pages from WordPress export (who, what, where, when, why, how, books, glossary, etc.)

### Phase 2: Conversion tooling
1. Write `_tools/convert.py` — parses WordPress XML export and generates:
   - Individual post HTML files in `posts/`
   - Blog index pages (paginated, ~20 posts per page)
   - Category index pages in `categories/`
   - Year-based archive pages in `archive/`
2. Handle content conversion:
   - `[caption]` → `<figure>` / `<figcaption>`
   - `[gallery]` → CSS grid image galleries
   - `<!--more-->` → excerpt truncation on index pages
   - Strip Word-pasted classes (`MsoNormal` etc.)
   - Convert WordPress image URLs to local `images/` paths
   - `[wpvideo]` / `[youtube]` / `[vimeo]` → appropriate `<iframe>` or `<video>` embeds
   - `[audio]` → `<audio>` element
3. Write `_tools/download_images.py` — bulk download all 1,482 attachments from WordPress.com
   - Preserve directory structure (year/month)
   - Download full-size originals (strip `?w=300` resize params)
   - Verify downloads, retry failures
   - Generate web-optimized versions if originals are very large

### Phase 3: Content conversion
1. Run image download (images are still live at flyingsummers.com/wp-content/uploads/)
2. Run conversion script to generate all HTML
3. Review output, fix edge cases
4. Handle the 174 comments — render as static HTML beneath each post (read-only, no new comments)

### Phase 4: Blog features (no JS)
1. Paginated blog index with post excerpts, dates, authors, categories
2. Category pages with filtered post listings
3. Year-based archive with post listings
4. Post navigation (previous/next links)
5. Sidebar or footer with category list, archive links, about blurb
6. RSS feed (static XML file, regenerated with each new post)

### Phase 5: New post workflow
1. Colin provides `post-title.md` with YAML frontmatter (title, date, author, categories, tags) and markdown body with image placeholders
2. Claude converts to HTML post page matching site template
3. Claude updates index, category, and archive pages
4. Claude adds images to `images/` directory
5. Commit and push to deploy

### Open Questions
- **Comments**: Include the 174 existing comments as static HTML? Or drop them?
- **Videos**: The 16 `[wpvideo]` entries may be WordPress.com hosted — need to check if they're accessible or need downloading
- **Search**: WordPress had search — skip it (no JS) or add a simple category/archive browsing experience?
- **Blogger images**: Some early posts reference `photos1.blogger.com` — these may be dead links, need to check
- **Two authors**: Display author on each post? Different styling per author?
