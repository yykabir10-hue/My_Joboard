import { describe, expect, test } from "bun:test"
import { jobageToThreshold, parseJobDetailFromHtml, toJobCard, type ApiJob } from "../src/helpers"

function apiJob(overrides: Partial<ApiJob> = {}): ApiJob {
  return {
    slug: "backend-engineer-berlin-1",
    company_name: "Acme GmbH",
    title: "Backend Engineer",
    description: "<p>Build things.</p>",
    remote: false,
    url: "https://www.arbeitnow.com/jobs/companies/acme-gmbh/backend-engineer-berlin-1",
    tags: ["Python"],
    job_types: ["FULL_TIME"],
    location: "Berlin, Germany",
    created_at: 1700000000,
    ...overrides,
  }
}

describe("toJobCard", () => {
  test("maps API fields to the shared JobCard shape", () => {
    const card = toJobCard(apiJob())
    expect(card.id).toBe("backend-engineer-berlin-1")
    expect(card.company).toBe("Acme GmbH")
    expect(card.location).toBe("Berlin, Germany")
    expect(card.date).toBe(new Date(1700000000 * 1000).toISOString())
    expect(card.remote).toBe(false)
  })

  test("missing company/location become null, not empty string", () => {
    const card = toJobCard(apiJob({ company_name: "", location: "" }))
    expect(card.company).toBeNull()
    expect(card.location).toBeNull()
  })
})

describe("jobageToThreshold", () => {
  test("9999 (default/all) returns null", () => {
    expect(jobageToThreshold(9999)).toBeNull()
  })

  test("0 or negative returns null", () => {
    expect(jobageToThreshold(0)).toBeNull()
    expect(jobageToThreshold(-5)).toBeNull()
  })

  test("7 days returns a threshold ~7 days before now", () => {
    const threshold = jobageToThreshold(7)
    expect(threshold).not.toBeNull()
    const expected = Math.floor(Date.now() / 1000) - 7 * 86400
    expect(Math.abs((threshold as number) - expected)).toBeLessThan(5)
  })
})

describe("parseJobDetailFromHtml", () => {
  const url = "https://www.arbeitnow.com/jobs/companies/acme-gmbh/backend-engineer-berlin-1"

  function pageWithLdJson(posting: object): string {
    const graph = { "@context": "https://schema.org/", "@graph": [{ "@type": "JobPosting", ...posting }] }
    return `<html><head><script type="application/ld+json">${JSON.stringify(graph)}</script></head><body></body></html>`
  }

  test("decodes German umlaut and typographic entities in the description", () => {
    const html = pageWithLdJson({
      title: "Deployment Strategist",
      description: "Wir suchen eine gro&szlig;e Pers&ouml;nlichkeit &ndash; das ist&rsquo;s.",
      hiringOrganization: { name: "Acme GmbH" },
      employmentType: "FULL_TIME",
    })
    const job = parseJobDetailFromHtml(html, url)
    expect(job).not.toBeNull()
    expect(job?.description).toBe("Wir suchen eine große Persönlichkeit – das ist’s.")
  })

  test("extracts jobLocation address into a single location string", () => {
    const html = pageWithLdJson({
      title: "Backend Engineer",
      description: "desc",
      hiringOrganization: { name: "Acme GmbH" },
      jobLocation: { address: { addressLocality: "Berlin", addressRegion: "Berlin", addressCountry: "DE" } },
    })
    const job = parseJobDetailFromHtml(html, url)
    expect(job?.location).toBe("Berlin, Berlin, DE")
  })

  test("returns null when no JSON-LD script tag is present", () => {
    expect(parseJobDetailFromHtml("<html><body>no ld+json here</body></html>", url)).toBeNull()
  })

  test("returns null when JSON-LD has no JobPosting entry", () => {
    const html = `<html><head><script type="application/ld+json">{"@graph":[{"@type":"Organization"}]}</script></head></html>`
    expect(parseJobDetailFromHtml(html, url)).toBeNull()
  })
})
