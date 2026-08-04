import { htmlFetch, parseJobDetailFromHtml, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a full xing.com job URL or a bare "<slug>-<id>" / numeric ID. */
function normalize(input: string): { url: string; id: string } | null {
  if (/^https?:\/\//i.test(input)) {
    const idMatch = input.match(/-(\d+)(?:[/?#]|$)/)
    return idMatch ? { url: input, id: idMatch[1] } : null
  }
  // A bare ID or slug-with-id can't be turned into a URL without the city/title slug
  // Xing requires in the path — there is no ID-only lookup route.
  return null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const normalized = normalize(opts.id)
  if (!normalized) {
    writeError(
      'Xing has no lookup-by-bare-ID endpoint — pass the job\'s full "url" from a search result instead.',
      "BAD_ID",
    )
    return 1
  }

  try {
    const html = await htmlFetch(normalized.url)
    if (!html) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const job = parseJobDetailFromHtml(html, normalized.url, normalized.id)
    if (!job) {
      writeError("Could not find schema.org JobPosting data on the page", "PARSE_FAILED")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}${job.employmentType ? " · " + job.employmentType : ""}`,
        "",
        job.industry ? `Industry: ${job.industry}` : "",
        job.date ? `Posted: ${job.date}` : "",
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
