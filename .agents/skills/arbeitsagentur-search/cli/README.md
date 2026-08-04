# arbeitsagentur-cli

CLI for the **Bundesagentur für Arbeit Jobsuche** — the German federal employment
agency's official job board, and the largest job database in Germany.

**Data source**: `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service` (official public REST API).
**Authentication**: A published public client key (`X-API-Key: jobboerse-jobsuche`) — no registration, no secret.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

Unlike the HTML-scraping portal skills in this fork, this one is API-backed: it can't
break from a markup change, and it carries no Terms-of-Service restriction.

## Installation

```bash
cd .agents/skills/arbeitsagentur-search/cli
bun install   # optional — only installs TypeScript dev types
```

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings |
| `detail` | Fetch a single job's full description (by Referenznummer or URL) |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Data engineer roles in Berlin, last 7 days
bun run src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 7 --format table

# 25 km around Munich, German-language query
bun run src/cli.ts search -q "Softwareentwickler" -l "München" --radius 25 --format table

# Full detail for one posting
bun run src/cli.ts detail 10000-1183204759-S --format plain
```

See `../SKILL.md` for the full flag reference and `../url-reference.md` for the
endpoint investigation notes (including the v6-search / v4-detail version split).

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keywords (`was`). |
| `--location` | `-l` | City/region (`wo`). Umlauts work as-is. |
| `--jobage` | | Posted within N days — genuine server-side filter. |
| `--radius` | | Radius in km around `--location`. |
| `--page` | | 1-indexed page. |
| `--size` | | Results per API page, max 100 (default 25). |
| `--limit` | `-n` | Cap results emitted. |
| `--all-offer-types` | | Include self-employment / training listings (excluded by default). |
| `--format` | | `json` \| `table` \| `plain`. |

## Tests

```bash
bun run typecheck
bun run test
```
