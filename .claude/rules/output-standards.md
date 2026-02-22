# Output Standards

All review output files must follow these conventions:

## Formatting
- All output files are valid Markdown (no raw HTML)
- Use fenced code blocks with language hints for technical recommendations
- Tables use proper Markdown table syntax with alignment

## Scoring
- All scores use integer scale 1-10
- Overall page score depends on sections analyzed:
  - **All three sections**: SEO (35%) + CRO (35%) + Content (30%), rounded to nearest integer
  - **Two sections**: equal weight (50%/50%), rounded to nearest integer
  - **One section**: that section's score = overall score
- Score change tracking: show "+N" or "-N" compared to previous version, "New" for first review, "—" for unanalyzed sections
- Unchanged pages (HTML checksum match): show "Carried forward from v[N]" in the change column

## Priority Levels
- **Critical**: Immediate action required — significant negative impact
- **High**: Should be addressed soon — noticeable impact
- **Medium**: Worth addressing — incremental improvement
- **Low**: Nice to have — minor enhancement

## Recommendations Format
Every recommendation must include:
- **Description**: What to do (actionable, specific)
- **Effort**: Low / Medium / High
- **Impact**: Low / Medium / High
- **Affected Pages**: Which pages this applies to

## Dates
- Format: YYYY-MM-DD throughout all files and filenames

## File Naming
- Page reviews: `review-v[N]-[YYYY-MM-DD].md`
- Site overviews: `site-overview-v[N]-[YYYY-MM-DD].md`
- Recommendations: `recommendations-v[N]-[YYYY-MM-DD].md`

## Page Slugs
- Lowercase, hyphens only, no special characters
- Root path → `homepage`
- Strip leading/trailing slashes, replace `/` with `-`

## Partial Analysis

When a review covers fewer than all three sections (SEO, CRO, Content):
- Always list which sections were analyzed in the Scores Overview table
- Omit section analysis blocks that were not analyzed (do not show empty or placeholder blocks)
- The overall score reflects only the analyzed sections using the weighting rules above
- In site-level reviews, note pages with partial analysis and list their analyzed sections

## Change Detection

Checksum storage: `reviews/[domain]/.cache/checksums.json`

Format:
```json
{
  "[slug]": {
    "checksum": "[sha256hex]",
    "date": "YYYY-MM-DD",
    "version": N
  }
}
```

Rules:
- Checksum is SHA256 of the UTF-8 decoded HTML string saved in `.cache/[slug].html`
- Updated after successful analysis only
- If analysis fails after retry, the old checksum is preserved (page will be re-analyzed on next run)
- Unchanged pages carry forward their previous scores without re-analysis
