#!/usr/bin/env python3
"""
Single page fetcher for the website analysis system.

Fetches one URL, saves the HTML to the cache, and prints metadata.

Usage:
    python3 scripts/fetch_page.py <url>

Output:
    reviews/[domain]/.cache/[slug].html — cached HTML
    Prints: slug, status code, title, content length
"""

import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import ssl

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


USER_AGENT = "WebsiteAnalysisBot/1.0 (SEO/CRO/Content Review Tool)"


def url_to_slug(url):
    """Convert a URL path to a filesystem-safe slug."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "homepage"
    slug = path.replace("/", "-").lower()
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "homepage"


class TitleExtractor(HTMLParser):
    """Extract the <title> tag content from HTML."""

    def __init__(self):
        super().__init__()
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/fetch_page.py <url>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    if not url.startswith("http"):
        url = f"https://{url}"

    parsed = urlparse(url)
    domain = parsed.netloc
    slug = url_to_slug(url)

    # Set up directories
    reviews_dir = os.path.join("reviews", domain)
    cache_dir = os.path.join(reviews_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Fetch the page
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urlopen(req, timeout=15, context=SSL_CONTEXT)
        content = resp.read()
        status = resp.status
        content_type = resp.headers.get("Content-Type", "")
        final_url = resp.url
    except HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}", "url": url}))
        sys.exit(1)
    except (URLError, OSError) as e:
        print(json.dumps({"error": str(e), "url": url}))
        sys.exit(1)

    html = content.decode("utf-8", errors="replace")

    # Extract title
    title_parser = TitleExtractor()
    try:
        title_parser.feed(html)
    except Exception:
        pass
    title = title_parser.title.strip() or "(no title)"

    # Save cached HTML
    cache_path = os.path.join(cache_dir, f"{slug}.html")
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Print metadata as JSON
    result = {
        "url": url,
        "final_url": final_url,
        "domain": domain,
        "slug": slug,
        "status": status,
        "content_type": content_type,
        "content_length": len(content),
        "title": title,
        "cache_path": cache_path,
    }
    print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
