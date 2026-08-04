---
name: arbeitsagentur-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Germany, find German
  job listings, look up a German job posting, or asks about the German job market.
  This is the German federal employment agency's official job board (Bundesagentur
  für Arbeit / Arbeitsagentur Jobsuche) — the largest job database in Germany, and
  the most reliable German source. Prefer it as the first German portal to query.
  Trigger phrases: arbeitsagentur, agentur für arbeit, bundesagentur, jobbörse,
  jobsuche deutschland, stellenangebote, offene stellen, arbeitsstelle, jobs
  deutschland, jobs berlin, jobs münchen, jobs muenchen, jobs hamburg, jobs
  frankfurt, jobs köln, jobs koeln, arbeit finden, stellensuche, softwareentwickler
  stelle, data engineer stelle, find a job in germany, german job search, german
  vacancies, german employment agency.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts *)
---

# Arbeitsagentur (Bundesagentur für Arbeit) Search Skill

Search live job listings from the **Bundesagentur für Arbeit Jobsuche** — the German
federal employment agency's official job board, and the largest job database in
Germany. This is a genuine public REST API (documented by the
[bundesAPI](https://github.com/bundesAPI/jobsuche-api) community project): no
scraping, no authentication beyond a published public client key, no registration.

**This should normally be your first-choice German portal.** Unlike the HTML-scraping
skills in this fork (`stepstone-search`, `xing-search`), it cannot break from a markup
change or anti-bot escalation, it carries no Terms-of-Service restriction, and it
returns full plain-text descriptions for both `search` and `detail`.

## When to use this skill

- Search for job openings anywhere in Germany, scoped to a city and radius
- Filter by recency using a real **server-side** date filter
- Get the full description of a specific job listing

## Commands

### Search job listings

```bash
bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords (job title, skill, role). Maps to the API's `was`.
- `--location <text>` / `-l <text>` — German city or region, e.g. `"Berlin"`, `"München"`. Maps to `wo`. **Umlauts work as-is** — no transliteration needed (unlike `stepstone-search`).
- `--jobage <days>` — posted within N days. This is a genuine **server-side** filter (`veroeffentlichtseit`), not an approximation — unlike StepStone/Xing, where recency is filtered client-side.
- `--radius <km>` — search radius around `--location` (`umkreis`).
- `--page <n>` — 1-indexed page.
- `--size <n>` — results per API page, max **100**. Default 25.
- `--limit <n>` / `-n <n>` — cap results emitted (client-side).
- `--all-offer-types` — include self-employment and training-course listings. **By default these are excluded** (`angebotsart=1`, regular employment only) — the unfiltered feed mixes in `SELBSTAENDIGKEIT` entries such as `alfatraining` course listings, which are not real vacancies.
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts detail <referenznummer|url> [--format json|plain]
```

Pass the `id` (a *Referenznummer* like `10000-1183204759-S`) from a search result, or
a full `arbeitsagentur.de/jobsuche/jobdetail/...` URL.

## Usage examples

```bash
# Data engineer roles in Berlin posted in the last 7 days
bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 7 --format table

# German-language query, 25 km around Munich
bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts search -q "Softwareentwickler" -l "München" --radius 25 --format table

# Nationwide, large page for a broad sweep
bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts search -q "Projektmanager" --size 100 --format json

# Full detail for one posting
bun run .agents/skills/arbeitsagentur-search/cli/src/cli.ts detail 10000-1183204759-S --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use; also reports `meta.totalAvailable` (full match count, not just this page) |
| `table` | Quick human-readable scanning (`HO` column marks home-office-possible roles) |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process exits with code `1`.

## Notes

- **Endpoint versions are mismatched on purpose**: search uses `pc/v6/jobs`, detail uses `pc/v4/jobdetails`. Each was probed individually — `v4`/`v5` search return 404, and `v5`/`v6` detail return 403. Widely-circulated community examples still show `pc/v4/jobs` for search, which no longer works. See `url-reference.md`.
- **Descriptions are plain text**, with real newlines — no HTML tags and no entity decoding needed, unlike every scraped portal in this fork.
- **A small number of search results have no detail record** and return `NOT_FOUND` (`STELLENANGEBOT_NICHT_GEFUNDEN`) — typically listings syndicated from partner boards, or postings that expired between the search and the detail call. Measured at 0/20 missing in one sample and 1 miss in another, so it's uncommon but real; the CLI reports it cleanly rather than crashing.
- Results carry extra structured signal the scraped portals don't have: home-office flag, full-time/part-time, distance from the searched location, contract duration, start date, and normalized profession names.
- Rate limits were not encountered during development, but the CLI still retries 429/5xx with exponential backoff. It's a public service — keep volume sensible.
