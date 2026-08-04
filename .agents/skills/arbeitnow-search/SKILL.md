---
name: arbeitnow-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Germany, find German
  job listings, look up a specific job posting on Arbeitnow, or asks about the German
  tech/remote job market. Invoke for open positions, vacancies, and hiring across any
  sector, with particular strength in software, data, and remote-friendly roles. Trigger
  phrases: arbeitnow, jobs in germany, german jobs, jobsuche deutschland, stellenangebote,
  offene stellen, ledige stillinger deutschland, jobs berlin, jobs munich, jobs münchen,
  jobs hamburg, jobs frankfurt, remote jobs germany, homeoffice jobs, IT jobs deutschland,
  softwareentwickler job, data engineer deutschland, find a job in germany.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/arbeitnow-search/cli/src/cli.ts *)
---

# Arbeitnow Search Skill

Search live job listings from [Arbeitnow](https://www.arbeitnow.com)'s free, public
Job Board API — Germany-focused tech and remote-friendly roles. No authentication,
no API key, **zero runtime dependencies** — it runs with just `bun`.

> Arbeitnow's own API terms: "This is a free public API for jobs, please do not abuse."
> This skill honors that — no more than the documented pagination, no bulk scraping.

## When to use this skill

- Search for job openings in Germany by keyword, job title, city, or "Remote"
- Filter by recency (posted today / last 7 / 14 / 30 days)
- Get the full description of a specific job listing

## Commands

### Search job listings

```bash
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keyword search, matched against title/tags/job-type.
- `--location <text>` / `-l <text>` — a city (e.g. `"Berlin"`, `"München"`) or `"Remote"`. Matches client-side against the job's location field (or the `remote` flag for `"Remote"`). **German and English city names are treated as equivalent** — `-l "München"` also matches postings Arbeitnow stores as `"Munich"`, `"Munich, GER"`, or `"Munich Office"`, and likewise for Köln/Cologne, Nürnberg/Nuremberg, etc. The `location` field is free text written by each employer, so both spellings genuinely coexist in one API page; without the alias list a `"München"` search missed most Munich jobs.
- `--jobage <days>` — posted within N days: `1`, `7`, `14`, `30`. Omit for all postings.
- `--page <n>` — 1-indexed page into the upstream API. Page size varies (~100-175 jobs); filtering happens **within** the fetched page, so a narrow query on one page may need `--page 2`, `3`, ... to find more matches. There is no native server-side search filter on this API (confirmed empirically — query params are ignored), which is why filtering is client-side.
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts detail <url|slug> [--format json|plain]
```

Prefer passing the job's `url` from a search result — Arbeitnow has no per-slug API
lookup, so a bare slug is resolved by scanning the first 3 API pages only (bounded;
may miss a job that has scrolled off recent pages).

## Usage examples

```bash
# Data engineer roles in Berlin, last 14 days
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search -q "data engineer" -l "Berlin" --jobage 14 --format table

# Any remote-friendly role
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search -q "python" -l "Remote" --format table

# Browse everything on page 2 (no keyword)
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts search --page 2 --format table

# Full detail for a specific job (URL from a search result)
bun run .agents/skills/arbeitnow-search/cli/src/cli.ts detail "https://www.arbeitnow.com/jobs/companies/acme-gmbh/backend-engineer-berlin-1" --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing URLs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Data is from Arbeitnow's public `job-board-api` — no credentials required, jobs refresh hourly.
- Listings are overwhelmingly German cities and remote/"Homeoffice" postings — this is a Germany-market source, not a global aggregator.
- `search` returns each job's **full description already inlined** — `detail` re-fetches the job's own page and parses its embedded schema.org `JobPosting` JSON-LD block, which is more stable than scraping page markup directly.
- Descriptions may contain German umlaut/typographic HTML entities (`&auml;`, `&szlig;`, `&rsquo;`, etc.) — the parser decodes these, not just the basic XML-escape set.
- **Narrow query + city can legitimately return zero.** Because both filters are client-side over a single API page, a specific keyword combined with a specific city may match nothing on that page even though such jobs exist further in. If a search comes back empty, retry with `--page 2`, or drop one of the two filters, before concluding the portal is broken.
