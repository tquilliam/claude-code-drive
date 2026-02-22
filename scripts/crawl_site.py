#!/usr/bin/env python3
"""
Full site crawler for the website analysis system.

Discovers all pages on a site via:
1. Sitemap.xml parsing (including sitemap indexes)
2. robots.txt Sitemap directives
3. Link following from the homepage (BFS, configurable depth)

Usage:
    python3 scripts/crawl_site.py <url> [--max-pages 100] [--max-depth 3] [--delay 1.0]

Output:
    reviews/[domain]/discovered-pages.json  — page manifest
    reviews/[domain]/.cache/[slug].html     — cached HTML per page
"""

import argparse
import gzip
import json
import os
import re
import sys
import time
from datetime import date
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.robotparser import RobotFileParser
import ssl

# Create an SSL context that doesn't verify certificates (macOS compatibility)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE
import xml.etree.ElementTree as ET


USER_AGENT = "WebsiteAnalysisBot/1.0 (SEO/CRO/Content Review Tool)"


def normalize_url(url):
    """Normalize a URL for deduplication."""
    parsed = urlparse(url)
    # Remove fragments
    path = parsed.path.rstrip("/") or "/"
    # Reconstruct without fragment, with consistent trailing slash handling
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def url_to_slug(url, base_domain):
    """Convert a URL path to a filesystem-safe slug."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "homepage"
    # Replace slashes with hyphens, lowercase
    slug = path.replace("/", "-").lower()
    # Remove non-alphanumeric chars except hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "homepage"


def fetch_url(url, timeout=15):
    """Fetch a URL and return (content_bytes, content_type, status_code, final_url)."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urlopen(req, timeout=timeout, context=SSL_CONTEXT)
        content = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        # Handle gzip
        if resp.headers.get("Content-Encoding") == "gzip" or url.endswith(".gz"):
            try:
                content = gzip.decompress(content)
            except Exception:
                pass
        return content, content_type, resp.status, resp.url
    except HTTPError as e:
        return None, "", e.code, url
    except (URLError, OSError) as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}", file=sys.stderr)
        return None, "", 0, url


class LinkExtractor(HTMLParser):
    """Extract <a href> links from HTML."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def extract_links(html, base_url):
    """Extract same-domain links from HTML content."""
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc

    parser = LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        return []

    links = set()
    for href in parser.links:
        # Skip non-http links
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        # Same domain only
        if parsed.netloc != base_domain:
            continue
        # Skip non-page resources
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext in (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js",
                    ".zip", ".xml", ".json", ".ico", ".woff", ".woff2", ".ttf", ".eot",
                    ".mp4", ".mp3", ".avi", ".mov", ".webp", ".webm"):
            continue
        links.add(normalize_url(full_url))

    return links


def discover_from_sitemap(base_url):
    """Discover pages from sitemap.xml and robots.txt."""
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls = set()

    # Collect sitemap URLs to try
    sitemap_urls = [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
    ]

    # Check robots.txt for Sitemap directives
    robots_url = f"{base}/robots.txt"
    content, _, status, _ = fetch_url(robots_url)
    if content and status == 200:
        text = content.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url not in sitemap_urls:
                    sitemap_urls.append(sitemap_url)

    # Parse all sitemaps
    for sitemap_url in sitemap_urls:
        urls.update(parse_sitemap(sitemap_url))

    return urls


def parse_sitemap(sitemap_url, depth=0):
    """Parse a sitemap XML and return discovered URLs. Handles sitemap indexes recursively."""
    if depth > 3:  # Prevent infinite recursion
        return set()

    urls = set()
    content, _, status, _ = fetch_url(sitemap_url)
    if not content or status != 200:
        return urls

    try:
        text = content.decode("utf-8", errors="replace")
        # Remove namespace prefixes for simpler parsing
        text = re.sub(r'xmlns\s*=\s*"[^"]*"', "", text)
        root = ET.fromstring(text)
    except ET.ParseError:
        return urls

    # Check if this is a sitemap index
    for sitemap_elem in root.iter("sitemap"):
        loc = sitemap_elem.find("loc")
        if loc is not None and loc.text:
            child_urls = parse_sitemap(loc.text.strip(), depth + 1)
            urls.update(child_urls)

    # Extract page URLs
    for url_elem in root.iter("url"):
        loc = url_elem.find("loc")
        if loc is not None and loc.text:
            urls.add(normalize_url(loc.text.strip()))

    return urls


def discover_from_links(start_url, max_depth, max_pages, delay, robot_parser, path_prefix=None):
    """Discover pages by following links from the start URL (BFS)."""
    discovered = {}  # url -> depth
    queue = [(normalize_url(start_url), 0)]
    visited = set()

    while queue and len(discovered) < max_pages:
        url, depth = queue.pop(0)

        if url in visited:
            continue
        if depth > max_depth:
            continue

        # Check robots.txt
        if robot_parser:
            try:
                if not robot_parser.can_fetch(USER_AGENT, url):
                    print(f"  [SKIP] Blocked by robots.txt: {url}")
                    visited.add(url)
                    continue
            except Exception:
                pass

        visited.add(url)
        print(f"  [CRAWL] Depth {depth}: {url}")

        content, content_type, status, final_url = fetch_url(url)
        if not content or status != 200:
            continue

        # Only process HTML pages
        if "text/html" not in content_type.lower():
            continue

        html = content.decode("utf-8", errors="replace")
        discovered[url] = {"depth": depth, "html": html, "status": status}

        # Extract and queue links
        if depth < max_depth:
            links = extract_links(html, url)
            for link in links:
                if link not in visited and len(discovered) + len(queue) < max_pages * 2:
                    # Check path prefix if specified
                    if path_prefix:
                        parsed_link = urlparse(link)
                        normalized_prefix = path_prefix.rstrip("/")
                        if not parsed_link.path.rstrip("/").startswith(normalized_prefix):
                            continue
                    queue.append((link, depth + 1))

        time.sleep(delay)

    return discovered


def setup_robots_parser(base_url):
    """Set up robots.txt parser."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    # Fetch robots.txt manually with SSL context
    content, _, status, _ = fetch_url(robots_url)
    if content and status == 200:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(content.decode("utf-8", errors="replace").splitlines())
        return rp
    return None


def main():
    parser = argparse.ArgumentParser(description="Crawl a website and discover all pages")
    parser.add_argument("url", help="The starting URL to crawl")
    parser.add_argument("--max-pages", type=int, default=100, help="Maximum pages to discover (default: 100)")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum link-follow depth (default: 3)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--path-prefix", type=str, default=None, help="Only include pages whose path starts with this prefix (e.g. /blinds)")
    args = parser.parse_args()

    # Normalize starting URL
    url = args.url
    if not url.startswith("http"):
        url = f"https://{url}"

    parsed = urlparse(url)
    domain = parsed.netloc
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    print(f"[START] Crawling {domain}")
    print(f"  Max pages: {args.max_pages}, Max depth: {args.max_depth}, Delay: {args.delay}s")
    if args.path_prefix:
        print(f"  Path prefix filter: {args.path_prefix}")

    # Set up output directories
    reviews_dir = os.path.join("reviews", domain)
    cache_dir = os.path.join(reviews_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Set up robots.txt parser
    print(f"\n[PHASE 0] Checking robots.txt...")
    robot_parser = setup_robots_parser(base_url)

    # Phase 1: Sitemap discovery
    print(f"\n[PHASE 1] Discovering pages from sitemap...")
    sitemap_urls = discover_from_sitemap(url)
    print(f"  Found {len(sitemap_urls)} URLs from sitemap")

    # Phase 2: Link following
    print(f"\n[PHASE 2] Discovering pages by following links...")
    crawled = discover_from_links(url, args.max_depth, args.max_pages, args.delay, robot_parser, path_prefix=args.path_prefix)
    print(f"  Crawled {len(crawled)} pages via link following")

    # Merge results
    all_urls = set(sitemap_urls) | set(crawled.keys())

    # Fetch any sitemap-only URLs that weren't crawled (up to max_pages limit)
    sitemap_only = sitemap_urls - set(crawled.keys())
    fetched_count = len(crawled)

    for surl in sorted(sitemap_only):
        if fetched_count >= args.max_pages:
            break

        # Check robots.txt
        if robot_parser:
            try:
                if not robot_parser.can_fetch(USER_AGENT, surl):
                    continue
            except Exception:
                pass

        print(f"  [FETCH] Sitemap URL: {surl}")
        content, content_type, status, final_url = fetch_url(surl)
        if content and status == 200 and "text/html" in content_type.lower():
            html = content.decode("utf-8", errors="replace")
            crawled[surl] = {"depth": -1, "html": html, "status": status}
            fetched_count += 1
            time.sleep(args.delay)

    # Build page manifest and save cached HTML
    pages = []
    for page_url in sorted(crawled.keys()):
        # Filter by path prefix if specified
        if args.path_prefix:
            parsed_page = urlparse(page_url)
            normalized_prefix = args.path_prefix.rstrip("/")
            if not parsed_page.path.rstrip("/").startswith(normalized_prefix):
                continue

        info = crawled[page_url]
        slug = url_to_slug(page_url, domain)

        # Save cached HTML
        cache_path = os.path.join(cache_dir, f"{slug}.html")
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(info["html"])

        source = "sitemap" if page_url in sitemap_urls else "link-follow"
        if page_url in sitemap_urls and page_url in crawled:
            source = "sitemap+crawl"

        pages.append({
            "url": page_url,
            "slug": slug,
            "source": source,
            "depth": info["depth"],
            "status": info["status"],
        })

    # Write manifest
    manifest = {
        "domain": domain,
        "base_url": base_url,
        "crawl_date": date.today().isoformat(),
        "total_pages": len(pages),
        "max_pages_limit": args.max_pages,
        "max_depth_limit": args.max_depth,
        "pages": pages,
    }

    manifest_path = os.path.join(reviews_dir, "discovered-pages.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n[DONE] Discovered {len(pages)} pages")
    print(f"  Manifest: {manifest_path}")
    print(f"  Cache: {cache_dir}/")

    if len(pages) >= 50:
        print(f"\n[WARNING] Found {len(pages)} pages. This is a large site.")
        print("  Consider using --max-pages to limit the review scope.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
