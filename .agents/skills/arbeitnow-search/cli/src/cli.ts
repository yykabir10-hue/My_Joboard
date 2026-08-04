#!/usr/bin/env bun
// Self-contained CLI for searching jobs on Arbeitnow's public Job Board API
// (Germany-focused tech & remote listings). No external CLI framework, so it
// runs anywhere `bun` is available with zero install beyond the repo clone.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", l: "location", n: "limit" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
      const next = argv[i + 1]
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true
      } else {
        flags[key] = next
        i++
      }
    } else {
      ;(flags._ as string[]).push(a)
    }
  }
  return flags
}

const HELP = `arbeitnow-cli — search jobs on Arbeitnow (Germany-focused tech & remote)

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <url|slug> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Keywords, matched against title/tags/job-type. Recommended.
  --location, -l <text>   City name (e.g. "Berlin", "Munich") or "Remote". Filters
                          client-side on the job's location field.
  --jobage <days>         Posted within N days: 1, 7, 14, 30. Default: all.
  --page <n>              1-indexed page into the upstream API (~100-175 jobs/page,
                          size varies). Filtering happens within the fetched page.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

DETAIL
  Pass the job's "url" from a search result (preferred — Arbeitnow has no per-slug
  API lookup) or a bare slug (resolved via a bounded 3-page scan; may not be found
  if it's fallen off the first pages).

EXAMPLES
  bun run src/cli.ts search -q "data engineer" -l "Berlin" --jobage 14 --format table
  bun run src/cli.ts search -q "python" -l "Remote" --format table
  bun run src/cli.ts detail "https://www.arbeitnow.com/jobs/companies/acme/backend-engineer-42" --format plain

No authentication required — this is Arbeitnow's free public Job Board API.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  if (cmd === "search") {
    const fmt = (flags.format as string) || "json"

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n")
        return null
      }
      return val
    }

    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage)
      if (v === null) return 1
      flags.jobage = String(v)
    }
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page)
      if (v === null) return 1
      flags.page = String(v)
    }
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit)
      if (v === null) return 1
      flags.limit = String(v)
    }

    const opts: SearchOpts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      location: typeof flags.location === "string" ? flags.location : undefined,
      jobage: flags.jobage ? parseInt(flags.jobage as string, 10) : 9999,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      limit: flags.limit ? parseInt(flags.limit as string, 10) : undefined,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires a <url|slug>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = {
      id,
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main()
  .then((code) => {
    // Do not call process.exit here. When stdout is a pipe, writes are
    // asynchronous, so exiting immediately discards whatever has not drained
    // yet - silently truncating output at the 64KB pipe buffer. It is invisible
    // interactively (TTY writes are synchronous) and invisible with `>` (file
    // writes are too); it only bites when piped, which is what automation does.
    // Setting exitCode lets the runtime flush and exit on its own.
    process.exitCode = code
  })
  .catch((e) => {
    process.stderr.write(
      JSON.stringify({
        error: e instanceof Error ? e.message : String(e),
        code: "INTERNAL_ERROR",
      }) + "\n",
    )
    process.exitCode = 1
  })
