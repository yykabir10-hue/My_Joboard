// Data source: Arbeitnow's public Job Board API (https://www.arbeitnow.com/api/job-board-api).
// A free, no-auth, no-API-key REST API intended for exactly this kind of consumption
// (per its own `meta.terms` field: "This is a free public API for jobs, please do not
// abuse"). Search returns paginated JSON directly — no HTML parsing needed. The API has
// no server-side `?search=`/`?tags=` filter (confirmed empirically: every query-param
// variant returns the same result set as no params at all), so query/location/jobage
// filtering happens client-side on whichever page was fetched.
//
// Detail has no per-slug API lookup either, so it fetches the job's own page (the `url`
// each search result already carries) and reads the schema.org JobPosting block embedded
// in a <script type="application/ld+json"> tag — cleaner and more stable than scraping
// arbitrary CSS classes.

export const SEARCH_URL = "https://www.arbeitnow.com/api/job-board-api"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async function fetchWithBackoff(url: string, headers: Record<string, string>): Promise<Response | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers,
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
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
    if (response.status === 404) return null
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response
  }
  throw new Error("Request failed after max retries")
}

/** Fetch a page of the Job Board API. Returns null on a 404. */
export async function apiFetch(url: string): Promise<ApiResponse | null> {
  const response = await fetchWithBackoff(url, {
    "User-Agent": UA,
    Accept: "application/json",
  })
  if (!response) return null
  return (await response.json()) as ApiResponse
}

/** Fetch a job's own HTML page (for `detail`). Returns "" on a 404. */
export async function htmlFetch(url: string): Promise<string> {
  const response = await fetchWithBackoff(url, {
    "User-Agent": UA,
    Accept: "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
  })
  if (!response) return ""
  return response.text()
}

export interface ApiJob {
  slug: string
  company_name: string
  title: string
  description: string
  remote: boolean
  url: string
  tags: string[]
  job_types: string[]
  location: string
  created_at: number
}

export interface ApiResponse {
  data: ApiJob[]
  links: { first: string | null; last: string | null; prev: string | null; next: string | null }
  meta: { current_page: number; per_page: number; from: number | null; to: number | null }
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  remote: boolean
  tags: string[]
  jobTypes: string[]
}

export interface JobDetail extends JobCard {
  description: string | null
  employmentType: string | null
  datePosted: string | null
  validThrough: string | null
  applyUrl: string | null
}

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

// Named entities beyond the XML-escape basics: German-language postings routinely carry
// umlaut/eszett entities and typographic punctuation (curly quotes, dashes, ellipsis).
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
  eacute: "é",
  egrave: "è",
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&(\w+);/g, (m, name) => (name in NAMED_ENTITIES ? NAMED_ENTITIES[name] : m))
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    // amp/lt/gt last so entities decoded above (which may themselves contain literal & from
    // a double-escaped source) aren't re-mangled, and so "&amp;lt;" -> "&lt;" -> "<" doesn't happen.
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
}

function stripTags(html: string): string {
  return html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|ul|ol|div|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
}

function cleanDescription(html: string): string | null {
  const withoutXmlDecl = html.replace(/^\s*<\?xml[^>]*>/i, "")
  const text = decodeHtmlEntities(stripTags(withoutXmlDecl))
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
  return text || null
}

/** Map one API job object to the shared JobCard shape. */
export function toJobCard(job: ApiJob): JobCard {
  return {
    id: job.slug,
    title: job.title,
    company: job.company_name || null,
    location: job.location || null,
    date: job.created_at ? new Date(job.created_at * 1000).toISOString() : null,
    url: job.url,
    remote: !!job.remote,
    tags: job.tags || [],
    jobTypes: job.job_types || [],
  }
}

/** Convert a job-age in days to a minimum `created_at` unix-seconds threshold. */
export function jobageToThreshold(days: number): number | null {
  if (!days || days <= 0 || days >= 9999) return null
  return Math.floor(Date.now() / 1000) - days * 86400
}

/**
 * Parse the schema.org JobPosting block out of a job page's JSON-LD script tag.
 * Arbeitnow embeds a single `@graph` array containing one JobPosting entry.
 */
export function parseJobDetailFromHtml(html: string, fallbackUrl: string): JobDetail | null {
  const ldMatch = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/i)
  if (!ldMatch) return null

  let parsed: any
  try {
    parsed = JSON.parse(ldMatch[1].trim())
  } catch {
    return null
  }

  const graph = Array.isArray(parsed["@graph"]) ? parsed["@graph"] : [parsed]
  const posting = graph.find((n: any) => n && n["@type"] === "JobPosting")
  if (!posting) return null

  const title = typeof posting.title === "string" ? decodeHtmlEntities(posting.title) : "(untitled)"
  const company =
    posting.hiringOrganization && typeof posting.hiringOrganization.name === "string"
      ? decodeHtmlEntities(posting.hiringOrganization.name)
      : null
  const loc = posting.jobLocation
  const address = Array.isArray(loc) ? loc[0]?.address : loc?.address
  const location = address
    ? [address.addressLocality, address.addressRegion, address.addressCountry].filter(Boolean).join(", ") || null
    : null

  return {
    id:
      fallbackUrl
        .split("/")
        .filter(Boolean)
        .pop() || fallbackUrl,
    title,
    company,
    location,
    date: typeof posting.datePosted === "string" ? posting.datePosted : null,
    url: fallbackUrl,
    remote: /remote/i.test(location || "") || /remote/i.test(posting.jobLocationType || ""),
    tags: [],
    jobTypes: typeof posting.employmentType === "string" ? [posting.employmentType] : [],
    description: typeof posting.description === "string" ? cleanDescription(posting.description) : null,
    employmentType: typeof posting.employmentType === "string" ? posting.employmentType : null,
    datePosted: typeof posting.datePosted === "string" ? posting.datePosted : null,
    validThrough: typeof posting.validThrough === "string" ? posting.validThrough : null,
    applyUrl: typeof posting.url === "string" ? posting.url : fallbackUrl,
  }
}
