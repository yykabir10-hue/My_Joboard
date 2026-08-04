# Bundesagentur für Arbeit (Arbeitsagentur) Jobsuche — endpoint reference

Official public API of the German Federal Employment Agency. Community documentation:
[bundesAPI/jobsuche-api](https://github.com/bundesAPI/jobsuche-api).

**No scraping, no robots.txt concern, no ToS restriction** — this is a published open
API. No personal-use-only warning is required.

## Authentication

```
X-API-Key: jobboerse-jobsuche
```

A well-known public client key published for this open API — not a secret and not
user-specific. No OAuth, no registration, no per-user token.

## Base URL

```
https://rest.arbeitsagentur.de/jobboerse/jobsuche-service
```

## ⚠️ Version discovery (the community docs are partly stale)

Each path below was probed individually on 2026-08-03. **The search and detail
endpoints are on different API versions**, which looks like a bug but is not:

| Path | Result |
|---|---|
| `pc/v6/jobs` | ✅ **200** — the working search endpoint |
| `pc/v5/jobs` | ❌ 404 |
| `pc/v4/jobs` | ❌ 404 (still shown in most community examples — no longer works) |
| `pc/v4/app/jobs` | ❌ 404 |
| `pc/v6/jobdetails/{b64}` | ❌ 403 |
| `pc/v5/jobdetails/{b64}` | ❌ 403 |
| `pc/v4/jobdetails/{b64}` | ✅ **200** — the working detail endpoint |
| `pc/v3/jobdetails/{b64}` | ❌ 404 |

If search starts 404ing in future, walk the version number **up** (`v7`, `v8`) before
assuming the API is down — that is exactly how `v4` → `v6` happened here.

## Search

```
GET {base}/pc/v6/jobs?was=<query>&wo=<location>&angebotsart=1&veroeffentlichtseit=<days>&umkreis=<km>&page=<n>&size=<n>
```

| Param | Meaning | Notes |
|---|---|---|
| `was` | Keywords / job title | Plain text, URL-encoded |
| `wo` | Location | Plain text; **umlauts work as-is**, no transliteration (contrast with StepStone's path-slug scheme) |
| `angebotsart` | Offer type | `1` = ARBEIT (regular employment). **Verified meaningful**: without it, results include `SELBSTAENDIGKEIT` entries (self-employment / training courses, e.g. `alfatraining` course listings) that are not real vacancies. `Data Engineer`+`Berlin` returned 159 unfiltered vs 150 with `angebotsart=1` |
| `veroeffentlichtseit` | Posted within N days | **Genuine server-side filter** — verified: 150 results → 15 with `=7` |
| `umkreis` | Radius in km | Verified accepted |
| `page` | 1-indexed page | Verified: page 2 returns a different result set |
| `size` | Results per page | **Max 100** (verified `size=100` returns exactly 100) |

### Response shape

```json
{
  "ergebnisliste": [ { ...job... } ],
  "maxErgebnisse": 660,
  "page": 1,
  "size": 100,
  "woOutput": { "bereinigterOrt": "Berlin", "suchmodus": "UMKREISSUCHE", "koordinaten": [...] },
  "facetten": { "verguetung": {...}, "befristung": {...}, "externestellenboersen": {...}, ... }
}
```

`maxErgebnisse` is the **total** match count, not the page count — surfaced as
`meta.totalAvailable` in this CLI's JSON output so callers can decide whether to page.

### Job object

```json
{
  "referenznummer": "10000-1183204759-S",
  "stellenangebotsTitel": "Data Engineer",
  "stellenangebotsart": "ARBEIT",
  "firma": "alfatraining Bildungszentrum GmbH",
  "stellenlokationen": [
    { "adresse": { "strasse": "...", "hausnummer": "73", "plz": "10247",
                   "ort": "Berlin", "region": "BERLIN", "land": "DEUTSCHLAND" },
      "breite": 52.51, "laenge": 13.46 }
  ],
  "arbeitszeitVollzeit": true,
  "homeofficemoeglich": true,
  "homeofficetyp": "NACH_VEREINBARUNG",
  "veroeffentlichungszeitraum": { "von": "2026-07-13" },
  "eintrittszeitraum": { "von": "2026-08-03" },
  "datumErsteVeroeffentlichung": "2025-02-10",
  "aenderungsdatum": "2026-07-13T10:44:14.885",
  "verguetungsangabe": "KEINE_ANGABEN",
  "vertragsdauer": "KEINE_ANGABE",
  "hauptberuf": "Data Engineer",
  "alleBerufe": ["Data Engineer", "Informatiker/in"],
  "entfernung": 3
}
```

Field notes:
- `referenznummer` is the primary key — it drives both `detail` and the public web URL.
- `stellenlokationen` is an **array**; multi-site postings list several cities. The CLI
  joins and de-duplicates them.
- `verguetungsangabe` / `vertragsdauer` use `KEINE_ANGABEN` / `KEINE_ANGABE` as
  "not specified" sentinels — the CLI maps these to `null` rather than surfacing the
  literal sentinel string.
- Field completeness is high: across a 100-record sample, **zero** records were missing
  title, company, locations, publication date, or reference number.

## Detail

```
GET {base}/pc/v4/jobdetails/{base64(referenznummer)}
```

The path segment is the **base64 of the raw reference number**. Verified: standard
base64, unpadded base64, and percent-encoded (`%3D`) padding **all work** — the API
accepts any of the three. This CLI uses URL-safe unpadded base64 because it needs no
escaping in a path.

> Note: for these reference numbers, URL-safe and standard base64 happen to produce
> identical output (the input alphabet doesn't generate `+` or `/`), so the choice is
> defensive rather than load-bearing. Tests assert the encoding is URL-clean.

Returns the same job object as search, **plus**:

```json
{ "stellenangebotsBeschreibung": "Starttermine: 03.08.2026...\n\n...", "istBetreut": false,
  "allianzpartnerUrl": "http://www.arbeitsagentur.de", "allianzpartnerName": "arbeitsagentur.de" }
```

`stellenangebotsBeschreibung` is **plain text with real newlines** — no HTML tags, no
entity encoding. Nothing to strip or decode.

### Missing detail records

Some search results have no detail record and return **404** with:

```json
{ "messages": [ { "code": "STELLENANGEBOT_NICHT_GEFUNDEN" } ] }
```

Confirmed this is genuinely upstream and not an encoding bug: the same reference was
tried with standard base64 and URL-safe base64 (byte-identical here), both 404 with
the structured `STELLENANGEBOT_NICHT_GEFUNDEN` code rather than a generic error.
Likely partner-board syndicated listings, or postings expiring between the search and
detail calls. Measured 0/20 missing in one sample; 1 individual miss in another.
The CLI surfaces this as `{"error":"Job not found","code":"NOT_FOUND"}`, exit 1.

## Public web URL

```
https://www.arbeitsagentur.de/jobsuche/jobdetail/{referenznummer}
```

Uses the **raw** reference number (not base64). Verified 200 with a correct
`<title>`. This is what the CLI emits as each result's `url`, so it's directly
clickable and usable with `/apply`.
