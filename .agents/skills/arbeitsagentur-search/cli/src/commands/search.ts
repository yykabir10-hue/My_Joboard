import {
  buildSearchUrl,
  fetchJson,
  toJobCard,
  writeError,
  type ApiSearchResponse,
  type JobCard,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  location?: string
  jobage: number
  radiusKm?: number
  page: number
  size: number
  limit?: number
  /** When true, restrict to angebotsart=1 (regular employment). Default true. */
  jobsOnly: boolean
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 40).padEnd(40)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 22).padEnd(22)
    const date = (c.date || "—").slice(0, 10).padEnd(10)
    const ho = c.homeOffice ? "HO" : "  "
    return `${c.id.slice(0, 24).padEnd(24)} ${title} ${company} ${loc} ${date} ${ho}`
  })
  const header =
    "REFERENZNUMMER".padEnd(24) +
    " " +
    "TITLE".padEnd(40) +
    " " +
    "COMPANY".padEnd(26) +
    " " +
    "LOCATION".padEnd(22) +
    " " +
    "DATE".padEnd(10) +
    " HO"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const url = buildSearchUrl({
      query: opts.query,
      location: opts.location,
      jobage: opts.jobage,
      radiusKm: opts.radiusKm,
      page: opts.page,
      size: opts.size,
      offerType: opts.jobsOnly ? 1 : undefined,
    })
    const response = await fetchJson<ApiSearchResponse>(url)
    if (!response) {
      writeError("Arbeitsagentur API returned no data for this query", "NOT_FOUND")
      return 1
    }

    let cards = (response.ergebnisliste ?? [])
      .map(toJobCard)
      .filter((c): c is JobCard => c !== null)

    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"}${c.homeOffice ? " · home office" : ""} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          {
            meta: {
              count: cards.length,
              page: opts.page,
              // The API reports the full match count, not just this page's —
              // useful for deciding whether to page further.
              totalAvailable: response.maxErgebnisse ?? null,
            },
            results: cards,
          },
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
