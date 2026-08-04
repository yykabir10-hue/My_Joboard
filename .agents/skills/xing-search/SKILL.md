---
name: xing-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Germany or the wider
  DACH region on Xing, find job listings, or look up a specific Xing job posting.
  Invoke for open positions, vacancies, and hiring across any sector or role. Trigger
  phrases: xing, xing jobs, jobs auf xing, jobsuche deutschland, stellenangebote,
  offene stellen, jobs berlin, jobs münchen, jobs muenchen, jobs hamburg, jobs
  frankfurt, jobs köln, jobs koeln, jobs österreich, jobs schweiz, softwareentwickler
  stelle, data engineer stelle, find a job in germany, german job search, dach jobs.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/xing-search/cli/src/cli.ts *)
---

# Xing Search Skill

Search live job listings from [Xing](https://www.xing.com), a leading professional
network for the German-speaking (DACH) market. No authentication needed to read
search results or job descriptions.

## ⚠️ Personal use only

This uses Xing's public job-search pages; Xing's `robots.txt` disallows `/jobs/search`
and `/jobs/search?*` for generic crawlers, and automated access is against Xing's
Terms of Service. **Keep volume low and don't use it commercially or for bulk data
collection.** Run it on your own responsibility — same posture the repo already
ships for `linkedin-search`.

## When to use this skill

- Search for job openings in Germany/DACH by keyword, job title, or city
- Filter by recency where Xing provides a posting date (see Notes — not all listings have one)
- Get the full description of a specific job listing

## Commands

### Search job listings

```bash
bun run .agents/skills/xing-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (job title, skill, role), e.g. `"Data Engineer"`.
- `--location <text>` / `-l <text>` — a city, e.g. `"Berlin"`, `"München"`. Optional.
- `--jobage <days>` — posted within N days: `1`, `7`, `14`, `30`. No working server-side date filter was found (tested `sort=date`, no effect) — this filters client-side on each card's `<time>` value; cards Xing shows with no date at all are excluded rather than guessed at.
- `--page <n>` — 1-indexed page.
- `--limit <n>` / `-n <n>` — cap total results emitted (client-side).
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/xing-search/cli/src/cli.ts detail <url> [--format json|plain]
```

Pass the job's full `url` from a search result — Xing has no bare-ID lookup route.
Unlike `stepstone-search`'s `detail`, this one is fully live-verified: the individual
job page embeds a complete schema.org `JobPosting` (title, full description,
employment type, industry, location) as JSON-LD with no login wall.

## Usage examples

```bash
# Data engineer roles in Berlin, last 14 days
bun run .agents/skills/xing-search/cli/src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 14 --format table

# German-language query, nationwide
bun run .agents/skills/xing-search/cli/src/cli.ts search -q "Produktmanager" --format table

# Full detail for one job
bun run .agents/skills/xing-search/cli/src/cli.ts detail "https://www.xing.com/jobs/berlin-senior-software-engineer-155853218" --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing URLs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- Field extraction anchors on stable `data-testid`/`data-xds` attributes, not the CSS class names (styled-components build hashes, not guaranteed stable across Xing deployments).
- Sponsored/promoted listings that redirect through a third-party ad tracker (e.g. `jometer.com`) instead of a `xing.com/jobs/...` URL are **skipped** — they carry no stable Xing job ID and can't be fetched via `detail`. Confirmed present in real search results (about 1 in 20 during development).
- Some listings show no posting date at all (Xing omits it) — `date` is `null` for those, honestly, rather than guessed. Confirmed live: roughly half of a real result set lacked a `<time>` element.
- A job's location may list several cities (multi-location postings) — these are joined into one comma-separated string, e.g. `"Aschaffenburg, Berlin, Oldenburg"`.
