import { WEB_BASE, buildDetailUrl, fetchJson, toJobDetail, writeError, type ApiJob } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/**
 * Accept a raw reference number (e.g. `10000-1183204759-S`) or a full
 * arbeitsagentur.de job URL, from which the reference number is the last segment.
 */
export function normalizeRef(input: string): string | null {
  if (/^https?:\/\//i.test(input)) {
    try {
      const path = new URL(input).pathname.replace(/\/+$/, "")
      const last = path.split("/").pop()
      return last ? decodeURIComponent(last) : null
    } catch {
      return null
    }
  }
  const trimmed = input.trim()
  return trimmed.length > 0 ? trimmed : null
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const ref = normalizeRef(opts.id)
  if (!ref) {
    writeError(
      `Could not parse a Referenznummer from "${opts.id}" — pass the id from a search result (e.g. 10000-1183204759-S) or a ${WEB_BASE}/... URL`,
      "BAD_ID",
    )
    return 1
  }

  try {
    const job = await fetchJson<ApiJob>(buildDetailUrl(ref))
    if (!job) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const detail = toJobDetail(job, ref)

    if (opts.format === "plain") {
      const lines = [
        detail.title,
        `${detail.company || "—"} · ${detail.location || "—"}${detail.homeOffice ? " · home office" : ""}`,
        "",
        detail.offerType ? `Type: ${detail.offerType}` : "",
        detail.fullTime === null ? "" : `Hours: ${detail.fullTime ? "Vollzeit" : "Teilzeit"}`,
        detail.startDate ? `Start: ${detail.startDate}` : "",
        detail.contractDuration ? `Contract: ${detail.contractDuration}` : "",
        detail.salaryInfo ? `Pay: ${detail.salaryInfo}` : "",
        detail.professions.length ? `Professions: ${detail.professions.join(", ")}` : "",
        "",
        detail.description || "(no description)",
        "",
        `URL: ${detail.url}`,
        detail.applyUrl && detail.applyUrl !== detail.url ? `Apply: ${detail.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(detail, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}
