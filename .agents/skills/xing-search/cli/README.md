# xing-cli

CLI for searching jobs on [Xing](https://www.xing.com), a leading professional
network for the German-speaking (DACH) market.

**Data source**: Xing's public `jobs/search/ki` results page (`search`) and individual job pages' embedded JSON-LD (`detail`).
**Authentication**: None required.
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> **Personal use only.** Xing's robots.txt disallows `/jobs/search`; automated access
> is against Xing's Terms of Service. Keep volume low, don't use it commercially or
> for bulk data collection, and run it on your own responsibility.

## Installation

```bash
cd .agents/skills/xing-search/cli
bun install   # optional — only installs TypeScript dev types
```

The CLI runs without any install because it has zero runtime dependencies.

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings |
| `detail` | Fetch full detail for a single job (by URL). Live-verified. |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
# Data engineer roles in Berlin, last 14 days
bun run src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 14 --format table

# German-language query, nationwide
bun run src/cli.ts search -q "Produktmanager" --format table

# Full detail for one job
bun run src/cli.ts detail "https://www.xing.com/jobs/berlin-senior-software-engineer-155853218" --format plain
```

See `../SKILL.md` for the full flag reference and `../url-reference.md` for the endpoint investigation notes.

## Search flags

| Flag | Alias | Description |
|------|-------|-------------|
| `--query` | `-q` | Keywords (title/skill/role). |
| `--location` | `-l` | City. Optional. |
| `--jobage` | | Posted within N days. Client-side; excludes cards with no date rather than guessing. |
| `--page` | | 1-indexed page. |
| `--limit` | `-n` | Cap results emitted. |
| `--format` | | `json` \| `table` \| `plain`. |

## Tests

```bash
bun run typecheck
bun run test
```
