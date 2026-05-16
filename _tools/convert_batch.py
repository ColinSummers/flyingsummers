#!/usr/bin/env python3
"""Convert WordPress XML export posts to static HTML.

Usage: python3 _tools/convert_batch.py [--count N] [--download-images]

Reads the WordPress export XML and attachment map, generates:
  - posts/*.html       Individual post pages
  - index.html         Blog home with excerpts
  - images/**          Downloaded post images (with --download-images)
"""
import xml.etree.ElementTree as ET
import json, re, os, sys, html, urllib.request, urllib.error, io
from pathlib import Path
from datetime import datetime
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
XML_PATH = BASE / 'blog-archive-2026-05-15.xml'
ATTACHMENTS_PATH = BASE / '_tools' / 'attachments.json'
POSTS_DIR = BASE / 'posts'
IMAGES_DIR = BASE / 'images'
R2_BASE = 'https://pub-2e58c6df17c64bd492e25a414243b1b7.r2.dev'
IMG_DIMS_CACHE_PATH = BASE / '_tools' / 'image_dims.json'
_img_dims_cache = {}


def load_img_dims_cache():
    global _img_dims_cache
    if IMG_DIMS_CACHE_PATH.exists():
        with open(IMG_DIMS_CACHE_PATH) as f:
            _img_dims_cache = json.load(f)


def save_img_dims_cache():
    with open(IMG_DIMS_CACHE_PATH, 'w') as f:
        json.dump(_img_dims_cache, f, indent=1, sort_keys=True)


def get_image_dims(url):
    """Fetch image dimensions from a URL. Returns (width, height) or None."""
    if url in _img_dims_cache:
        return tuple(_img_dims_cache[url])
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            img = Image.open(io.BytesIO(data))
            dims = img.size
            _img_dims_cache[url] = list(dims)
            return dims
    except Exception:
        return None


def ensure_img_dims(html_str):
    """Add width/height to <img> tags that lack them."""
    def add_dims(m):
        tag = m.group(0)
        if 'width=' in tag and 'height=' in tag:
            return tag
        src_m = re.search(r'src="([^"]+)"', tag)
        if not src_m:
            return tag
        url = src_m.group(1)
        if not url.startswith(R2_BASE):
            return tag
        dims = get_image_dims(url)
        if not dims:
            return tag
        w, h = dims
        tag = tag.rstrip(' />')
        if 'width=' not in tag:
            tag += f' width="{w}"'
        if 'height=' not in tag:
            tag += f' height="{h}"'
        tag += ' />'
        return tag
    return re.sub(r'<img[^>]+/?>', add_dims, html_str)

def load_attachments():
    with open(ATTACHMENTS_PATH) as f:
        return json.load(f)

def parse_posts(xml_path, count=None):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {
        'wp': 'http://wordpress.org/export/1.2/',
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
        'dc': 'http://purl.org/dc/elements/1.1/',
    }
    channel = root.find('channel')
    posts = []
    for item in channel.findall('item'):
        pt = item.find('wp:post_type', ns)
        if pt is None or pt.text != 'post':
            continue
        status = item.find('wp:status', ns).text
        if status != 'publish':
            continue
        date = item.find('wp:post_date', ns).text
        title = item.find('title').text or 'Untitled'
        slug = item.find('wp:post_name', ns).text
        author = item.find('dc:creator', ns).text
        content = item.find('content:encoded', ns).text or ''
        excerpt_el = item.find('excerpt:encoded', ns)
        excerpt_text = excerpt_el.text if excerpt_el is not None and excerpt_el.text else ''
        cats = [c.text for c in item.findall('category') if c.get('domain') == 'category']
        tags = [c.text for c in item.findall('category') if c.get('domain') == 'post_tag']
        thumb_id = None
        for pm in item.findall('wp:postmeta', ns):
            key = pm.find('wp:meta_key', ns).text
            if key == '_thumbnail_id':
                thumb_id = pm.find('wp:meta_value', ns).text
                break
        comments = []
        for c in item.findall('wp:comment', ns):
            ca = c.find('wp:comment_approved', ns)
            if ca is not None and ca.text == '1':
                comments.append({
                    'author': c.find('wp:comment_author', ns).text or 'Anonymous',
                    'date': c.find('wp:comment_date', ns).text,
                    'content': c.find('wp:comment_content', ns).text or ''
                })
        posts.append({
            'date': date, 'title': title, 'slug': slug, 'author': author,
            'content': content, 'excerpt': excerpt_text,
            'categories': cats, 'tags': tags,
            'thumbnail_id': thumb_id, 'comments': comments
        })
    posts.sort(key=lambda x: x['date'], reverse=True)
    if count:
        posts = posts[:count]
    return posts


SKIP_PAGES = {'atari', 'drone', 'fhr-condo', 'home-movies-super8',
               '2007-diamond-twinstar-da42-for-sale', '2007-diamond-da42-for-sale',
               'n972rd', 'n972rd-ahrs-failure', 'what', 'when'}

SIDEBAR_PAGES = [
    ('The Plane', [
        ('a-plane-like-none-other', 'A Plane Like None Other'),
        ('n972rd-ahrs-failure', 'AHRS Failure'),
    ]),
    ('Flying', [
        ('crossing-the-country', 'Crossing the Country'),
        ('flights-colin', 'Flights'),
        ('states', 'States'),
        ('airports-visited-colin', 'Airports'),
    ]),
    ('Reference', [
        ('books', 'Books'),
        ('glossary', 'Glossary'),
        ('links', 'Links'),
    ]),
]


def parse_pages(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {
        'wp': 'http://wordpress.org/export/1.2/',
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'dc': 'http://purl.org/dc/elements/1.1/',
    }
    channel = root.find('channel')
    pages = []
    for item in channel.findall('item'):
        pt = item.find('wp:post_type', ns)
        if pt is None or pt.text != 'page':
            continue
        status = item.find('wp:status', ns).text
        if status != 'publish':
            continue
        slug = item.find('wp:post_name', ns).text
        if slug in SKIP_PAGES:
            continue
        title = item.find('title').text or 'Untitled'
        content = item.find('content:encoded', ns).text or ''
        pages.append({'slug': slug, 'title': title, 'content': content})
    return pages


def make_nav_links(prefix='', from_pages=False):
    """Generate the <ul class="nav-links"> with dropdown menus.
    prefix: path prefix to site root ('' for root, '../' for subdirs).
    from_pages: True when generating pages in pages/ (links are siblings).
    """
    if from_pages:
        p = ''
    else:
        p = f'{prefix}pages/'
    return f'''<ul class="nav-links">
        <li><a href="{p}who.html">Who</a></li>
        <li><a href="{p}where.html">Where</a>
          <ul class="nav-dropdown">
            <li><a href="{p}crossing-the-country.html">Crossing the Country</a></li>
            <li><a href="{p}flights-colin.html">Flights</a></li>
            <li><a href="{p}states.html">States</a></li>
            <li><a href="{p}airports-visited-colin.html">Airports</a></li>
          </ul>
        </li>
        <li><a href="{p}why.html">Why</a></li>
        <li><a href="{p}how.html">How</a>
          <ul class="nav-dropdown">
            <li><a href="{p}glossary.html">Glossary</a></li>
            <li><a href="{p}links.html">Links</a></li>
            <li><a href="{p}books.html">Books</a></li>
          </ul>
        </li>
        <li><a href="{p}a-plane-like-none-other.html">N972RD</a></li>
      </ul>
      <label for="search-toggle" class="search-icon"><svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="7" fill="none" stroke="currentColor" stroke-width="2.5"/><line x1="15.5" y1="15.5" x2="22" y2="22" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg></label>'''


SEARCH_DIALOG = '''  <input type="checkbox" id="search-toggle" class="search-toggle" />
  <label for="search-toggle" class="search-overlay"></label>
  <div class="search-dialog">
    <label for="search-toggle" class="search-close">&times;</label>
    <h3>Search Flying Summers Brothers</h3>
    <form action="https://www.google.com/search" method="get">
      <input type="hidden" name="sitesearch" value="flyingsummers.com" />
      <input type="text" name="q" placeholder="Search..." />
      <button type="submit">Go</button>
    </form>
  </div>'''


def wp_url_to_local(url):
    """Convert a WordPress upload URL to a local images/ path."""
    url = re.sub(r'\?w=\d+(&h=\d+)?', '', url)
    m = re.search(r'/wp-content/uploads/(.+)$', url)
    if m:
        return 'images/' + m.group(1)
    return None


def clean_url(url):
    """Strip WP resize params from URL."""
    return re.sub(r'\?w=\d+(&h=\d+)?', '', url)


def clean_img_tag(img_tag):
    """Clean WP cruft from an img tag and fix src to local path."""
    img_tag = re.sub(r'src="([^"]+)"', lambda m: f'src="{fix_img_src(m.group(1))}"', img_tag)
    img_tag = re.sub(r'\s*class="[^"]*"', '', img_tag)
    img_tag = re.sub(r'\s*srcset="[^"]*"', '', img_tag)
    img_tag = re.sub(r'\s*sizes="[^"]*"', '', img_tag)
    img_tag = re.sub(r'\s*data-[a-z-]+="[^"]*"', '', img_tag)
    return img_tag


TYPO_FIXES = {
    'N972RD want to be in that sky': 'N972RD wants to be in that sky',
    'hope around in the little plane': 'hop around in the little plane',
    'of Norwood in moment': 'of Norwood in moments',
}

WPVIDEO_MAP = {
    '1uetUdsB': 'buffalo.mp4',
    '8kjjodEr': 'ksmo-n972rd-ldg.mov',
    'ausAFuPY': 'img_2356.mov',
    'AZtYpTSX': 'corvalis.mov',
    'dAIJbgUx': 'ils-kind-nt1.mov',
    'H1AhWnv1': 'depart-ifr.mov',
    'h6J2BYkY': 'dynamic-sky.mov',
    'ifvLLVw3': 'spinning.mov',
    'mGzWYvRs': 'bridge-video.m4v',
    'Ncik3loG': 'landing_2_fhr.mov',
    'PpOI51sC': 'malfunction.mov',
    'Rtr72EOr': 'ohio.m4v',
    'T83npYjg': 'landing-klgb.mov',
    'vExh868d': 'beauty-of-ifr.mov',
    'voihpRWi': 'icing-video.mp4',
    'w40aJ7nN': 'img_5228.m4v',
    'w8xU7VIp': 'landingfhr.mov',
}


def wpautop(text):
    """Mimic WordPress wpautop: convert double-newlines to <p> tags."""
    if '<p>' in text or '<p ' in text:
        return text
    blocks = re.split(r'\n{2,}', text)
    result = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if re.match(r'^<(?:figure|div|blockquote|ul|ol|h[1-6]|table|pre|hr)', block, re.I):
            result.append(block)
        elif re.match(r'^\[(?:caption|gallery|wpvideo|youtube|vimeo|audio)', block):
            result.append(block)
        elif re.match(r'^<!--', block):
            result.append(block)
        else:
            block = block.replace('\n', '<br />\n')
            result.append(f'<p>{block}</p>')
    return '\n\n'.join(result)


def convert_content(content, attachments):
    """Convert WordPress HTML content to clean static HTML."""
    for old, new in TYPO_FIXES.items():
        content = content.replace(old, new)

    # Handle <!--more--> by removing it (full content on post page)
    content = content.replace('<!--more-->', '')

    # Convert double-newline paragraphs to <p> tags (older WP posts)
    content = wpautop(content)

    # Convert Gutenberg YouTube/Vimeo embeds (bare URLs in wp-block-embed wrappers)
    def gutenberg_embed(m):
        url = m.group(1).strip()
        yt = re.search(r'youtube\.com/watch\?v=([^&\s"]+)', url)
        if yt:
            return f'<div class="video-embed"><iframe src="https://www.youtube.com/embed/{yt.group(1)}" allowfullscreen loading="lazy"></iframe></div>'
        vi = re.search(r'vimeo\.com/(\d+)', url)
        if vi:
            return f'<div class="video-embed"><iframe src="https://player.vimeo.com/video/{vi.group(1)}" allowfullscreen loading="lazy"></iframe></div>'
        return ''
    content = re.sub(
        r'<figure[^>]*wp-block-embed[^>]*>.*?<div[^>]*>\s*(https?://[^\s<]+)\s*</div>\s*</figure>',
        gutenberg_embed, content, flags=re.DOTALL
    )

    # Strip WordPress block editor comments
    content = re.sub(r'<!-- /?wp:\w+[^>]*-->\s*', '', content)

    # Convert [caption] shortcodes to <figure>
    def caption_replace(m):
        body = m.group(1).strip()
        img_match = re.search(r'<img[^>]+>', body)
        img_tag = img_match.group(0) if img_match else ''
        caption_text = re.sub(r'</?a[^>]*>', '', body)
        caption_text = re.sub(r'<img[^>]+>', '', caption_text).strip()
        img_tag = clean_img_tag(img_tag)
        if caption_text:
            return f'<figure>{img_tag}<figcaption>{caption_text}</figcaption></figure>'
        return f'<figure>{img_tag}</figure>'

    content = re.sub(
        r'\[caption[^\]]*\](.*?)\[/caption\]',
        caption_replace, content, flags=re.DOTALL
    )

    # Convert [gallery] shortcodes
    def gallery_replace(m):
        attrs = m.group(1)
        ids_match = re.search(r'ids="([^"]+)"', attrs)
        if not ids_match:
            return ''
        ids = ids_match.group(1).split(',')
        imgs = []
        for aid in ids:
            url = attachments.get(aid.strip())
            if url:
                local = wp_url_to_local(url)
                if local:
                    imgs.append(f'<a href="{R2_BASE}/{local}"><img src="{R2_BASE}/{local}" alt="" loading="lazy" /></a>')
        if imgs:
            return '<div class="gallery">' + '\n'.join(imgs) + '</div>'
        return ''

    content = re.sub(r'\[gallery([^\]]*)\]', gallery_replace, content)

    # Convert [wpvideo] shortcodes to local <video> elements
    def wpvideo_replace(m):
        vid_id = m.group(1)
        filename = WPVIDEO_MAP.get(vid_id)
        if filename:
            poster_name = re.sub(r'\.[^.]+$', '.jpg', filename)
            return f'<div class="video-embed"><video controls preload="metadata" poster="{R2_BASE}/videos/posters/{poster_name}"><source src="{R2_BASE}/videos/{filename}" /></video></div>'
        return f'<div class="video-embed"><p><em>[Video: {vid_id} — file not mapped]</em></p></div>'
    content = re.sub(r'\[wpvideo\s+(\w+)[^\]]*\]', wpvideo_replace, content)

    # Convert [youtube] and [vimeo]
    content = re.sub(r'\[youtube\s+([^\]]+)\]',
                     r'<div class="video-embed"><iframe src="https://www.youtube.com/embed/\1" allowfullscreen loading="lazy"></iframe></div>',
                     content)
    content = re.sub(r'\[vimeo\s+([^\]]+)\]',
                     r'<div class="video-embed"><iframe src="https://player.vimeo.com/video/\1" allowfullscreen loading="lazy"></iframe></div>',
                     content)

    # Convert [audio] shortcodes
    content = re.sub(r'\[audio\s+([^\]]+)\]',
                     r'<audio controls src="\1"></audio>',
                     content)

    # Fix remaining img src URLs
    content = re.sub(r'src="([^"]*flyingsummers\.com/wp-content/uploads/[^"]*)"',
                     lambda m2: f'src="{fix_img_src(m2.group(1))}"', content)

    # Fix link href for images
    content = re.sub(r'href="([^"]*flyingsummers\.com/wp-content/uploads/[^"]*)"',
                     lambda m2: f'href="{fix_img_src(m2.group(1))}"', content)

    # Remove Word/iWork-pasted classes and spans
    content = re.sub(r'\s*class="Mso[^"]*"', '', content)
    content = re.sub(r'<p class="MsoNormal">', '<p>', content)
    content = re.sub(r'\s*class="[ps]\d+"', '', content)
    content = re.sub(r'<span class="[ps]\d+">(.*?)</span>', r'\1', content, flags=re.DOTALL)
    # Unwrap bare spans with no attributes left
    content = re.sub(r'<span>(.*?)</span>', r'\1', content, flags=re.DOTALL)
    # Remove inline text-align styles on paragraphs (keep the content)
    content = re.sub(r'\s*style="text-align:\s*right;?"', '', content)

    # Remove Gutenberg block classes and remaining WP classes on any tag
    content = re.sub(r'\s*class="wp-block-[^"]*"', '', content)
    content = re.sub(r'\s*class="wp-image-\d+"', '', content)
    content = re.sub(r'\s*class="wp-element-caption"', '', content)
    content = re.sub(r'\s*class="size-\w+"', '', content)
    content = re.sub(r'\s*class="[^"]*(?:wp-image|aligncenter|alignleft|alignright|size-)[^"]*"', '', content)

    # Clean bare img tags that weren't inside [caption]
    content = re.sub(r'<img([^>]*)>', lambda m: clean_img_tag(f'<img{m.group(1)}>'), content)

    # Fix figcaption that contains img (malformed caption nesting)
    def fix_figcaption(m):
        inner = m.group(1)
        img_match = re.search(r'<img[^>]+>', inner)
        if img_match:
            img_tag = img_match.group(0)
            caption = re.sub(r'<img[^>]+>', '', inner).strip()
            if caption:
                return f'{img_tag}<figcaption>{caption}</figcaption>'
            return img_tag
        return f'<figcaption>{inner}</figcaption>'
    content = re.sub(r'<figcaption>(.*?)</figcaption>', fix_figcaption, content, flags=re.DOTALL)

    # Remove empty paragraphs
    content = re.sub(r'<p>\s*</p>', '', content)

    # Add width/height to images missing them
    content = ensure_img_dims(content)

    return content.strip()


def fix_img_src(url):
    """Convert a WP image URL to an R2 URL."""
    url = clean_url(url)
    local = wp_url_to_local(url)
    if local:
        return f'{R2_BASE}/{local}'
    return url


def get_excerpt(content, max_chars=300):
    """Extract a text excerpt from HTML content."""
    for old, new in TYPO_FIXES.items():
        content = content.replace(old, new)
    if '<!--more-->' in content:
        before = content.split('<!--more-->')[0]
        before_clean = re.sub(r'<[^>]+>', '', re.sub(r'\[/?[^\]]+\]', '', before))
        if len(before_clean.split()) >= 50:
            text = before
        else:
            text = content
    else:
        text = content

    text = re.sub(r'\[caption[^\]]*\].*?\[/caption\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[gallery[^\]]*\]', '', text)
    text = re.sub(r'<figure[^>]*>.*?</figure>', '', text, flags=re.DOTALL)
    text = re.sub(r'<figcaption[^>]*>.*?</figcaption>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[/?[^\]]+\]', '', text)
    text = html.unescape(text).strip()

    paras = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    text = ''
    for p in paras:
        if text:
            text += ' '
        text += p
        if len(text.split()) >= 50:
            break

    if len(text) > max_chars:
        text = text[:max_chars].rsplit(' ', 1)[0] + '...'
    return text


FALLBACK_IMAGES = {
    'the-same-mistake-over-and-over': 'images/2020/01/da40-audio.png',
}


def get_first_image(content, attachments, slug=None):
    """Get the first image URL from post content for use as card image."""
    if slug and slug in FALLBACK_IMAGES:
        return FALLBACK_IMAGES[slug]
    # Check for img tags
    m = re.search(r'<img[^>]+src="([^"]+)"', content)
    if m:
        url = clean_url(m.group(1))
        local = wp_url_to_local(url)
        if local:
            return local
    # Check caption shortcodes
    m = re.search(r'\[caption[^\]]*\].*?src="([^"]+)"', content, re.DOTALL)
    if m:
        url = clean_url(m.group(1))
        local = wp_url_to_local(url)
        if local:
            return local
    # Check for wpvideo — use the poster image
    m = re.search(r'\[wpvideo\s+(\w+)', content)
    if m:
        filename = WPVIDEO_MAP.get(m.group(1))
        if filename:
            poster = re.sub(r'\.[^.]+$', '.jpg', filename)
            return f'videos/posters/{poster}'
    return None


def format_date(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    return dt.strftime('%B %-d, %Y')


def format_date_short(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    return dt.strftime('%b %-d, %Y')


def add_lightbox(content_html, slug, title=''):
    """Wrap images in lightbox links and append lightbox overlays."""
    images = []
    # Collect all images with their captions
    # From figures
    for m in re.finditer(r'<figure>(.*?)</figure>', content_html, re.DOTALL):
        inner = m.group(1)
        img_m = re.search(r'<img[^>]+src="([^"]+)"[^>]*>', inner)
        cap_m = re.search(r'<figcaption>(.*?)</figcaption>', inner, re.DOTALL)
        if img_m:
            images.append({
                'src': img_m.group(1),
                'caption': cap_m.group(1) if cap_m else '',
                'full_match': m.group(0),
                'type': 'figure'
            })
    # From galleries
    for m in re.finditer(r'<div class="gallery">(.*?)</div>', content_html, re.DOTALL):
        inner = m.group(1)
        for img_m in re.finditer(r'<a[^>]*><img[^>]+src="([^"]+)"[^>]*/></a>', inner):
            images.append({
                'src': img_m.group(1),
                'caption': '',
                'full_match': None,
                'type': 'gallery'
            })

    if not images:
        return content_html

    total = len(images)
    lightboxes = ''

    # Replace figure images with clickable links
    img_idx = 0
    for img in images:
        lb_id = f'lb-{slug}-{img_idx}'
        if img['type'] == 'figure' and img['full_match']:
            inner = img['full_match']
            # Wrap the img in a link to the lightbox
            new_inner = re.sub(
                r'(<img[^>]+>)',
                f'<a href="#{lb_id}">\\1</a>',
                inner, count=1
            )
            content_html = content_html.replace(img['full_match'], new_inner, 1)
        img_idx += 1

    # Replace gallery images with clickable links
    img_idx_gallery = len([i for i in images if i['type'] == 'figure'])
    def gallery_img_replace(gallery_match):
        nonlocal img_idx_gallery
        gallery_html = gallery_match.group(1)
        def single_img(m):
            nonlocal img_idx_gallery
            lb_id = f'lb-{slug}-{img_idx_gallery}'
            img_tag = re.search(r'<img[^>]+/>', m.group(0)).group(0)
            img_idx_gallery += 1
            return f'<a href="#{lb_id}">{img_tag}</a>'
        gallery_html = re.sub(r'<a[^>]*><img[^>]+/></a>', single_img, gallery_html)
        return f'<div class="gallery">{gallery_html}</div>'

    content_html = re.sub(r'<div class="gallery">(.*?)</div>', gallery_img_replace, content_html, flags=re.DOTALL)

    # Generate lightbox overlays
    for i, img in enumerate(images):
        lb_id = f'lb-{slug}-{i}'
        prev_link = f'<a href="#lb-{slug}-{i-1}" class="lightbox-prev">&lsaquo;</a>' if i > 0 else ''
        next_link = f'<a href="#lb-{slug}-{i+1}" class="lightbox-next">&rsaquo;</a>' if i < total - 1 else ''
        caption_html = f'<div class="lightbox-caption">{img["caption"]}</div>' if img['caption'] else ''
        counter = f'<div class="lightbox-counter">{i+1} / {total}</div>'

        title_escaped = html.escape(title)
        lightboxes += f'''<div id="{lb_id}" class="lightbox">
  <a href="#" class="lightbox-title">{title_escaped}</a>
  <a href="#" class="lightbox-close">&times;</a>
  {prev_link}
  {next_link}
  <div class="lightbox-content">
    <img src="{img['src']}" alt="" />
    {caption_html}
    {counter}
  </div>
</div>
'''

    return content_html + '\n' + lightboxes


def make_static_page_html(page, attachments):
    """Generate full HTML for a static page (books, glossary, etc.)."""
    title = html.escape(page['title'])
    content_html = convert_content(page['content'], attachments)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FSB | {title}</title>
  <link rel="stylesheet" href="../style.css" />
</head>
<body>
  <div class="sky-bg"></div>
  <nav class="navbar">
    <div class="navbar-inner">
      <a class="navbar-brand" href="../">Flying Summers Brothers</a>
      <input type="checkbox" id="nav-toggle" class="nav-toggle" />
      <label for="nav-toggle" class="nav-toggle-label"></label>
      {make_nav_links(from_pages=True)}
    </div>
  </nav>
{SEARCH_DIALOG}
  <main>
    <div class="page-content card">
      <h1>{title}</h1>
      {content_html}
    </div>
  </main>
  <footer>
    <p>&copy; Colin &amp; Adam Summers</p>
  </footer>
</body>
</html>
'''


def make_post_html(post, attachments, prev_post=None, next_post=None):
    """Generate full HTML for a single post page."""
    title = html.escape(post['title'])
    date_display = format_date(post['date'])
    excerpt = html.escape(get_excerpt(post['content']))
    content_html = convert_content(post['content'], attachments)
    content_html = add_lightbox(content_html, post['slug'], post['title'])
    author = post['author']
    show_author = (author == 'stingraydoctor')
    author_display = 'Adam Summers' if author == 'stingraydoctor' else 'Colin Summers'

    cats_html = ''
    if post['categories']:
        cat_links = ', '.join(
            f'<a href="../categories/{c.lower().replace(" ", "-")}.html">{html.escape(c)}</a>'
            for c in post['categories'] if c != 'Uncategorized'
        )
        if cat_links:
            cats_html = f'<span class="post-categories">{cat_links}</span>'

    # Comments
    comments_html = ''
    comment_count = len(post['comments'])
    if comment_count > 0:
        comments_items = ''
        for c in post['comments']:
            c_author = html.escape(c['author'])
            c_date = format_date_short(c['date'])
            c_content = c['content']
            # Basic formatting for comment content
            c_content = re.sub(r'\n\n+', '</p><p>', c_content)
            c_content = re.sub(r'\n', '<br>', c_content)
            comments_items += f'''<div class="comment">
<div class="comment-meta"><strong>{c_author}</strong> &middot; {c_date}</div>
<div class="comment-body"><p>{c_content}</p></div>
</div>
'''
        word = 'comment' if comment_count == 1 else 'comments'
        comments_html = f'''
<div class="comments-section">
  <input type="checkbox" id="comments-toggle" class="comments-toggle" />
  <label for="comments-toggle" class="comments-toggle-label">{comment_count} {word}</label>
  <div class="comments-dialog">
    <label for="comments-toggle" class="comments-close">&times;</label>
    <h3>{comment_count} {word}</h3>
    {comments_items}
  </div>
  <label for="comments-toggle" class="comments-overlay"></label>
</div>'''

    # Post navigation
    nav_html = ''
    nav_parts = []
    if next_post:
        nav_parts.append(f'<a href="{next_post["slug"]}.html" class="post-nav-prev">&larr; {html.escape(next_post["title"])}</a>')
    if prev_post:
        nav_parts.append(f'<a href="{prev_post["slug"]}.html" class="post-nav-next">{html.escape(prev_post["title"])} &rarr;</a>')
    if nav_parts:
        nav_html = '<nav class="post-nav">' + ''.join(nav_parts) + '</nav>'

    byline = ''
    if show_author:
        byline = f' &middot; <span class="post-author">{author_display}</span>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FSB | {title}</title>
  <meta name="description" content="{excerpt}" />
  <meta name="author" content="{author_display}" />
  <link rel="stylesheet" href="../style.css" />
</head>
<body>
  <div class="sky-bg"></div>
  <nav class="navbar">
    <div class="navbar-inner">
      <a class="navbar-brand" href="../">Flying Summers Brothers</a>
      <input type="checkbox" id="nav-toggle" class="nav-toggle" />
      <label for="nav-toggle" class="nav-toggle-label"></label>
      {make_nav_links(prefix='../')}
    </div>
  </nav>
{SEARCH_DIALOG}
  <main>
    <article class="post card">
      <header class="post-header">
        <h1>{title}</h1>
        <div class="post-meta">
          <time datetime="{post['date'][:10]}">{date_display}</time>{byline}
          {cats_html}
        </div>
      </header>
      <div class="post-content">
        {content_html}
      </div>
      {comments_html}
    </article>
    {nav_html}
  </main>
  <footer>
    <p>&copy; Colin &amp; Adam Summers</p>
  </footer>
</body>
</html>
'''


def make_post_card(post, attachments, prefix=''):
    """Generate a single post card HTML. prefix adjusts relative paths ('' for root, '../' for subdirs)."""
    title = html.escape(post['title'])
    date_short = format_date_short(post['date'])
    excerpt = get_excerpt(post['content'])
    first_img = get_first_image(post['content'], attachments, slug=post['slug'])

    no_image = not first_img

    img_html = ''
    if first_img:
        img_html = f'<div class="card-image"><a href="{prefix}posts/{post["slug"]}.html"><img src="{R2_BASE}/{first_img}" alt="" loading="lazy" /></a></div>'

    card = f'''    <article class="post-card card">
      <div class="card-header">
        <time datetime="{post['date'][:10]}">{date_short}</time>
        <h2><a href="{prefix}posts/{post['slug']}.html">{title}</a></h2>
      </div>
      {img_html}
      <div class="card-body">
        <p class="excerpt">{html.escape(excerpt)}</p>
        <a href="{prefix}posts/{post['slug']}.html" class="read-more">Read more &rarr;</a>
      </div>
    </article>
'''
    return card, no_image


POSTS_PER_PAGE = 10


def make_index_html(posts, attachments):
    """Generate paginated blog index pages. Returns list of (relative_path, html) tuples."""
    import math
    total_pages = max(1, math.ceil(len(posts) / POSTS_PER_PAGE))
    pages = []
    no_image_posts = []

    for page_num in range(1, total_pages + 1):
        start = (page_num - 1) * POSTS_PER_PAGE
        end = start + POSTS_PER_PAGE
        page_posts = posts[start:end]

        # Determine path prefix for this page
        if page_num == 1:
            prefix = ''
            rel_path = 'index.html'
            stylesheet = 'style.css'
            banner_prefix = ''
            home_href = './'
            pages_prefix = ''
        else:
            prefix = '../'
            rel_path = f'page/{page_num}.html'
            stylesheet = '../style.css'
            banner_prefix = '../'
            home_href = '../'
            pages_prefix = '../'

        cards = ''
        for p in page_posts:
            card, no_image = make_post_card(p, attachments, prefix=prefix)
            cards += card
            if no_image:
                no_image_posts.append(p['slug'])

        # Build pagination nav
        # Show: first, prev, current, next, last — with ... for gaps
        def page_href(pn):
            if pn == 1:
                return f'{prefix}index.html' if prefix else 'index.html'
            return f'{prefix}page/{pn}.html' if prefix else f'page/{pn}.html'

        def page_date(pn):
            idx = (pn - 1) * POSTS_PER_PAGE
            return format_date_short(posts[idx]['date'])

        def make_page_nav(css_class='page-nav'):
            if total_pages <= 1:
                return ''
            # 5 slots: latest, prev, ..., next, first
            slots = []
            # Slot 1: latest (page 1) — skip if we're on page 1
            if page_num > 1:
                slots.append(('latest', f'<a href="{page_href(1)}">{page_date(1)}</a>'))
            else:
                slots.append(('', ''))
            # Slot 2: prev — skip if same as latest or doesn't exist
            if page_num > 2:
                slots.append(('prev', f'<a href="{page_href(page_num - 1)}">{page_date(page_num - 1)}</a>'))
            else:
                slots.append(('', ''))
            # Slot 3: current position
            slots.append(('', '<span class="current">...</span>'))
            # Slot 4: next — skip if same as first or doesn't exist
            if page_num < total_pages - 1:
                slots.append(('next', f'<a href="{page_href(page_num + 1)}">{page_date(page_num + 1)}</a>'))
            else:
                slots.append(('', ''))
            # Slot 5: first (oldest, last page) — skip if we're on it
            if page_num < total_pages:
                slots.append(('first', f'<a href="{page_href(total_pages)}">{page_date(total_pages)}</a>'))
            else:
                slots.append(('', ''))

            slot_html = ''
            for label, content in slots:
                label_el = f'<span class="pn-label">{label}</span>' if label else ''
                slot_html += f'<div class="pn-slot">{content}{label_el}</div>'
            return f'    <nav class="{css_class}">{slot_html}</nav>\n'

        nav_bottom = make_page_nav('page-nav')
        nav_top = make_page_nav('page-nav page-nav-top') if page_num > 1 else ''

        page_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Flying Summers Brothers</title>
  <meta name="description" content="Adam and Colin take to the sky." />
  <meta name="author" content="Colin Summers" />
  <link rel="stylesheet" href="{stylesheet}" />
</head>
<body>
  <div class="sky-bg"></div>
  <nav class="navbar">
    <div class="navbar-inner">
      <a class="navbar-brand" href="{home_href}">Flying Summers Brothers</a>
      <input type="checkbox" id="nav-toggle" class="nav-toggle" />
      <label for="nav-toggle" class="nav-toggle-label"></label>
      {make_nav_links(prefix=prefix)}
    </div>
  </nav>
{SEARCH_DIALOG}
  <header class="site-banner">
    <img id="banner" src="{R2_BASE}/covers/banners/masthead1.jpg" alt="Flying Summers Brothers" />
  </header>
  <script>document.getElementById('banner').src='{R2_BASE}/covers/banners/masthead'+Math.ceil(Math.random()*10)+'.jpg';</script>
  <main class="blog-index">
{nav_top}{cards}
{nav_bottom}  </main>
  <footer>
    <p>&copy; Colin &amp; Adam Summers</p>
  </footer>
</body>
</html>
'''
        pages.append((rel_path, page_html))

    if no_image_posts:
        print(f"WARNING: Posts with no image: {', '.join(no_image_posts)}")

    return pages


def download_image(url, dest_path):
    """Download a single image."""
    dest_path = Path(dest_path)
    if dest_path.exists():
        return True
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    url = clean_url(url)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(dest_path, 'wb') as f:
                f.write(resp.read())
        return True
    except (urllib.error.URLError, OSError) as e:
        print(f"  FAILED: {url} -> {e}")
        return False


def collect_image_urls(posts, attachments):
    """Collect all image URLs needed for a set of posts."""
    urls = set()
    for p in posts:
        content = p['content']
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', content):
            urls.add(clean_url(m.group(1)))
        for m in re.finditer(r'<a[^>]+href="([^"]+\.(jpg|jpeg|png|gif))"', content, re.I):
            urls.add(clean_url(m.group(1)))
        for m in re.finditer(r'\[gallery[^\]]*ids="([^"]+)"', content):
            for aid in m.group(1).split(','):
                url = attachments.get(aid.strip())
                if url:
                    urls.add(url)
    return [u for u in urls if 'flyingsummers.com/wp-content/uploads/' in u]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--download-images', action='store_true')
    args = parser.parse_args()

    load_img_dims_cache()
    attachments = load_attachments()
    posts = parse_posts(XML_PATH, count=args.count)
    print(f"Processing {len(posts)} posts...")

    # Download images
    if args.download_images:
        image_urls = collect_image_urls(posts, attachments)
        print(f"Downloading {len(image_urls)} images...")
        ok, fail = 0, 0
        for url in sorted(image_urls):
            local = wp_url_to_local(url)
            if local:
                dest = BASE / local
                if download_image(url, dest):
                    ok += 1
                else:
                    fail += 1
        print(f"Images: {ok} downloaded, {fail} failed")

    # Generate post pages
    POSTS_DIR.mkdir(exist_ok=True)
    for i, post in enumerate(posts):
        prev_post = posts[i - 1] if i > 0 else None
        next_post = posts[i + 1] if i < len(posts) - 1 else None
        post_html = make_post_html(post, attachments, prev_post, next_post)
        path = POSTS_DIR / f"{post['slug']}.html"
        with open(path, 'w') as f:
            f.write(post_html)
    print(f"Generated {len(posts)} post pages in posts/")

    # Generate paginated index pages
    index_pages = make_index_html(posts, attachments)
    PAGE_DIR = BASE / 'page'
    PAGE_DIR.mkdir(exist_ok=True)
    for rel_path, page_html in index_pages:
        out_path = BASE / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            f.write(page_html)
        print(f"Generated {rel_path}")

    # Generate static pages
    PAGES_DIR = BASE / 'pages'
    PAGES_DIR.mkdir(exist_ok=True)
    wp_pages = parse_pages(XML_PATH)
    page_count = 0
    for pg in wp_pages:
        page_html = make_static_page_html(pg, attachments)
        path = PAGES_DIR / f"{pg['slug']}.html"
        with open(path, 'w') as f:
            f.write(page_html)
        page_count += 1
    print(f"Generated {page_count} static pages in pages/")

    save_img_dims_cache()
    print(f"Image dimension cache: {len(_img_dims_cache)} entries")

    # Generate sitemap.xml
    site = 'https://flyingsummers.com'
    urls = [f'  <url><loc>{site}/</loc></url>']
    for p in posts:
        urls.append(f'  <url><loc>{site}/posts/{p["slug"]}.html</loc><lastmod>{p["date"][:10]}</lastmod></url>')
    for pg in wp_pages:
        urls.append(f'  <url><loc>{site}/pages/{pg["slug"]}.html</loc></url>')
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(urls) + '\n</urlset>\n'
    with open(BASE / 'sitemap.xml', 'w') as f:
        f.write(sitemap)
    print(f"Generated sitemap.xml ({len(urls)} URLs)")


if __name__ == '__main__':
    main()
