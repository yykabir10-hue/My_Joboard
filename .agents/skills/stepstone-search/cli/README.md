# stepstone-cli

CLI for searching jobs on [StepStone.de](https://www.stepstone.de), one of Germany's
largest job boards.

**Data source**: server-rendered `stepstone.de/jobs/...` search pages (`search`); the job's own detail page + embedded JSON-LD (`detail`, unverified — see `../url-reference.md`).
**Authentication**: None required.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

## Installation

```bash
cd .agents/skills/stepstone-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings |
| `detail` | Fetch full detail for a single job (by URL). **Unverified** — see SKILL.md. |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Data engineer roles in Berlin, last 14 days
bun run src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 14 --format table

# Nationwide, German-language query
bun run src/cli.ts search -q "Softwareentwickler" --format table

# Full detail for one job
bun run src/cli.ts detail "https://www.stepstone.de/stellenangebote--...-inline.html" --format plain
```

See `../SKILL.md` for the full flag reference and `../url-reference.md` for the endpoint investigation notes.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keywords (title/skill/role). |
| `--location` | `-l` | German city. Omit for nationwide. |
| `--jobage` | | Posted within N days. Approximate (relative-time text, no exact timestamp). |
| `--page` | | 1-indexed page (25 results/page). |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

## Tests

```bash
bun run typecheck
bun run test
```
