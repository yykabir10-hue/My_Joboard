import { describe, expect, test } from "bun:test"
import {
  buildDetailUrl,
  buildSearchUrl,
  decodeRef,
  encodeRef,
  formatLocation,
  toJobCard,
  toJobDetail,
  type ApiJob,
} from "../src/helpers"
import { normalizeRef } from "../src/commands/detail"

function apiJob(overrides: Partial<ApiJob> = {}): ApiJob {
  return {
    referenznummer: "10000-1183204759-S",
    stellenangebotsTitel: "Data Engineer",
    stellenangebotsart: "ARBEIT",
    firma: "Acme GmbH",
    arbeitszeitVollzeit: true,
    homeofficemoeglich: false,
    veroeffentlichungszeitraum: { von: "2026-07-13" },
    stellenlokationen: [{ adresse: { ort: "Berlin", region: "BERLIN", land: "DEUTSCHLAND" } }],
    ...overrides,
  }
}

describe("formatLocation", () => {
  test("returns the city for a single location", () => {
    expect(formatLocation([{ adresse: { ort: "Berlin" } }])).toBe("Berlin")
  })

  test("joins multiple cities, as multi-site postings carry several", () => {
    expect(
      formatLocation([{ adresse: { ort: "Berlin" } }, { adresse: { ort: "München" } }, { adresse: { ort: "Köln" } }]),
    ).toBe("Berlin, München, Köln")
  })

  test("de-duplicates repeated cities rather than printing 'Berlin, Berlin'", () => {
    expect(formatLocation([{ adresse: { ort: "Berlin" } }, { adresse: { ort: "Berlin" } }])).toBe("Berlin")
  })

  test("falls back to region when a location has no city", () => {
    expect(formatLocation([{ adresse: { region: "BAYERN" } }])).toBe("BAYERN")
  })

  test("returns null (not an empty string) when there are no usable locations", () => {
    expect(formatLocation([])).toBeNull()
    expect(formatLocation(undefined)).toBeNull()
    expect(formatLocation([{}])).toBeNull()
  })
})

describe("encodeRef / decodeRef", () => {
  test("round-trips a standard reference number", () => {
    const ref = "10000-1183204759-S"
    expect(decodeRef(encodeRef(ref))).toBe(ref)
  })

  test("round-trips a reference number whose base64 needs padding", () => {
    // Verified live: this shape produces a '=' pad in standard base64.
    const ref = "12336-a26f539j0449337-S"
    expect(decodeRef(encodeRef(ref))).toBe(ref)
  })

  test("round-trips a reference number containing an underscore", () => {
    const ref = "13635-31b26ab2_JB5209868"
    expect(decodeRef(encodeRef(ref))).toBe(ref)
  })

  test("emits no characters that would need escaping in a URL path", () => {
    for (const ref of ["10000-1183204759-S", "12336-a26f539j0449337-S", "13635-31b26ab2_JB5209868"]) {
      const encoded = encodeRef(ref)
      expect(encoded).toBe(encodeURIComponent(encoded))
    }
  })
})

describe("toJobCard", () => {
  test("maps API fields onto the shared JobCard shape", () => {
    const card = toJobCard(apiJob())
    expect(card).not.toBeNull()
    expect(card?.id).toBe("10000-1183204759-S")
    expect(card?.title).toBe("Data Engineer")
    expect(card?.company).toBe("Acme GmbH")
    expect(card?.location).toBe("Berlin")
    expect(card?.date).toBe("2026-07-13")
  })

  test("builds a human-facing arbeitsagentur.de URL from the reference number", () => {
    const card = toJobCard(apiJob())
    expect(card?.url).toBe("https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-1183204759-S")
  })

  test("returns null when there is no reference number to key on", () => {
    expect(toJobCard(apiJob({ referenznummer: undefined }))).toBeNull()
  })

  test("anonymous postings yield company null, never an empty string", () => {
    expect(toJobCard(apiJob({ firma: undefined }))?.company).toBeNull()
  })

  test("falls back to hauptberuf when the posting has no explicit title", () => {
    const card = toJobCard(apiJob({ stellenangebotsTitel: undefined, hauptberuf: "Informatiker/in" }))
    expect(card?.title).toBe("Informatiker/in")
  })

  test("boolean flags stay null when the API omits them, rather than defaulting to false", () => {
    const card = toJobCard(apiJob({ homeofficemoeglich: undefined, arbeitszeitVollzeit: undefined }))
    expect(card?.homeOffice).toBeNull()
    expect(card?.fullTime).toBeNull()
  })
})

describe("toJobDetail", () => {
  test("carries the plain-text description through untouched", () => {
    const detail = toJobDetail(apiJob({ stellenangebotsBeschreibung: "  Zeile eins\nZeile zwei  " }), "10000-1-S")
    expect(detail.description).toBe("Zeile eins\nZeile zwei")
  })

  test("treats the API's KEINE_ANGABE sentinels as absent, not as literal values", () => {
    const detail = toJobDetail(
      apiJob({ verguetungsangabe: "KEINE_ANGABEN", vertragsdauer: "KEINE_ANGABE" }),
      "10000-1-S",
    )
    expect(detail.salaryInfo).toBeNull()
    expect(detail.contractDuration).toBeNull()
  })

  test("keeps a real salary/contract value when one is present", () => {
    const detail = toJobDetail(apiJob({ verguetungsangabe: "jahr", vertragsdauer: "UNBEFRISTET" }), "10000-1-S")
    expect(detail.salaryInfo).toBe("jahr")
    expect(detail.contractDuration).toBe("UNBEFRISTET")
  })

  test("description is null (not empty string) when the API omits it", () => {
    expect(toJobDetail(apiJob(), "10000-1-S").description).toBeNull()
  })
})

describe("buildSearchUrl", () => {
  test("maps query/location onto the API's German parameter names", () => {
    const url = new URL(buildSearchUrl({ query: "Data Engineer", location: "Berlin", page: 1, size: 25 }))
    expect(url.searchParams.get("was")).toBe("Data Engineer")
    expect(url.searchParams.get("wo")).toBe("Berlin")
  })

  test("hits the v6 search path (v4/v5 are retired and 404)", () => {
    expect(buildSearchUrl({ page: 1, size: 25 })).toContain("/pc/v6/jobs?")
  })

  test("angebotsart is sent only when an offer type is requested", () => {
    const withType = new URL(buildSearchUrl({ page: 1, size: 25, offerType: 1 }))
    expect(withType.searchParams.get("angebotsart")).toBe("1")
    const without = new URL(buildSearchUrl({ page: 1, size: 25 }))
    expect(without.searchParams.has("angebotsart")).toBe(false)
  })

  test("jobage maps to veroeffentlichtseit, and the 'all' sentinel is omitted", () => {
    expect(new URL(buildSearchUrl({ page: 1, size: 25, jobage: 7 })).searchParams.get("veroeffentlichtseit")).toBe("7")
    expect(new URL(buildSearchUrl({ page: 1, size: 25, jobage: 9999 })).searchParams.has("veroeffentlichtseit")).toBe(
      false,
    )
    expect(new URL(buildSearchUrl({ page: 1, size: 25, jobage: 0 })).searchParams.has("veroeffentlichtseit")).toBe(false)
  })

  test("umlaut locations are URL-encoded rather than transliterated", () => {
    const url = new URL(buildSearchUrl({ location: "München", page: 1, size: 25 }))
    expect(url.searchParams.get("wo")).toBe("München")
  })
})

describe("buildDetailUrl", () => {
  test("hits the v4 detail path (v5/v6 return 403) with the base64 reference", () => {
    const url = buildDetailUrl("10000-1183204759-S")
    expect(url).toContain("/pc/v4/jobdetails/")
    expect(url.endsWith(encodeRef("10000-1183204759-S"))).toBe(true)
  })
})

describe("normalizeRef", () => {
  test("passes a bare reference number through", () => {
    expect(normalizeRef("10000-1183204759-S")).toBe("10000-1183204759-S")
  })

  test("extracts the reference number from a full job URL", () => {
    expect(normalizeRef("https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-1183204759-S")).toBe(
      "10000-1183204759-S",
    )
  })

  test("tolerates a trailing slash on the URL", () => {
    expect(normalizeRef("https://www.arbeitsagentur.de/jobsuche/jobdetail/10000-1183204759-S/")).toBe(
      "10000-1183204759-S",
    )
  })

  test("returns null for empty input rather than an empty lookup", () => {
    expect(normalizeRef("   ")).toBeNull()
  })
})
