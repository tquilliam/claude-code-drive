# Website Analysis System

## Project Overview
Multi-agent website analysis system using a combined specialist subagent (SEO, CRO, Content) coordinated by triage/director logic to produce comprehensive, versioned website reviews. Supports single pages, sections, and focused analysis with change detection to skip re-analyzing unchanged pages.

## Architecture
- **Triage**: Parses user briefs, determines task type (page, section, focused), detects changes
- **Specialists**: One combined subagent (`combined-agent`) analyzes individual pages, running only requested sections
- **Director**: Consolidates specialist outputs into versioned deliverables, uploads to Google Drive

## Commands
- `/review-page <url>` — Single page review
- `/brief <description>` — General brief intake (triage routes to single page, section, or focused analysis)

---

## Triage Logic

When a review request is received:

1. **Extract domain** from the URL (e.g., `https://example.com/about` → `example.com`)
2. **Discover pages**:
   - For `/review-page`: Run `python3 scripts/fetch_page.py <url>` to fetch one page
   - For `/brief` (single page): Extract URL and run `fetch_page.py`
   - For `/brief` (section): Detect path prefix, ask user (root only vs all sub-pages), then run `fetch_page.py` or `crawl_site.py --path-prefix [prefix]`
   - For `/brief` (focused): Route based on URL and focus areas
3. **Detect version**: Check `reviews/[domain]/pages/[slug]/` or `reviews/[domain]/` for existing review files
   - List files matching `reviews/[domain]/pages/[slug]/review-v*-*.md` (single page) or `reviews/[domain]/site-overview-v*-*.md` (multi-page)
   - Extract version numbers via pattern `v(\d+)`
   - `new_version = max(existing_versions) + 1` (or 1 if none exist)
4. **Check for changes** (re-reviews only):
   - Compute SHA256 checksum of each page's cached HTML
   - Compare to stored checksums in `reviews/[domain]/.cache/checksums.json`
   - Skip analysis for unchanged pages; carry forward previous scores
5. **Spawn combined subagent** for changed/new pages (details below)

## Spawning the Combined Agent

Use the Task tool to spawn the combined subagent. For each page being analyzed:

- Spawn **1 combined subagent per page** (analyzes SEO, CRO, and/or Content based on focus_areas)
- **Batch pages**: Process up to 6 pages at a time (6 pages x 1 agent = 6 concurrent, under the 7-agent limit)
- Each subagent receives in its prompt:
  1. The page URL
  2. The path to cached HTML: `reviews/[domain]/.cache/[slug].html`
  3. The focus_areas list: e.g., `["SEO", "CRO", "Content"]` or a subset like `["CRO"]`
  4. The full combined agent framework (read from `.claude/agents/combined-agent.md`)
- Subagent skips any sections not in focus_areas and returns only the requested analysis

**Subagent prompt template:**
```
You are the combined website analysis agent.

URL: [url]
Page HTML is saved at: [cache_path]
Focus areas: [focus_areas list, e.g., ["SEO", "CRO", "Content"]]

[Paste full contents of .claude/agents/combined-agent.md here]
```

The agent will analyze only the sections listed in focus_areas. Omit sections not requested.

## Director Logic

After ALL combined subagents complete for ALL pages:

1. **Create folder structure**:
   ```
   reviews/[domain]/
   ├── .cache/                           # Cached HTML (from fetch/crawl)
   ├── .cache/checksums.json             # SHA256 checksums of cached HTML
   ├── site-overview-v[N]-[YYYY-MM-DD].md  (multi-page reviews only)
   ├── recommendations-v[N]-[YYYY-MM-DD].md  (multi-page reviews only)
   └── pages/
       └── [page-slug]/
           └── review-v[N]-[YYYY-MM-DD].md
   ```

2. **For each page**: Merge the combined agent report into a single review file
   - Use the template at `templates/page-review.md`
   - Include only the sections that were analyzed (omit unanalyzed sections)
   - Calculate overall score based on sections analyzed:
     - All three: SEO (35%) + CRO (35%) + Content (30%)
     - Two sections: equal weight (50%/50%)
     - One section: that section's score
   - If re-review: include score changes from previous version
   - If page unchanged: use "Review Status: Unchanged" block instead of analysis blocks

3. **For multi-page reviews**: Generate site overview and recommendations
   - Use `templates/site-overview.md` and `templates/recommendation.md`
   - Compute site-wide averages (accounting for partial analyses)
   - Identify cross-cutting issues (issues appearing on 3+ pages)
   - Identify best and worst performing pages per category

4. **Update checksums**:
   - Write `reviews/[domain]/.cache/checksums.json` with SHA256 checksums for all successfully analyzed pages
   - Format: `{ "[slug]": { "checksum": "[sha256hex]", "date": "YYYY-MM-DD", "version": N } }`

5. **Upload to Google Drive**:
   ```
   python3 scripts/gdrive_upload.py reviews/[domain]/ --version [N]
   ```

6. **Present summary** to user: task type, page count, score(s), top action items, Drive URL

## Version Management

- Version numbers are integers starting at 1
- Filename pattern: `review-v[N]-[YYYY-MM-DD].md`
- Site overview: `site-overview-v[N]-[YYYY-MM-DD].md`
- Re-reviews preserve all previous versions alongside new ones
- Score change tracking: compare current scores to most recent previous version
- New pages (not in previous review) get v1 regardless of site version
- Removed pages (in previous review but not current) noted in site overview

## Change Detection

On re-reviews (version ≥ 2), before spawning analysis agents:

1. **Compute checksums**: Calculate SHA256 of each page's cached HTML
2. **Load stored checksums**: Read `reviews/[domain]/.cache/checksums.json` if it exists
   - Format: `{ "[slug]": { "checksum": "[sha256hex]", "date": "YYYY-MM-DD", "version": N } }`
3. **Compare per page**:
   - **Not in checksums.json**: New page → run full analysis
   - **Checksum matches**: HTML unchanged → skip analysis, carry forward previous score
   - **Checksum differs**: HTML changed → run full analysis
4. **Update checksums** after successful analysis (do NOT update if analysis fails — preserve for retry)

This avoids re-analyzing unchanged pages, significantly reducing AI usage on large re-reviews.

## Section Analysis

When `/brief` detects a section-scoped request (e.g., "/blinds section"):

1. **Ask the user**: Confirm whether to analyze just the section root page or all pages under that path
2. **Root page only**: Run `python3 scripts/fetch_page.py [section_root_url]` and follow single-page workflow
3. **All sub-pages**: Run `python3 scripts/crawl_site.py [base_url] --path-prefix [section_path] --max-depth 2`
   - The `--path-prefix` flag filters discovered pages to only those under the specified path
   - Limits depth to 2 by default to keep crawls fast
   - Then proceed with change detection and analysis for discovered pages

## Page Slug Convention

Convert URL path to slug:
- Strip leading/trailing slashes
- Replace `/` with `-`
- Lowercase everything
- Root path (`/`) → `homepage`
- Example: `/about/team/` → `about-team`
- Example: `/products/widget-pro` → `products-widget-pro`

## Error Handling

- If a subagent fails: retry once. If it fails again, note the failure in the page review and continue with available results
- If crawler finds 50+ pages: warn the user and ask for confirmation before proceeding
- If gdrive is not authenticated: print setup instructions and skip upload (local files still created)

## Google Drive Structure

```
Website Reviews/           (root folder in Drive)
└── [domain]/
    ├── site-overview-v[N]-[date].md
    ├── recommendations-v[N]-[date].md
    └── pages/
        └── [slug]/
            └── review-v[N]-[date].md
```
