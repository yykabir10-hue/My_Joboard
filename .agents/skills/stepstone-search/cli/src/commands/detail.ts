import { htmlFetch, parseJobDetailFromHtml, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a raw numeric job ID, a full detail URL, or the -inline.html slug. */
function normalizeUrl(input: string): { url: string; id: string } | null {
  if (/^https?:\/\//i.test(input)) {
    const idMatch = input.match(/--(\d+)-inline\.html/)
    return idMatch ? { url: input, id: idMatch[1] } : null
  }
  const bareId = input.match(/^\d+$/)
  if (bareId) {
    // No numeric-ID-only lookup endpoint exists on StepStone — a bare ID alone
    // cannot be turned into a URL without the title slug. Callers should pass the
    // full "url" field from a search result instead.
    return null
  }
  return null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const normalized = normalizeUrl(opts.id)
  if (!normalized) {
    writeError(
      'StepStone has no lookup-by-bare-ID endpoint — pass the job\'s full "url" from a search result instead.',
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
      writeError(
        "Could not find schema.org JobPosting data on the page (StepStone's detail-page markup may differ from what was verified during development)",
        "PARSE_FAILED",
      )
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}`,
        "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
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
