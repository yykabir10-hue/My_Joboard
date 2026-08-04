---
name: stepstone-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Germany, find German
  job listings on StepStone, look up a specific job posting, or asks about the German
  job market broadly. Invoke for open positions, vacancies, and hiring across any
  sector or role (software, data, engineering, sales, finance, HR, etc.) in Germany.
  Trigger phrases: stepstone, jobsuche deutschland, stellenangebote, offene stellen,
  jobs deutschland, jobs berlin, jobs münchen, jobs muenchen, jobs hamburg, jobs
  frankfurt, jobs köln, jobs koeln, stellenanzeige, arbeit finden deutschland, softwar
  entwickler stelle, data engineer stelle, find a job in germany, german job search,
  german vacancies.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/stepstone-search/cli/src/cli.ts *)
---

# StepStone Search Skill

Search live job listings from [StepStone.de](https://www.stepstone.de), one of
Germany's largest job boards. No authentication needed. `robots.txt` does not
disallow the current `/jobs/...` search route for generic crawlers (it only blocks a
legacy `/5/...` path), so — unlike LinkedIn/Xing — this does not carry a
personal-use-only warning; keep volume reasonable regardless.

## When to use this skill

- Search for job openings anywhere in Germany, or scoped to a specific city
- Filter by recency (approximate — see Notes)
- Browse a specific job's basic info from search results (title, company, location, URL)

## Commands

### Search job listings

```bash
bun run .agents/skills/stepstone-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (job title, skill, role), e.g. `"Data Engineer"`.
- `--location <text>` / `-l <text>` — a German city, e.g. `"Berlin"`, `"München"`. Omit for a nationwide search.
- `--jobage <days>` — posted within N days: `1`, `7`, `14`, `30`. **Approximate**: StepStone's cards expose only a relative German string ("vor 5 Tagen") with no exact timestamp, converted to an approximate ISO date client-side.
- `--page <n>` — 1-indexed page (25 results/page).
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/stepstone-search/cli/src/cli.ts detail <url> [--format json|plain]
```

**Known limitation:** pass the job's full `url` from a search result (there is no
bare-ID lookup). During development, StepStone's individual job-detail pages
(`/stellenangebote--...-inline.html`) refused every automated fetch attempt with
HTTP/2 connection resets — not a 403/429, a protocol-level block distinct from the
search-page behavior, which fetches cleanly. `detail` is implemented against the
standard schema.org `JobPosting` JSON-LD pattern (the same one confirmed working on
`arbeitnow-search`) and may work depending on your network path, but this was **not**
live-verified. `search` results already carry title/company/location/URL, so most
`/scrape` usage does not depend on `detail` working for this portal.

## Usage examples

```bash
# Data engineer roles in Berlin, last 14 days
bun run .agents/skills/stepstone-search/cli/src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 14 --format table

# German-language query, no city (nationwide)
bun run .agents/skills/stepstone-search/cli/src/cli.ts search -q "Softwareentwickler" --format table

# City with an umlaut — pass it exactly, the CLI transliterates internally
bun run .agents/skills/stepstone-search/cli/src/cli.ts search -q "Product Manager" -l "München" --format table

# Full detail for one job (URL from a search result)
bun run .agents/skills/stepstone-search/cli/src/cli.ts detail "https://www.stepstone.de/stellenangebote--...-inline.html" --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing URLs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- StepStone's own `/public-api/resultlist/` JSON endpoint 403s on a direct call (bot-protected); this CLI parses the server-rendered search HTML instead, same approach as `jobindex-search`.
- Field extraction anchors on stable `data-at="job-item-*"` attributes, not the CSS class names (which are Emotion/Next.js build hashes and not guaranteed stable). A card whose markup doesn't match the expected icon-then-text shape yields `null` for that field rather than risking a wrong value borrowed from a neighboring field — confirmed against real search pages during development (0 nulls across 50 real cards).
- Descriptions/titles/companies may contain German umlaut and typographic HTML entities (`&auml;`, `&szlig;`, `&rsquo;`, etc.) — decoded beyond the basic XML-escape set.
- 25 results per page.
