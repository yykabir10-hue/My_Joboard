import { describe, expect, test } from "bun:test"
import { buildSearchUrl, germanSlugify, parseJobCards, relativeGermanToISODate } from "../src/helpers"

/**
 * A representative two-card fragment reproducing the real markup shape discovered
 * live on stepstone.de: `data-at="job-item-title"` anchor carrying the href+ID, a
 * company/location field behind an icon+text pair (some cards wrap the text in an
 * extra <div>, some don't — both variants are exercised here), and a relative
 * "vor X" timeago string with no machine-readable timestamp.
 */
function fixtureHtml(): string {
  return `
    <style>.res-abc123 [data-at="job-item-title"]{color:teal;}</style>
    <a class="res-xaz43y" href="/stellenangebote--Data-Engineer-m-w-d-Berlin-Acme-GmbH--111111-inline.html" data-testid="job-item-title" data-at="job-item-title">
      <div class="res-xrpel9"><div class="res-kyg8or"><div class="res-ewgtgq">Data Engineer (m/w/d)</div></div></div>
    </a>
    <span data-genesis-element="TEXT" data-at="job-item-company-name">
      <span data-genesis-element="ICON_CONTAINER"><svg><path d="M0 0"/></svg></span>
      <style data-emotion="res du9bhi">.res-du9bhi{color:red;}</style>
      <span class="res-du9bhi" data-genesis-element="TEXT"><div class="res-ewgtgq">Acme GmbH</div></span>
    </span>
    <span data-genesis-element="BASE" data-at="job-item-location">
      <span data-genesis-element="ICON_CONTAINER"><svg><path d="M0 0"/></svg></span>
      <span class="res-du9bhi" data-genesis-element="TEXT">Berlin</span>
    </span>
    <span data-at="job-item-timeago"><time class="">vor 5 Tagen</time></span>

    <a href="/stellenangebote--Sales-Manager-m-w-d-Hamburg-Beta-AG--222222-inline.html" data-testid="job-item-title" data-at="job-item-title">
      <div class="res-xrpel9"><div class="res-kyg8or"><div class="res-ewgtgq">Sales Manager (m/w/d)</div></div></div>
    </a>
    <span data-genesis-element="TEXT" data-at="job-item-company-name">
      <span data-genesis-element="ICON_CONTAINER"><svg><path d="M0 0"/></svg></span>
      <span class="res-zzz999" data-genesis-element="TEXT">Beta AG</span>
    </span>
    <span data-genesis-element="BASE" data-at="job-item-location">
      <span data-genesis-element="ICON_CONTAINER"><svg><path d="M0 0"/></svg></span>
      <span class="res-zzz999" data-genesis-element="TEXT">Hamburg, Bremen</span>
    </span>
    <span data-at="job-item-timeago"><time class="">vor 1 Woche</time></span>
  `
}

describe("parseJobCards", () => {
  const cards = parseJobCards(fixtureHtml())

  test("splits into the correct number of cards despite a CSS selector containing the same data-at string", () => {
    expect(cards).toHaveLength(2)
  })

  test("extracts id and url from the href, ignoring the CSS <style> block match", () => {
    expect(cards[0].id).toBe("111111")
    expect(cards[0].url).toBe("https://www.stepstone.de/stellenangebote--Data-Engineer-m-w-d-Berlin-Acme-GmbH--111111-inline.html")
  })

  test("extracts title from the nested div, not from the URL slug, when present", () => {
    expect(cards[0].title).toBe("Data Engineer (m/w/d)")
  })

  test("extracts company/location correctly when the field text is wrapped in an extra <div> (line-clamp variant)", () => {
    expect(cards[0].company).toBe("Acme GmbH")
    expect(cards[0].location).toBe("Berlin")
  })

  test("extracts company/location correctly when the field text has no <div> wrapper", () => {
    expect(cards[1].company).toBe("Beta AG")
    expect(cards[1].location).toBe("Hamburg, Bremen")
  })

  test("does not cross-contaminate company with location text across the two shapes", () => {
    expect(cards[0].company).not.toBe(cards[0].location)
    expect(cards[1].company).not.toBe(cards[1].location)
  })

  test("captures the raw relative-time string per card", () => {
    expect(cards[0].timeagoRaw).toBe("vor 5 Tagen")
    expect(cards[1].timeagoRaw).toBe("vor 1 Woche")
  })

  test("falls back to a URL-slug-derived title when no title <div> is found", () => {
    const html = `<a href="/stellenangebote--Backend-Engineer-Berlin-Acme--333333-inline.html" data-at="job-item-title"></a>`
    const [card] = parseJobCards(html)
    expect(card.title.toLowerCase()).toContain("backend engineer")
  })

  test("returns an empty array for a page with no job cards", () => {
    expect(parseJobCards("<html><body>no jobs here</body></html>")).toHaveLength(0)
  })
})

describe("germanSlugify", () => {
  test("transliterates umlauts and eszett the way StepStone's own URLs do", () => {
    expect(germanSlugify("München")).toBe("muenchen")
    expect(germanSlugify("Köln")).toBe("koeln")
    expect(germanSlugify("Düsseldorf")).toBe("duesseldorf")
    expect(germanSlugify("Straße")).toBe("strasse")
  })

  test("collapses spaces and punctuation into single hyphens, trimmed", () => {
    expect(germanSlugify("Data Engineer (m/w/d)")).toBe("data-engineer-m-w-d")
  })
})

describe("buildSearchUrl", () => {
  test("query + location produces the confirmed live URL shape", () => {
    expect(buildSearchUrl("Data Engineer", "München", 1)).toBe(
      "https://www.stepstone.de/jobs/data-engineer/in-muenchen",
    )
  })

  test("page > 1 appends ?page=N", () => {
    expect(buildSearchUrl("Data Engineer", "München", 3)).toBe(
      "https://www.stepstone.de/jobs/data-engineer/in-muenchen?page=3",
    )
  })

  test("location is optional (nationwide search)", () => {
    expect(buildSearchUrl("Data Engineer", undefined, 1)).toBe("https://www.stepstone.de/jobs/data-engineer")
  })

  test("query is optional too", () => {
    expect(buildSearchUrl(undefined, undefined, 1)).toBe("https://www.stepstone.de/jobs")
  })
})

describe("relativeGermanToISODate", () => {
  const now = Date.UTC(2026, 0, 15, 12, 0, 0)

  test("'vor N Tagen' subtracts N days", () => {
    const iso = relativeGermanToISODate("vor 5 Tagen", now)
    expect(iso).toBe(new Date(now - 5 * 86400000).toISOString())
  })

  test("'vor 1 Woche' subtracts 7 days", () => {
    const iso = relativeGermanToISODate("vor 1 Woche", now)
    expect(iso).toBe(new Date(now - 7 * 86400000).toISOString())
  })

  test("'vor N Stunden' subtracts N hours", () => {
    const iso = relativeGermanToISODate("vor 17 Stunden", now)
    expect(iso).toBe(new Date(now - 17 * 3600000).toISOString())
  })

  test("unparseable text returns null rather than a wrong guess", () => {
    expect(relativeGermanToISODate("kürzlich", now)).toBeNull()
  })
})
