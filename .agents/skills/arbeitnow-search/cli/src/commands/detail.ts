import { SEARCH_URL, apiFetch, htmlFetch, parseJobDetailFromHtml, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

const BOUNDED_SLUG_SEARCH_PAGES = 3

/** Resolve a bare slug to its full job-page URL by scanning a bounded number of API pages. */
async function resolveSlugToUrl(slug: string): Promise<string | null> {
  for (let page = 1; page <= BOUNDED_SLUG_SEARCH_PAGES; page++) {
    const response = await apiFetch(`${SEARCH_URL}?page=${page}`)
    if (!response || response.data.length === 0) break
    const hit = response.data.find((j) => j.slug === slug)
    if (hit) return hit.url
    if (!response.links.next) break
  }
  return null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  let url = opts.id
  if (!/^https?:\/\//i.test(url)) {
    const resolved = await resolveSlugToUrl(opts.id)
    if (!resolved) {
      writeError(
        `Could not resolve slug "${opts.id}" to a job URL within the first ${BOUNDED_SLUG_SEARCH_PAGES} pages. ` +
          "Arbeitnow has no per-slug API lookup — pass the job's full \"url\" from a search result instead.",
        "NOT_FOUND",
      )
      return 1
    }
    url = resolved
  }

  try {
    const html = await htmlFetch(url)
    if (!html) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const job = parseJobDetailFromHtml(html, url)
    if (!job) {
      writeError("Could not parse job posting data from the page", "PARSE_FAILED")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}${job.remote ? " · remote" : ""}`,
        "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.datePosted ? `Posted: ${job.datePosted}` : "",
        job.validThrough ? `Apply by: ${job.validThrough}` : "",
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`,
        job.applyUrl && job.applyUrl !== job.url ? `Apply: ${job.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}
