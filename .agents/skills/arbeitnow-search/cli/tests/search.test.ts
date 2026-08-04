import { afterEach, describe, expect, test } from "bun:test"
import { locationVariants, runSearch } from "../src/commands/search"

const originalFetch = globalThis.fetch
const originalStdoutWrite = process.stdout.write

function apiResponse(jobs: any[]): Response {
  return new Response(
    JSON.stringify({
      data: jobs,
      links: { first: null, last: null, prev: null, next: null },
      meta: { current_page: 1, per_page: jobs.length, from: 1, to: jobs.length },
    }),
  )
}

function job(overrides: Record<string, any> = {}) {
  return {
    slug: "job-1",
    company_name: "Acme GmbH",
    title: "Backend Engineer",
    description: "desc",
    remote: false,
    url: "https://www.arbeitnow.com/jobs/companies/acme/job-1",
    tags: [],
    job_types: [],
    location: "Berlin, Germany",
    created_at: Math.floor(Date.now() / 1000),
    ...overrides,
  }
}

afterEach(() => {
  globalThis.fetch = originalFetch
  process.stdout.write = originalStdoutWrite
})

function captureStdout(): { get: () => string } {
  let out = ""
  process.stdout.write = ((chunk: string | Uint8Array) => {
    out += chunk.toString()
    return true
  }) as typeof process.stdout.write
  return { get: () => out }
}

describe("runSearch", () => {
  test("--limit 0 emits zero results", async () => {
    globalThis.fetch = (async () => apiResponse([job()])) as typeof fetch
    const out = captureStdout()

    const code = await runSearch({ jobage: 9999, page: 1, limit: 0, format: "json" })

    expect(code).toBe(0)
    expect(JSON.parse(out.get()).results).toHaveLength(0)
  })

  test("--query filters on title (case-insensitive)", async () => {
    globalThis.fetch = (async () =>
      apiResponse([job({ slug: "a", title: "Backend Engineer" }), job({ slug: "b", title: "Sales Manager" })])) as typeof fetch
    const out = captureStdout()

    await runSearch({ query: "engineer", jobage: 9999, page: 1, format: "json" })

    const results = JSON.parse(out.get()).results
    expect(results).toHaveLength(1)
    expect(results[0].id).toBe("a")
  })

  test('--location "Remote" matches jobs flagged remote or with Homeoffice in location', async () => {
    globalThis.fetch = (async () =>
      apiResponse([
        job({ slug: "a", remote: true, location: "Germany" }),
        job({ slug: "b", remote: false, location: "Homeoffice" }),
        job({ slug: "c", remote: false, location: "Munich" }),
      ])) as typeof fetch
    const out = captureStdout()

    await runSearch({ location: "Remote", jobage: 9999, page: 1, format: "json" })

    const ids = JSON.parse(out.get()).results.map((r: any) => r.id)
    expect(ids.sort()).toEqual(["a", "b"])
  })

  test("--jobage excludes postings older than N days", async () => {
    const now = Math.floor(Date.now() / 1000)
    globalThis.fetch = (async () =>
      apiResponse([
        job({ slug: "fresh", created_at: now - 86400 }),
        job({ slug: "stale", created_at: now - 30 * 86400 }),
      ])) as typeof fetch
    const out = captureStdout()

    await runSearch({ jobage: 7, page: 1, format: "json" })

    const ids = JSON.parse(out.get()).results.map((r: any) => r.id)
    expect(ids).toEqual(["fresh"])
  })

  test("table format prints 'No results.' for an empty set", async () => {
    globalThis.fetch = (async () => apiResponse([])) as typeof fetch
    const out = captureStdout()

    await runSearch({ jobage: 9999, page: 1, format: "table" })

    expect(out.get().trim()).toBe("No results.")
  })
})

describe("locationVariants (regression: München/Munich did not unify)", () => {
  test("German city name also matches its English spelling", () => {
    const v = locationVariants("München")
    expect(v).toContain("munich")
    expect(v).toContain("muenchen")
  })

  test("English city name also matches the German spelling", () => {
    expect(locationVariants("Cologne")).toContain("köln")
  })

  test("an unknown city returns just itself, lowercased", () => {
    expect(locationVariants("Bielefeld")).toEqual(["bielefeld"])
  })

  test('--location "München" finds a posting Arbeitnow spelled "Munich, GER"', async () => {
    globalThis.fetch = (async () =>
      apiResponse([
        job({ slug: "a", location: "Munich, GER" }),
        job({ slug: "b", location: "München, Germany" }),
        job({ slug: "c", location: "Hamburg" }),
      ])) as typeof fetch
    const out = captureStdout()

    await runSearch({ location: "München", jobage: 9999, page: 1, format: "json" })

    const ids = JSON.parse(out.get()).results.map((r: any) => r.id)
    expect(ids.sort()).toEqual(["a", "b"])
  })
})
