#!/usr/bin/env bun
// Self-contained CLI for the Bundesagentur für Arbeit (German Federal Employment
// Agency) public Jobsuche API — Germany's official, largest job database. No
// external CLI framework, so it runs anywhere `bun` is available with zero install
// beyond the repo clone. No authentication beyond the public, published client key.

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

const HELP = `arbeitsagentur-cli — search jobs on the Bundesagentur für Arbeit Jobsuche
                     (Germany's official federal job board — the largest German job database)

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <referenznummer|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Keywords (job title, skill, role), e.g. "Data Engineer".
                          Maps to the API's 'was' parameter.
  --location, -l <text>   German city / region, e.g. "Berlin", "München".
                          Maps to 'wo'. Umlauts are fine — no transliteration needed.
  --jobage <days>         Posted within N days (server-side 'veroeffentlichtseit').
                          Default: all.
  --radius <km>           Search radius around --location, in km ('umkreis').
  --page <n>              1-indexed page. Default 1.
  --size <n>              Results per API page (max 100). Default 25.
  --limit, -n <n>         Cap results emitted (client-side).
  --all-offer-types       Include self-employment / training-course listings.
                          By default only real employment (angebotsart=1) is returned.
  --format <fmt>          json (default) | table | plain.

DETAIL
  Pass the Referenznummer from a search result (e.g. 10000-1183204759-S) or a full
  arbeitsagentur.de/jobsuche/jobdetail/... URL.

EXAMPLES
  bun run src/cli.ts search -q "Data Engineer" -l "Berlin" --jobage 7 --format table
  bun run src/cli.ts search -q "Softwareentwickler" -l "München" --radius 25 --format table
  bun run src/cli.ts detail 10000-1183204759-S --format plain

Official German government open API — no personal-use restriction, no scraping.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
    const val = parseInt(raw as string, 10)
    if (isNaN(val)) {
      process.stderr.write(
        JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n",
      )
      return null
    }
    return val
  }

  if (cmd === "search") {
    const fmt = (flags.format as string) || "json"

    for (const name of ["jobage", "page", "limit", "size", "radius"]) {
      if (flags[name] !== undefined) {
        const v = parseIntFlag(name, flags[name])
        if (v === null) return 1
        flags[name] = String(v)
      }
    }

    const size = flags.size ? parseInt(flags.size as string, 10) : 25
    if (size < 1 || size > 100) {
      process.stderr.write(
        JSON.stringify({ error: "--size must be between 1 and 100 (API page-size limit)", code: "BAD_ARG" }) + "\n",
      )
      return 1
    }

    const opts: SearchOpts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      location: typeof flags.location === "string" ? flags.location : undefined,
      jobage: flags.jobage ? parseInt(flags.jobage as string, 10) : 9999,
      radiusKm: flags.radius ? parseInt(flags.radius as string, 10) : undefined,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      size,
      limit: flags.limit ? parseInt(flags.limit as string, 10) : undefined,
      jobsOnly: flags["all-offer-types"] !== true,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires a <referenznummer|url>", code: "NO_ID" }) + "\n")
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
