import { SEARCH_URL, apiFetch, jobageToThreshold, toJobCard, writeError, type JobCard } from "../helpers.js"

export interface SearchOpts {
  query?: string
  location?: string
  jobage: number
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function matchesQuery(card: JobCard, query: string): boolean {
  const q = query.toLowerCase()
  return (
    card.title.toLowerCase().includes(q) ||
    card.tags.some((t) => t.toLowerCase().includes(q)) ||
    card.jobTypes.some((t) => t.toLowerCase().includes(q))
  )
}

/**
 * German and English names for the same city, plus umlaut/ASCII spellings. Arbeitnow's
 * `location` field is free text supplied by each employer, so the same city genuinely
 * appears as "München", "Munich", and "Munich, GER" within a single API page
 * (confirmed live). Without this, `-l "München"` silently misses every posting that
 * happened to spell it in English.
 */
const CITY_ALIASES: string[][] = [
  ["münchen", "munchen", "muenchen", "munich"],
  ["köln", "koln", "koeln", "cologne"],
  ["nürnberg", "nurnberg", "nuernberg", "nuremberg"],
  ["wien", "vienna"],
  ["zürich", "zurich", "zuerich"],
  ["frankfurt am main", "frankfurt"],
  ["deutschland", "germany"],
  ["braunschweig", "brunswick"],
  ["hannover", "hanover"],
]

/** All spellings equivalent to the given location, including the input itself. */
export function locationVariants(location: string): string[] {
  const l = location.trim().toLowerCase()
  const group = CITY_ALIASES.find((g) => g.includes(l))
  return group ? Array.from(new Set([l, ...group])) : [l]
}

function matchesLocation(card: JobCard, location: string): boolean {
  const l = location.trim().toLowerCase()
  if (l === "remote") return card.remote || /remote|homeoffice/i.test(card.location || "")
  const haystack = (card.location || "").toLowerCase()
  return locationVariants(l).some((v) => haystack.includes(v))
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 28).padEnd(28)
    const date = (c.date || "—").slice(0, 10)
    return `${c.id.slice(0, 30).padEnd(30)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(30) + " " + "TITLE".padEnd(42) + " " + "COMPANY".padEnd(26) + " " + "LOCATION".padEnd(28) + " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const response = await apiFetch(`${SEARCH_URL}?page=${opts.page}`)
    if (!response) {
      writeError("Arbeitnow API returned no data for this page", "NOT_FOUND")
      return 1
    }

    let cards = response.data.map(toJobCard)

    if (opts.query) cards = cards.filter((c) => matchesQuery(c, opts.query as string))
    if (opts.location) cards = cards.filter((c) => matchesLocation(c, opts.location as string))

    const threshold = jobageToThreshold(opts.jobage)
    if (threshold !== null) {
      cards = cards.filter((c) => (c.date ? new Date(c.date).getTime() / 1000 >= threshold : false))
    }

    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"}${c.remote ? " · remote" : ""} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          { meta: { count: cards.length, page: opts.page }, results: cards },
          null,
          2,
        ) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}
