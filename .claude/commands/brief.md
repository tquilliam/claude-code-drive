---
description: Submit a general brief for website analysis tasks
argument-hint: <brief description>
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Task, WebFetch
---

# Brief Intake

The user has submitted the following brief:

$ARGUMENTS

## Triage Process

Analyze the brief to determine:

### 1. Task Type
- **Single page review**: Brief focuses on one specific URL or page
- **Section review**: Brief mentions a path-scoped analysis (e.g., "/blinds section", "all products pages")
- **Focused analysis**: Brief mentions only specific concerns (e.g., "why isn't this converting?", "SEO audit only", "content review")
- **Comparison**: Brief asks to compare pages, versions, or competitors
- **Content creation**: Brief asks for new content recommendations, content strategy

### 2. URLs
- Extract any URLs mentioned in the brief
- If no URL is provided, ask the user for one before proceeding
- If raw HTML or file paths are provided instead of URLs, handle as manual input

### 3. Focus Areas
Determine which specialist analysis sections are needed:
- If the brief mentions SEO-specific concerns (keywords, search, rankings, technical SEO) → `focus_areas: ["SEO"]`
- If the brief mentions conversion/UX concerns (CTAs, forms, trust, flow, layout, persuasion) → `focus_areas: ["CRO"]`
- If the brief mentions content quality concerns (readability, tone, structure, completeness, effectiveness) → `focus_areas: ["Content"]`
- If the brief is general or mentions multiple areas → `focus_areas: ["SEO", "CRO", "Content"]`
- If unclear, default to all three: `focus_areas: ["SEO", "CRO", "Content"]`

### 4. Special Requirements
Note any specific requests:
- Particular deliverable format
- Stakeholder context (who will read this?)
- Competitive analysis needs
- Business goals or target audience info
- Specific pages to prioritize

## Routing by Task Type

### Single Page Review

1. Extract the page URL from the brief (or ask for one if missing)
2. Run: `python3 scripts/fetch_page.py [url]`
3. Parse the JSON output to extract domain, slug, and cache_path
4. Follow the `/review-page` workflow using the combined agent (see Step 3 onward in /review-page command)
   - But set focus_areas based on triage (not always all three)

### Section Review

1. **Detect section brief**: Look for path-like tokens (e.g., `/blinds`, `/products`, `/services`) combined with language suggesting multiple pages ("section", "all [noun] pages", "everything under")
2. If detected, **ask the user**:
   ```
   I've identified a section brief for [/detected-path].

   Would you like to:
   A) Analyze just the section root page (e.g., https://domain[/detected-path])
   B) Crawl and analyze all pages under [/detected-path]/*
   ```
3. Based on user response:
   - **Root page only**: Run `python3 scripts/fetch_page.py https://[domain][/path]` and follow single-page workflow
   - **All sub-pages**:
     - Run: `python3 scripts/crawl_site.py https://[domain] --path-prefix [/path] --max-depth 2`
     - Read manifest at `reviews/[domain]/discovered-pages.json`
     - Proceed with change detection and multi-page analysis (steps below)

### Focused Analysis

1. Extract page URL(s) from brief
2. For single or multiple pages:
   - If single page: Run `python3 scripts/fetch_page.py [url]`
   - If multiple pages: Run `python3 scripts/crawl_site.py [base_url] [options]`
3. Follow change detection and analysis workflow using combined agent with the determined `focus_areas`

### Manual Input

If the user provides raw HTML/content instead of a URL:
1. Save the content to `reviews/[domain-or-project]/.cache/[slug].html`
2. Proceed with specialist analysis as normal
3. Note "Source: Manual Input" in the review output

## Change Detection (for re-reviews of pages/sections)

Before spawning analysis agents:

1. Compute SHA256 checksum of each page's cached HTML
2. Read `reviews/[domain]/.cache/checksums.json` if it exists
3. For each page:
   - **Not in checksums.json** → new page, run full analysis
   - **Checksum matches** → skip analysis, carry forward previous score with note
   - **Checksum differs** → run full analysis
4. After successful analysis → update `checksums.json` with new checksums
   - Format: `{ "[slug]": { "checksum": "[sha256]", "date": "YYYY-MM-DD", "version": N } }`
   - Do NOT update checksums if analysis fails (preserve old value for retry)

## Spawning the Combined Agent

For each page to analyze:

1. Read `.claude/agents/combined-agent.md`
2. Spawn ONE subagent (subagent_type: "general-purpose")

Batching: Up to 6 pages concurrently (one agent per page).

Prompt template:
```
You are the combined website analysis agent.

URL: [url]
Page HTML is saved at: [cache_path]
Focus areas: [focus_areas list, e.g., ["SEO", "CRO", "Content"]]

[Full contents of .claude/agents/combined-agent.md]
```

If focus_areas contains fewer than all three sections, the agent will only analyze those sections and omit the others from its output.

Wait for all agents to complete before proceeding to consolidation.

## Context Enrichment

If the user provides additional context in the brief (target audience, business goals, competitors, brand guidelines, specific pages to prioritize), include this context in the subagent prompts. For example:

```
Additional context from brief:
- Target audience: [audience description]
- Business goal: [goal]
- Competitive context: [context]
- Brand guidelines: [guidelines]

Incorporate this context into your analysis where relevant.
```

## Consolidation

After all analysis agents complete:

1. For single-page briefs: Merge agent output into `templates/page-review.md` and write to `reviews/[domain]/pages/[slug]/review-v[N]-[date].md`
2. For multi-page briefs:
   - Create individual page review files for each page (using `templates/page-review.md`)
   - Create site overview: `reviews/[domain]/site-overview-v[N]-[date].md` (using `templates/site-overview.md`)
   - Create recommendations: `reviews/[domain]/recommendations-v[N]-[date].md` (using `templates/recommendation.md`)
3. Apply scoring formulas based on sections analyzed (see `.claude/rules/output-standards.md`)
4. Update `reviews/[domain]/.cache/checksums.json` with new checksums for analyzed pages

## Google Drive Upload

After consolidation:

```bash
python3 scripts/gdrive_upload.py reviews/[domain]/ --version [N]
```

Skip if gdrive is not available/authenticated. Local files are still created.

## Present Results

Show a summary to the user with:
- Task type (single page, section, focused analysis)
- Total pages analyzed
- Overall score(s)
- Top priority action items
- Link to Google Drive folder (if uploaded)
- Path to local review files
