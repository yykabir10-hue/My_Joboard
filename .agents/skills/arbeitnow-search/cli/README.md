# arbeitnow-cli

CLI for searching jobs on [Arbeitnow](https://www.arbeitnow.com)'s free public
Job Board API — Germany-focused tech and remote-friendly roles.

**Data source**: `https://www.arbeitnow.com/api/job-board-api` (search) + the job's own page's embedded JSON-LD (`detail`).
**Authentication**: None required.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

## Installation

```bash
cd .agents/skills/arbeitnow-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings |
| `detail` | Fetch full detail for a single job listing (by URL or slug) |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Data engineer roles in Berlin, last 14 days
bun run src/cli.ts search -q "data engineer" -l "Berlin" --jobage 14 --format table

# Remote-friendly roles
bun run src/cli.ts search -q "python" -l "Remote" --format table

# Full detail for one job
bun run src/cli.ts detail "https://www.arbeitnow.com/jobs/companies/acme-gmbh/backend-engineer-berlin-1" --format plain
```

See `../SKILL.md` for the full flag reference and `../url-reference.md` for the endpoint details.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keywords, matched against title/tags/job-type. |
| `--location` | `-l` | City (e.g. `"Berlin"`) or `"Remote"`. Client-side filter. |
| `--jobage` | | Posted within N days: `1`, `7`, `14`, `30`. |
| `--page` | | 1-indexed page into the upstream API. |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

## Tests

```bash
bun run typecheck
bun run test
```
