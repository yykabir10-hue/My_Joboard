import { describe, expect, test } from "bun:test"
import { jobageToThresholdMs, parseJobCards, parseJobDetailFromHtml, stripInvisibles } from "../src/helpers"

/**
 * Reproduces the real markup shapes discovered live on xing.com/jobs/search/ki:
 * a normal single-city card with a date, a multi-city card whose location text is
 * split across several <span>s with React hydration comments, a card with no
 * <time> element at all (Xing omits the date on some listings — confirmed live),
 * and a sponsored card whose href redirects through a third-party ad tracker
 * instead of xing.com (must be skipped — no stable Xing job ID).
 */
function fixtureHtml(): string {
  return `
    <div data-testid="job-search-result" aria-label="Data Engineer. Klicke...">
      <a href="/jobs/berlin-data-engineer-111111" target="_blank"></a>
      <div><div><div>
        <h2 data-testid="job-teaser-list-title">Data Engineer</h2><p>Acme GmbH</p>
        <div class="multi-location-display-styles__Container-x"><p>Berlin<b class="OverflowLabel">&nbsp;+ 0 weitere</b></p></div>
      </div></div></div>
      <span data-xds="Marker" role="status"><span>Vollzeit</span></span>
      <p data-xds="Meta"><time dateTime="2026-07-30T06:01:22Z">Vor 4 Tagen</time></p>
    </div>

    <div data-testid="job-search-result" aria-label="Backend Engineer. Klicke...">
      <a href="/jobs/multi-backend-engineer-222222" target="_blank"></a>
      <div><div><div>
        <h2 data-testid="job-teaser-list-title">Backend Engineer</h2><p>Multi GmbH</p>
        <div class="multi-location-display-styles__Container-x"><p><span>Köln<!-- -->, </span><span>München<!-- -->, </span><span>Berlin</span><b class="OverflowLabel">&nbsp;+ 0 weitere</b></p></div>
      </div></div></div>
      <p data-xds="Meta"></p>
    </div>

    <div data-testid="job-search-result" aria-label="Sponsored Role. Klicke...">
      <a href="https://tnl2.jometer.com/v2/job?jx=abc123" target="_blank"></a>
      <div><div><div>
        <h2 data-testid="job-teaser-list-title">Sponsored Role</h2><p>Ad Corp</p>
      </div></div></div>
    </div>
  `
}

describe("parseJobCards", () => {
  const cards = parseJobCards(fixtureHtml())

  test("skips sponsored cards whose href redirects through a third-party ad tracker", () => {
    expect(cards).toHaveLength(2)
    expect(cards.find((c) => c.title === "Sponsored Role")).toBeUndefined()
  })

  test("extracts id, title, company from a normal card", () => {
    expect(cards[0].id).toBe("111111")
    expect(cards[0].title).toBe("Data Engineer")
    expect(cards[0].company).toBe("Acme GmbH")
    expect(cards[0].url).toBe("https://www.xing.com/jobs/berlin-data-engineer-111111")
  })

  test("extracts a single-city location, stripping the '+N weitere' badge", () => {
    expect(cards[0].location).toBe("Berlin")
  })

  test("extracts an ISO date from the <time> element when present", () => {
    expect(cards[0].date).toBe("2026-07-30T06:01:22Z")
  })

  test("joins a multi-city location split across several <span>s with hydration comments", () => {
    expect(cards[1].location).toBe("Köln, München, Berlin")
  })

  test("date is null (not a wrong guess) when Xing omits the <time> element", () => {
    expect(cards[1].date).toBeNull()
  })
})

describe("jobageToThresholdMs", () => {
  test("9999 (default/all) returns null", () => {
    expect(jobageToThresholdMs(9999)).toBeNull()
  })

  test("0 or negative returns null", () => {
    expect(jobageToThresholdMs(0)).toBeNull()
    expect(jobageToThresholdMs(-3)).toBeNull()
  })
})

describe("parseJobDetailFromHtml", () => {
  const url = "https://www.xing.com/jobs/berlin-data-engineer-111111"

  function pageWithLdJson(posting: object): string {
    // Real Xing pages carry an extra `data-ch` attribute before `type=` on the
    // script tag — the parser must not assume a fixed attribute order.
    return `<html><head><script data-ch type="application/ld+json">${JSON.stringify({
      "@context": "https://schema.org/",
      "@type": "JobPosting",
      ...posting,
    })}</script></head></html>`
  }

  test("parses a job with the data-ch-prefixed script tag", () => {
    const html = pageWithLdJson({
      title: "Data Engineer",
      description: "<p>Build things.</p>",
      hiringOrganization: { name: "Acme GmbH" },
      employmentType: "Vollzeit",
      jobLocation: [{ address: { addressLocality: "Berlin", addressRegion: "Berlin", addressCountry: "DE" } }],
    })
    const job = parseJobDetailFromHtml(html, url, "111111")
    expect(job).not.toBeNull()
    expect(job?.title).toBe("Data Engineer")
    expect(job?.company).toBe("Acme GmbH")
    expect(job?.location).toBe("Berlin, Berlin, DE")
    expect(job?.description).toBe("Build things.")
  })

  test("returns null when no JobPosting JSON-LD is present", () => {
    expect(parseJobDetailFromHtml("<html><body>no ld+json here</body></html>", url, "111111")).toBeNull()
  })
})

describe("stripInvisibles (regression: soft hyphens broke cross-portal dedup)", () => {
  // Xing served exactly this for a real Robert Koch-Institut posting. It renders
  // as "Data Engineer" but contains U+00AD soft hyphens, so an exact-match dedup
  // against the same job from another portal silently failed.
  const LIVE_TITLE = "Da­ta En­gi­neer (d/m/w)"
  const LIVE_COMPANY = "Ro­bert Koch-In­sti­tut"

  test("strips soft hyphens so the title matches the same job from another portal", () => {
    expect(stripInvisibles(LIVE_TITLE)).toBe("Data Engineer (d/m/w)")
  })

  test("strips soft hyphens from company names", () => {
    expect(stripInvisibles(LIVE_COMPANY)).toBe("Robert Koch-Institut")
  })

  test("strips zero-width characters and BOM", () => {
    expect(stripInvisibles("Da​ta‌ En‍gineer﻿")).toBe("Data Engineer")
  })

  test("converts NBSP to a real space rather than deleting it", () => {
    expect(stripInvisibles("Data Engineer")).toBe("Data Engineer")
  })

  test("leaves a clean string untouched, including real hyphens and umlauts", () => {
    expect(stripInvisibles("Data Engineer - München (m/w/d)")).toBe("Data Engineer - München (m/w/d)")
  })

  test("parseJobCards emits soft-hyphen-free text end to end", () => {
    const html = `<div data-testid="job-search-result">
      <a href="/jobs/berlin-data-engineer-999999"></a>
      <h2 data-testid="job-teaser-list-title">Da­ta En­gi­neer (d/m/w)</h2><p>Ro­bert Koch-In­sti­tut</p>
    </div>`
    const [card] = parseJobCards(html)
    expect(card.title).toBe("Data Engineer (d/m/w)")
    expect(card.company).toBe("Robert Koch-Institut")
  })
})
