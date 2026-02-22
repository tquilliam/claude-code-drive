---
description: Run a social media performance review for a brand using Meta API data
argument-hint: <brand-slug> [--focus paid|organic|all] [--days 30]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Task
---

# Social Media Review

Run a comprehensive social media analysis for a brand using Meta API campaign and organic post data.

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
- `brand-slug` (required) — the slug of the brand to analyze
- `--focus` (optional, default: `all`) — which sections to analyze: `paid`, `organic`, or `all`
- `--days` (optional, default: `30`) — how many days of data to fetch

Map focus values:
- `all` → `["Paid", "Organic"]`
- `paid` → `["Paid"]`
- `organic` → `["Organic"]`

## Step 2: Load Brand File

Use Glob to find `brands/$brand-slug.md`:
```
glob brands/$brand-slug.md
```

If not found:
```
glob brands/*.md
```

List available brands and ask the user which one they meant.

If found, read the brand file and extract from YAML frontmatter:
- `brand` — brand name
- `slug` — brand slug
- `meta_account_id` — Ad Account ID
- `meta_page_id` — Page ID

Store these values for use in later steps.

## Step 3: Auth Check

Run the auth check script:
```bash
python3 scripts/meta_auth_check.py brands/$brand-slug.md
```

Parse the JSON output:
- If `valid: false` → print error message with link to `META_SETUP.md` and **STOP**
- If `valid: true` → continue

If there are `missing_permissions`, print a warning that those sections may fail.

## Step 4: Version Detection

Determine the version number for this review:

If focus includes "Paid":
```
glob social-reviews/$brand-slug/paid-analysis-v*-*.md
```

If focus includes "Organic":
```
glob social-reviews/$brand-slug/organic-concepts-v*-*.md
```

Extract all version numbers (the `N` in `v[N]`):
- New version = max(existing_versions) + 1
- If no existing files: new version = 1

Record today's date in YYYY-MM-DD format.

## Step 5: Fetch Meta Data

Run the data fetcher:
```bash
python3 scripts/fetch_meta_data.py brands/$brand-slug.md --days $days
```

Parse the JSON manifest output and extract:
- `files.account` — path to account JSON
- `files.campaigns` — path to campaigns JSON
- `files.adsets` — path to ad sets JSON
- `files.ads` — path to ads JSON
- `files.organic` — path to organic JSON
- `date_range.since` and `date_range.until` — the date range analyzed

If the fetch fails, print the error and **STOP**.

## Step 5.5: Creative Assets

After successfully fetching Meta data, ask the user:

> "Do you have any ad creative or design assets you'd like to review alongside this analysis? (e.g., images, PDFs, mockups)"

**If "No":**
- Set `creative_files = []`
- Do NOT add "Creative" to focus_areas
- Continue to Step 6

**If "Yes":**
- Ask: "What is the folder path to your creative assets? (e.g., `/Users/thom/Desktop/Ads/VictoryBlinds` or relative path like `creative/victory-blinds`)"
- Use Glob to discover all supported files in that folder (any depth): pattern `**/*.{jpg,jpeg,png,gif,webp,pdf,mp4,mov,webm}`
- If no files found: warn the user ("No supported image or PDF files found in that path") and set `creative_files = []`
- If files found:
  - Display the discovered files to the user with file counts
  - Store `creative_files = [list of discovered paths]`
  - Add "Creative" to focus_areas

## Step 6: Spawn Social Agent

Read `.claude/agents/social-agent.md` (full file contents).

Spawn ONE subagent via the Task tool with `subagent_type: "general-purpose"`:

```
You are the social media analysis agent.

**Brand Context**
Brand: [brand name from Step 2]
Slug: [slug from Step 2]
Brand context file: brands/[slug].md

**Data Files**
Account data: [account JSON path from Step 5]
Campaign data: [campaigns JSON path from Step 5]
Ad Set data: [adsets JSON path from Step 5]
Ad-level data: [ads JSON path from Step 5]
Organic data: [organic JSON path from Step 5]

[If creative_files is not empty:]
**Creative Asset Files**
[List each file path from creative_files, one per line]

**Analysis Parameters**
Date range: [since] to [until] ([N] days)
Focus areas: [focus_areas list from Steps 1 and 5.5 — e.g., ["Paid", "Organic"], or ["Paid", "Creative"], etc.]

---

[Full raw contents of .claude/agents/social-agent.md]
```

Wait for the agent to complete. It will return structured markdown with:
- Paid section (if "Paid" in focus areas)
- Organic section (if "Organic" in focus areas)
- Analysis Summary block

## Step 7: Consolidation

Once the agent returns:

1. **For Paid** (if included):
   - Read `templates/social-paid-analysis.md`
   - Merge the agent's Paid output into the template
   - Replace all placeholders with actual data/findings
   - Calculate overall score: (Campaign Efficiency + Creative Performance + Audience & Placement + Account Health) / 4, rounded to nearest integer
   - If this is a re-review (version > 1): compute score changes from the previous paid-analysis file
   - If "Creative" was in focus_areas and agent returned a Creative Asset Review section:
     - Merge the Creative Asset Review section into the template immediately after `## Creative Performance`
   - Write to: `social-reviews/$brand-slug/paid-analysis-v$version-$date.md`

2. **For Organic** (if included):
   - Read `templates/social-organic-concepts.md`
   - Merge the agent's Organic output (all concept blocks) into the template
   - Replace Performance Context and Paid Creative Signals sections
   - Write to: `social-reviews/$brand-slug/organic-concepts-v$version-$date.md`

3. **Create output directory** if it doesn't exist:
   ```bash
   mkdir -p social-reviews/$brand-slug
   ```

4. **Update checksums** — write `social-reviews/$brand-slug/.cache/checksums.json`:
   ```json
   {
     "paid": {
       "checksum": "[SHA256 of paid-analysis JSON output, if analyzed]",
       "date": "[YYYY-MM-DD]",
       "version": [N]
     },
     "organic": {
       "checksum": "[SHA256 of organic-concepts JSON output, if analyzed]",
       "date": "[YYYY-MM-DD]",
       "version": [N]
     }
   }
   ```

## Step 8: Upload to Google Drive

```bash
python3 scripts/gdrive_upload.py social-reviews/$brand-slug/ --version $version
```

Capture the output:
- If upload succeeds: note the Drive URL
- If gdrive is not installed: note that upload was skipped and provide instructions

## Step 9: Present Results

Display a summary to the user:

```
## Social Media Review Complete ✓

**Brand**: [Brand Name]
**Date Range**: [SINCE] to [UNTIL]
**Version**: v[N]
**Review Type**: [Paid / Organic / Paid + Organic / Paid + Creative / etc.]

### Key Metrics

[If Paid included]
- Total Spend: $[X]
- Account ROAS: [X]x
- Average CPA: $[X]
- Best Campaign: [Name] ($[X] CPA)
- Worst Campaign: [Name] ($[X] CPA)
- Overall Paid Score: [X]/10

[If Organic included]
- Concepts Generated: [X]
- Format Mix: [X] Reels, [X] Carousels, [X] Static

[If Creative included]
- Assets Reviewed: [X] files
- Creative Score: [X]/10

### Top 3 Priority Actions

1. [Highest priority from Paid or Organic]
2. [Action 2]
3. [Action 3]

### Files

**Local:**
- [social-reviews/$brand-slug/paid-analysis-v[N]-[DATE].md]
- [social-reviews/$brand-slug/organic-concepts-v[N]-[DATE].md]

**Google Drive:**
- [URL from gdrive upload]

---

Next steps:
- For paid optimizations, use the Creative Hypothesis to test new concepts
- For organic content, prioritize the Reels with emotional narratives
- Schedule a follow-up review in 30 days to measure impact
```

## Error Handling

- **Auth fails**: Print setup instructions and stop (don't proceed to fetch)
- **Fetch fails**: Print error details and stop (don't proceed to agent)
- **Agent fails**: Retry once. If it fails again, note the failure in the output file and continue with available results
- **Drive upload unavailable**: Note in results but don't block local file creation

## Notes

- All file paths should be relative to `/Users/thom/Claude Code Drive/` (the working directory)
- Dates should always be in YYYY-MM-DD format
- Scores are integer values 1-10
- Currency should always be labeled (e.g., $X AUD)
