// Data source: the Bundesagentur für Arbeit (German Federal Employment Agency)
// public Jobsuche API — the official job board of the German government, and the
// largest job database in Germany. Free, no registration, no scraping: a real REST
// API documented by the bundesAPI community project
// (https://github.com/bundesAPI/jobsuche-api).
//
// Because this is an official public API rather than a scraped site, it carries no
// personal-use-only warning and is far more durable than the HTML-scraping portal
// skills — it cannot break from a CSS/markup change or anti-bot escalation.
//
// ENDPOINT VERSIONS (verified live — the community docs are partly stale):
//   search → pc/v6/jobs           (v4 and v5 both return 404 as of 2026-08)
//   detail → pc/v4/jobdetails/... (v6 and v5 both return 403; v3 returns 404)
// The mixed version pair is not a mistake; each was probed individually.

export const API_BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
export const SEARCH_PATH = "pc/v6/jobs"
export const DETAIL_PATH = "pc/v4/jobdetails"
/** Public, well-known client key published for this open API (not a secret). */
export const API_KEY = "jobboerse-jobsuche"
/** Human-facing job page on arbeitsagentur.de, keyed by the raw reference number. */
export const WEB_BASE = "https://www.arbeitsagentur.de/jobsuche/jobdetail"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

async function apiFetch(url: string): Promise<Response | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: { "X-API-Key": API_KEY, Accept: "application/json" },
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
    if (response.status === 404) return null
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response
  }
  throw new Error("Request failed after max retries")
}

export async function fetchJson<T>(url: string): Promise<T | null> {
  const response = await apiFetch(url)
  if (!response) return null
  return (await response.json()) as T
}

export interface ApiAddress {
  strasse?: string
  hausnummer?: string
  plz?: string
  ort?: string
  region?: string
  land?: string
}

export interface ApiLocation {
  adresse?: ApiAddress
  breite?: number
  laenge?: number
}

export interface ApiJob {
  referenznummer?: string
  stellenangebotsTitel?: string
  stellenangebotsart?: string
  stellenangebotsBeschreibung?: string
  firma?: string
  stellenlokationen?: ApiLocation[]
  arbeitszeitVollzeit?: boolean
  homeofficemoeglich?: boolean
  homeofficetyp?: string
  veroeffentlichungszeitraum?: { von?: string; bis?: string }
  eintrittszeitraum?: { von?: string; bis?: string }
  aenderungsdatum?: string
  datumErsteVeroeffentlichung?: string
  verguetungsangabe?: string
  vertragsdauer?: string
  hauptberuf?: string
  alleBerufe?: string[]
  entfernung?: number
  externeUrl?: string
}

export interface ApiSearchResponse {
  ergebnisliste?: ApiJob[]
  maxErgebnisse?: number
  page?: number
  size?: number
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  offerType: string | null
  fullTime: boolean | null
  homeOffice: boolean | null
  distanceKm: number | null
}

export interface JobDetail extends JobCard {
  description: string | null
  startDate: string | null
  contractDuration: string | null
  salaryInfo: string | null
  professions: string[]
  applyUrl: string | null
}

/**
 * Format a job's location. Postings can carry several locations; they are joined
 * the same way the other German portal skills present multi-city postings.
 */
export function formatLocation(locations: ApiLocation[] | undefined): string | null {
  if (!locations || locations.length === 0) return null
  const parts = locations
    .map((l) => {
      const a = l.adresse
      if (!a) return null
      return a.ort || a.region || null
    })
    .filter((s): s is string => !!s)
  // De-duplicate while preserving order (multi-site postings often repeat a city).
  const seen = new Set<string>()
  const unique = parts.filter((p) => (seen.has(p) ? false : (seen.add(p), true)))
  return unique.length > 0 ? unique.join(", ") : null
}

/**
 * The detail endpoint keys on the base64 of the reference number. All three of
 * padded / unpadded / percent-encoded base64 were verified to work against the
 * live API; URL-safe unpadded is used here because it needs no escaping in a path.
 */
export function encodeRef(referenznummer: string): string {
  return Buffer.from(referenznummer, "utf-8").toString("base64url")
}

export function decodeRef(encoded: string): string {
  return Buffer.from(encoded, "base64url").toString("utf-8")
}

export function toJobCard(job: ApiJob): JobCard | null {
  const id = job.referenznummer
  if (!id) return null
  return {
    id,
    title: job.stellenangebotsTitel || job.hauptberuf || "(untitled)",
    company: job.firma || null,
    location: formatLocation(job.stellenlokationen),
    date: job.veroeffentlichungszeitraum?.von || job.datumErsteVeroeffentlichung || null,
    url: `${WEB_BASE}/${encodeURIComponent(id)}`,
    offerType: job.stellenangebotsart || null,
    fullTime: typeof job.arbeitszeitVollzeit === "boolean" ? job.arbeitszeitVollzeit : null,
    homeOffice: typeof job.homeofficemoeglich === "boolean" ? job.homeofficemoeglich : null,
    distanceKm: typeof job.entfernung === "number" ? job.entfernung : null,
  }
}

export function toJobDetail(job: ApiJob, id: string): JobDetail {
  const card = toJobCard({ ...job, referenznummer: job.referenznummer || id })
  const base: JobCard = card ?? {
    id,
    title: job.stellenangebotsTitel || "(untitled)",
    company: job.firma || null,
    location: formatLocation(job.stellenlokationen),
    date: job.veroeffentlichungszeitraum?.von || null,
    url: `${WEB_BASE}/${encodeURIComponent(id)}`,
    offerType: job.stellenangebotsart || null,
    fullTime: null,
    homeOffice: null,
    distanceKm: null,
  }
  return {
    ...base,
    // Descriptions come back as plain text with real newlines — no HTML to strip
    // and no entity decoding needed, unlike the scraped portals.
    description: job.stellenangebotsBeschreibung?.trim() || null,
    startDate: job.eintrittszeitraum?.von || null,
    contractDuration: job.vertragsdauer && job.vertragsdauer !== "KEINE_ANGABE" ? job.vertragsdauer : null,
    salaryInfo: job.verguetungsangabe && job.verguetungsangabe !== "KEINE_ANGABEN" ? job.verguetungsangabe : null,
    professions: job.alleBerufe || (job.hauptberuf ? [job.hauptberuf] : []),
    applyUrl: job.externeUrl || base.url,
  }
}

export interface SearchParams {
  query?: string
  location?: string
  jobage?: number
  radiusKm?: number
  page: number
  size: number
  /** `angebotsart` — 1 = ARBEIT (regular employment). Omit to include all types. */
  offerType?: number
}

export function buildSearchUrl(p: SearchParams): string {
  const params = new URLSearchParams()
  if (p.query) params.set("was", p.query)
  if (p.location) params.set("wo", p.location)
  if (p.offerType !== undefined) params.set("angebotsart", String(p.offerType))
  if (p.jobage && p.jobage > 0 && p.jobage < 9999) params.set("veroeffentlichtseit", String(p.jobage))
  if (p.radiusKm !== undefined) params.set("umkreis", String(p.radiusKm))
  params.set("page", String(p.page))
  params.set("size", String(p.size))
  return `${API_BASE}/${SEARCH_PATH}?${params.toString()}`
}

export function buildDetailUrl(referenznummer: string): string {
  return `${API_BASE}/${DETAIL_PATH}/${encodeRef(referenznummer)}`
}
