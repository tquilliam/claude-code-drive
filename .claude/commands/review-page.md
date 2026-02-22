---
description: Run a multi-agent review of a single web page
argument-hint: <url>
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Task, WebFetch
---

# Single Page Review

You are reviewing a single page: $ARGUMENTS

Follow the orchestration workflow defined in CLAUDE.md.

## Step 1: Fetch Page

Fetch the page content:
```bash
python3 scripts/fetch_page.py $ARGUMENTS
```

Read the JSON output to get the domain, slug, and cache path.

## Step 2: Version Detection

Extract domain and slug from the fetch output.
1. Use Glob to find files matching `reviews/[domain]/pages/[slug]/review-v*-*.md`
2. Extract the highest version number
3. New version = highest + 1 (or 1 if first review)
4. Record today's date in YYYY-MM-DD format

## Step 3: Change Detection (Only for re-reviews, i.e. version ≥ 2)

If this is a re-review (version number is 2 or higher):

1. Compute SHA256 checksum of the cached HTML file at `reviews/[domain]/.cache/[slug].html`
2. Read `reviews/[domain]/.cache/checksums.json` if it exists
3. Check if the slug exists in checksums.json:
   - **If checksum matches**: Skip analysis. The page HTML has not changed.
     - Note: "Page unchanged since v[N-1]. Scores carried forward."
     - Proceed directly to Step 5 (consolidation with carry-forward)
   - **If checksum differs or slug not found**: The page has changed or is new.
     - Proceed to Step 4 (analysis)

## Step 4: Analysis (if page changed or is new)

Read `.claude/agents/combined-agent.md`

Spawn ONE subagent using the Task tool (subagent_type: "general-purpose"):

Prompt structure:
```
You are the combined website analysis agent.

URL: [url]
Page HTML is saved at: [cache_path]
Focus areas: [SEO, CRO, Content]

[Full contents of .claude/agents/combined-agent.md]
```

The agent will analyze all three sections (SEO, CRO, Content) and return structured markdown.

## Step 5: Consolidation

1. Read `templates/page-review.md`
2. Fill in the template:
   - For unchanged pages: use the "Review Status: Unchanged" block with carried-forward scores
   - For changed/new pages: merge the combined agent's analysis into the appropriate sections
3. Calculate overall score:
   - All three sections: SEO (35%) + CRO (35%) + Content (30%), rounded to nearest integer
   - (If any section was not analyzed, adjust weights proportionally)
4. If re-review: compute score changes from the previous version
5. Create the output directory: `reviews/[domain]/pages/[slug]/`
6. Write to `reviews/[domain]/pages/[slug]/review-v[N]-[date].md`
7. After successful analysis, update `reviews/[domain]/.cache/checksums.json` with the new checksum for this slug

## Step 5: Upload

```bash
python3 scripts/gdrive_upload.py reviews/[domain]/ --version [N]
```

Skip if gdrive is not available.

## Step 6: Present Results

Show the full consolidated review to the user with:
- Overall score and category scores
- Top priority action items
- Link to Google Drive (if uploaded)
- Local file path
