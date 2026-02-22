#!/usr/bin/env python3
"""
Google Drive upload script for the website analysis system.

Uploads review files to Google Drive using the gdrive CLI tool.
Creates a mirrored folder structure in Drive.

Usage:
    python3 scripts/gdrive_upload.py reviews/[domain]/ [--version N]

Prerequisites:
    - gdrive CLI installed: https://github.com/glotlabs/gdrive
    - gdrive authenticated: run `gdrive account add` first

Folder structure in Drive:
    Website Reviews/
    └── [domain]/
        ├── site-overview-v[N]-[date].md
        ├── recommendations-v[N]-[date].md
        └── pages/
            └── [slug]/
                └── review-v[N]-[date].md
"""

import argparse
import json
import os
import re
import subprocess
import sys


DRIVE_ROOT_FOLDER = "Website Reviews"
CACHE_FILENAME = ".gdrive-ids.json"


def run_gdrive(args):
    """Run a gdrive command and return stdout. Raises on failure."""
    cmd = ["gdrive"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  [ERROR] gdrive {' '.join(args)}: {result.stderr.strip()}", file=sys.stderr)
            return None
        return result.stdout.strip()
    except FileNotFoundError:
        print("[ERROR] gdrive CLI not found. Install it from: https://github.com/glotlabs/gdrive", file=sys.stderr)
        print("  brew install glotlabs/tap/gdrive  (macOS)", file=sys.stderr)
        print("  Then run: gdrive account add", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] gdrive command timed out: {' '.join(args)}", file=sys.stderr)
        return None


def check_gdrive_auth():
    """Check if gdrive is authenticated."""
    result = run_gdrive(["account", "list"])
    if result is None or not result.strip():
        print("[ERROR] gdrive is not authenticated.", file=sys.stderr)
        print("  Run: gdrive account add", file=sys.stderr)
        sys.exit(1)
    return True


def load_id_cache(reviews_dir):
    """Load the Drive folder ID cache."""
    cache_path = os.path.join(reviews_dir, CACHE_FILENAME)
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    return {}


def save_id_cache(reviews_dir, cache):
    """Save the Drive folder ID cache."""
    cache_path = os.path.join(reviews_dir, CACHE_FILENAME)
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)


def find_or_create_folder(name, parent_id=None):
    """Find a folder by name under a parent, or create it."""
    # Search for existing folder
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    search_args = ["files", "list", "--query", query, "--print-only-id"]
    result = run_gdrive(search_args)

    if result and result.strip():
        # Return the first matching folder ID
        folder_id = result.strip().split("\n")[0].strip()
        if folder_id:
            print(f"  [FOUND] Folder '{name}': {folder_id}")
            return folder_id

    # Create the folder
    create_args = ["files", "mkdir", name]
    if parent_id:
        create_args.extend(["--parent", parent_id])

    result = run_gdrive(create_args)
    if result:
        # Extract folder ID from output
        # gdrive mkdir output format varies, try to extract ID
        folder_id = result.strip().split("\n")[0].strip()
        # If the output contains more info, try to parse just the ID
        match = re.search(r"([a-zA-Z0-9_-]{20,})", folder_id)
        if match:
            folder_id = match.group(1)
        print(f"  [CREATED] Folder '{name}': {folder_id}")
        return folder_id

    print(f"  [ERROR] Failed to create folder '{name}'", file=sys.stderr)
    return None


def upload_file(filepath, parent_id):
    """Upload a file to a Drive folder."""
    filename = os.path.basename(filepath)
    result = run_gdrive(["files", "upload", "--parent", parent_id, filepath])
    if result:
        print(f"  [UPLOADED] {filename}")
        return True
    else:
        print(f"  [FAILED] {filename}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Upload review files to Google Drive")
    parser.add_argument("reviews_dir", help="Path to the domain reviews directory (e.g., reviews/example.com/)")
    parser.add_argument("--version", type=int, help="Only upload files matching this version number")
    args = parser.parse_args()

    reviews_dir = args.reviews_dir.rstrip("/")
    if not os.path.isdir(reviews_dir):
        print(f"[ERROR] Directory not found: {reviews_dir}", file=sys.stderr)
        sys.exit(1)

    # Extract domain from path
    domain = os.path.basename(reviews_dir)
    print(f"[START] Uploading reviews for {domain} to Google Drive")

    # Check prerequisites
    check_gdrive_auth()

    # Load folder ID cache
    cache = load_id_cache(reviews_dir)

    # Create/find root folder
    print("\n[SETUP] Creating folder structure in Drive...")
    if "root" in cache:
        root_id = cache["root"]
        print(f"  [CACHED] Root folder: {root_id}")
    else:
        root_id = find_or_create_folder(DRIVE_ROOT_FOLDER)
        if not root_id:
            sys.exit(1)
        cache["root"] = root_id

    # Create/find domain folder
    domain_cache_key = f"domain:{domain}"
    if domain_cache_key in cache:
        domain_id = cache[domain_cache_key]
        print(f"  [CACHED] Domain folder: {domain_id}")
    else:
        domain_id = find_or_create_folder(domain, root_id)
        if not domain_id:
            sys.exit(1)
        cache[domain_cache_key] = domain_id

    # Create/find pages folder
    pages_cache_key = f"pages:{domain}"
    pages_dir = os.path.join(reviews_dir, "pages")
    pages_id = None
    if os.path.isdir(pages_dir):
        if pages_cache_key in cache:
            pages_id = cache[pages_cache_key]
            print(f"  [CACHED] Pages folder: {pages_id}")
        else:
            pages_id = find_or_create_folder("pages", domain_id)
            if pages_id:
                cache[pages_cache_key] = pages_id

    # Save cache before uploading
    save_id_cache(reviews_dir, cache)

    # Upload files
    print(f"\n[UPLOAD] Uploading files...")
    uploaded = 0
    failed = 0

    # Version filter pattern
    version_pattern = f"-v{args.version}-" if args.version else None

    # Upload top-level files (site overview, recommendations)
    for filename in sorted(os.listdir(reviews_dir)):
        filepath = os.path.join(reviews_dir, filename)
        if not os.path.isfile(filepath):
            continue
        if not filename.endswith(".md"):
            continue
        if filename.startswith("."):
            continue
        if version_pattern and version_pattern not in filename:
            continue

        if upload_file(filepath, domain_id):
            uploaded += 1
        else:
            failed += 1

    # Upload page review files
    if pages_id and os.path.isdir(pages_dir):
        for slug_dir in sorted(os.listdir(pages_dir)):
            slug_path = os.path.join(pages_dir, slug_dir)
            if not os.path.isdir(slug_path):
                continue

            # Create/find slug folder in Drive
            slug_cache_key = f"slug:{domain}:{slug_dir}"
            if slug_cache_key in cache:
                slug_id = cache[slug_cache_key]
            else:
                slug_id = find_or_create_folder(slug_dir, pages_id)
                if slug_id:
                    cache[slug_cache_key] = slug_id
                    save_id_cache(reviews_dir, cache)

            if not slug_id:
                print(f"  [SKIP] Could not create folder for {slug_dir}", file=sys.stderr)
                continue

            # Upload review files in this slug directory
            for filename in sorted(os.listdir(slug_path)):
                filepath = os.path.join(slug_path, filename)
                if not os.path.isfile(filepath) or not filename.endswith(".md"):
                    continue
                if version_pattern and version_pattern not in filename:
                    continue

                if upload_file(filepath, slug_id):
                    uploaded += 1
                else:
                    failed += 1

    # Save final cache
    save_id_cache(reviews_dir, cache)

    print(f"\n[DONE] Uploaded {uploaded} files, {failed} failed")
    if domain_id:
        print(f"  Drive folder: https://drive.google.com/drive/folders/{domain_id}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
