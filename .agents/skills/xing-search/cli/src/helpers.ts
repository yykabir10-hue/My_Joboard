// Data source: Xing's public job-search results page
// (https://www.xing.com/jobs/search/ki?keywords=...&location=...). Xing's robots.txt
// disallows `/jobs/search` and `/jobs/search?*` for `User-agent: *` — same posture the
// repo already ships a precedent for with linkedin-search. Personal use only, keep
// volume low (see SKILL.md).
//
// The card markup is a React app with hashed styled-components class names (NOT
// stable across builds) but stable `data-testid`/`data-xds` semantic attributes,
// which this parser anchors on exclusively.
//
// Individual job pages embed a full schema.org JobPosting as JSON-LD
// (`<script data-ch type="application/ld+json">`) with no login wall — confirmed live,
// unlike stepstone-search's detail page which is unreachable entirely.

export const SEARCH_URL = "https://www.xing.com/jobs/search/ki"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

/** Fetch HTML with exponential backoff on 429/5xx. Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(20000),
    })
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return ""
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response.text()
  }
  throw new Error("Request failed after max retries")
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  employmentType: string | null
  url: string
}

export interface JobDetail extends JobCard {
  description: string | null
  industry: string | null
  applyUrl: string | null
}

const NAMED_ENTITIES: Record<string, string> = {
  quot: '"',
  apos: "'",
  nbsp: " ",
  rsquo: "’",
  lsquo: "‘",
  rdquo: "”",
  ldquo: "“",
  hellip: "…",
  mdash: "—",
  ndash: "–",
  auml: "ä",
  ouml: "ö",
  uuml: "ü",
  Auml: "Ä",
  Ouml: "Ö",
  Uuml: "Ü",
  szlig: "ß",
}

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&(\w+);/g, (m, name) => (name in NAMED_ENTITIES ? NAMED_ENTITIES[name] : m))
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
}

/** Strip tags and React hydration comments (`<!-- -->`), collapsing whitespace. */
function stripTags(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|ul|ol|div|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
}

/**
 * Remove invisible formatting characters. Xing injects U+00AD SOFT HYPHEN into
 * titles and company names for typographic hyphenation ("Da­ta En­gi­neer"),
 * which renders identically to the clean string but silently corrupts everything
 * downstream: cross-portal dedup stops matching, `/rank` keyword scoring misses the
 * term, and the mangled text would be copied verbatim into a CV or cover letter.
 * Zero-width characters and BOM are stripped for the same reason; NBSP becomes a
 * real space rather than vanishing, since it is genuine whitespace.
 */
export function stripInvisibles(text: string): string {
  return text.replace(/[\u00AD\u200B\u200C\u200D\uFEFF]/g, "").replace(/\u00A0/g, " ")
}

function clean(html: string): string {
  return stripInvisibles(decodeHtmlEntities(stripTags(html)))
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

/**
 * Parse the search-results HTML into job cards. Cards without a real Xing job URL
 * (sponsored listings that redirect through a third-party ad tracker, e.g.
 * `tnl2.jometer.com`, confirmed present in live results) are skipped — they carry no
 * stable Xing job ID and `detail` could never fetch them.
 */
export function parseJobCards(html: string): JobCard[] {
  const results: JobCard[] = []
  const starts: number[] = []
  const markerRe = /data-testid="job-search-result"/g
  let m: RegExpExecArray | null
  while ((m = markerRe.exec(html)) !== null) starts.push(m.index)

  for (let i = 0; i < starts.length; i++) {
    const chunk = html.slice(starts[i], i + 1 < starts.length ? starts[i + 1] : html.length)

    const hrefMatch = chunk.match(/href="(\/jobs\/[a-z0-9-]+-(\d+))"/)
    if (!hrefMatch) continue // sponsored/external-redirect card — no stable Xing ID
    const [, path, id] = hrefMatch

    const titleMatch = chunk.match(/data-testid="job-teaser-list-title">([^<]+)<\/h2>/)
    if (!titleMatch) continue
    const title = clean(titleMatch[1])

    const companyMatch = chunk.match(/data-testid="job-teaser-list-title">[^<]+<\/h2><p[^>]*>([^<]+)<\/p>/)
    const company = companyMatch ? clean(companyMatch[1]) || null : null

    const locMatch = chunk.match(/multi-location-display[^"]*"><p[^>]*>([\s\S]*?)<\/p>/)
    let location: string | null = null
    if (locMatch) {
      const withoutBadge = locMatch[1].replace(/<b[^>]*>[\s\S]*?<\/b>/, "")
      location = clean(withoutBadge) || null
    }

    const timeMatch = chunk.match(/<time dateTime="([^"]+)"/)
    const date = timeMatch ? timeMatch[1] : null

    const empMatch = chunk.match(/data-xds="Marker"[^>]*role="status"><span[^>]*>([^<]+)<\/span>/)
    const employmentType = empMatch ? clean(empMatch[1]) || null : null

    results.push({
      id,
      title,
      company,
      location,
      date,
      employmentType,
      url: `https://www.xing.com${path}`,
    })
  }
  return results
}

/**
 * Parse a job-detail page via its embedded schema.org JobPosting JSON-LD block.
 * The script tag carries an extra `data-ch` attribute before `type=` — match
 * attributes loosely rather than assuming a fixed order.
 */
export function parseJobDetailFromHtml(html: string, url: string, id: string): JobDetail | null {
  const ldMatches = html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi)
  for (const ldMatch of ldMatches) {
    let posting: any
    try {
      posting = JSON.parse(ldMatch[1].trim())
    } catch {
      continue
    }
    if (!posting || posting["@type"] !== "JobPosting") continue

    const title = typeof posting.title === "string" ? clean(posting.title) : "(untitled)"
    const company =
      posting.hiringOrganization && typeof posting.hiringOrganization.name === "string"
        ? clean(posting.hiringOrganization.name)
        : null
    const loc = posting.jobLocation
    const address = Array.isArray(loc) ? loc[0]?.address : loc?.address
    const location = address
      ? [address.addressLocality, address.addressRegion, address.addressCountry].filter(Boolean).join(", ") || null
      : null

    return {
      id,
      title,
      company,
      location,
      date: typeof posting.datePosted === "string" ? posting.datePosted : null,
      employmentType: typeof posting.employmentType === "string" ? posting.employmentType : null,
      url,
      description: typeof posting.description === "string" ? clean(posting.description) : null,
      industry: typeof posting.industry === "string" ? posting.industry : null,
      applyUrl: typeof posting.url === "string" ? posting.url : url,
    }
  }
  return null
}

/** Convert a job-age in days to a minimum ISO-date threshold (ms since epoch). */
export function jobageToThresholdMs(days: number, now: number = Date.now()): number | null {
  if (!days || days <= 0 || days >= 9999) return null
  return now - days * 86400000
}
