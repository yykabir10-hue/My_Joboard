# StepStone.de — endpoint reference

## robots.txt

`https://www.stepstone.de/robots.txt`, `User-agent: *` block, disallows only legacy
paths: `/5/ergebnisliste.html`, `/5/advanced-job-search.html`, `/5/index.cfm/`,
`/aboutus/`, `/admin/`, and similar — **not** the current `/jobs/...` search route.
A separate `User-agent: Jobsearch1.5` block disallows `/jobs/vollzeit/`,
`/jobs/teilzeit/`, `/jobs/home-office/`, and `/jobs/*?*` (with an `Allow` carve-out for
`?q=*`), but that block applies only to a bot literally named `Jobsearch1.5`, not to
`User-agent: *`. No personal-use-only warning is required on the same basis the repo
applies it to `linkedin-search`/`xing-search`.

## Search: server-rendered HTML

```
GET https://www.stepstone.de/jobs/<query-slug>/in-<city-slug>[?page=N]
```

- `<query-slug>`: lowercase, spaces/punctuation to hyphens (`"Data Engineer"` →
  `data-engineer`). Both segments are optional — `/jobs` alone works (broad/no-op
  search), `/jobs/<query>` alone works (nationwide), confirmed live.
- `<city-slug>`: German umlaut transliteration matching StepStone's own convention:
  ä→ae, ö→oe, ü→ue, ß→ss (München → `muenchen`, Köln → `koeln`, Düsseldorf →
  `duesseldorf` — all confirmed against real StepStone URLs found in-page).
- `?page=N`: confirmed via the page's own pagination links
  (`aria-label="N von <total>"`, `rel="next"`). No `Allow`-listed alternate param found.
- **No working job-age filter parameter was found.** Tried `?ag=7` (a historically
  plausible StepStone param) — empirically it changes nothing: identical
  `searchResultsTotalJobCount` and no `searchResultsFilterValuesActivated` entry with
  or without it. No date-filter facet UI was found in the static HTML either (the
  facet panel appears to be client-rendered post-hydration, not present in the raw
  SSR response). `--jobage` is therefore a **client-side, approximate** filter based
  on parsing each card's relative-time text.
- StepStone's own JSON API (`https://www.stepstone.de/public-api/resultlist/`, found
  referenced in the page's JS bundle) returns **403** on a direct call even with a
  browser User-Agent and a same-origin `Referer` header — it requires session state
  only a real browser establishes. Not usable from a bare HTTP client.

### Card markup (per job)

Anchor (title + href + numeric ID — the reliable per-card boundary):
```html
<a href="/stellenangebote--<Title-Slug>--<jobID>-inline.html" data-testid="job-item-title" data-at="job-item-title">
  <div><div><div>Actual Title Text</div></div></div>
</a>
```
The bare substring `data-at="job-item-title"` **over-counts** — some pages embed a
matching CSS attribute selector (`[data-at="job-item-title"]{...}`) inside a `<style>`
block, which contains the same string but is not a real card. The parser requires the
`href="/stellenangebote--...--<digits>-inline.html"` attribute on the same tag to
disambiguate — this consistently gave exactly the true per-page job count (25) across
every page fetched during development.

Company and location each follow the same "icon then text" shape, anchored on
`data-at="job-item-company-name"` / `data-at="job-item-location"` respectively:
```html
<span data-at="job-item-company-name">
  <span data-genesis-element="ICON_CONTAINER"><svg>...</svg></span>
  <span data-genesis-element="TEXT">COMPANY NAME</span>              <!-- OR: -->
  <span data-genesis-element="TEXT"><div>COMPANY NAME</div></span>  <!-- line-clamp variant -->
</span>
```
Both variants (with/without the inner `<div>` line-clamp wrapper) were observed on
real pages within the same result set — the parser handles both. Exact CSS class
names (`res-du9bhi` etc.) are Emotion-generated build hashes and are **not** treated
as stable; only the `data-at`/`data-genesis-element` attributes are relied on.

Posted date — relative text only, no machine-readable timestamp found anywhere on
the page (checked for a `datetime` attribute on the `<time>` tag: absent):
```html
<span data-at="job-item-timeago"><time class="">vor 5 Tagen</time></span>
```
Observed values: `vor N Stunden`, `vor N Tagen`, `vor 1 Woche`, `vor N Wochen`. Not
observed but plausible: `Heute`, `Gestern` (handled defensively in the parser).

## Detail: NOT live-verified

```
GET https://www.stepstone.de/stellenangebote--<Title-Slug>--<jobID>-inline.html
```

Every fetch attempt against this route during development failed with an HTTP/2
stream reset (`curl` exit codes 92/28, Bun `fetch` throwing rather than returning a
response) — across multiple job IDs, multiple backoff intervals (5s, 10s, 25s+), both
HTTP/2 and forced HTTP/1.1. This is a distinct failure mode from the search route
(which fetched successfully dozens of times in the same session) and from a simple
429/403 (which the CLI's retry-with-backoff already handles) — it looks like
connection-level bot mitigation (TLS/HTTP2 fingerprinting) specifically hardening the
apply-adjacent detail-page route, consistent with the `Jobsearch1.5`-scoped
`Disallow: /jobapply`, `Disallow: /direkt-bewerben.html` entries in robots.txt
suggesting StepStone treats the application funnel as more sensitive than search.

**Consequence:** the ground-truth markup of the detail page was never observed.
`cli/src/helpers.ts`'s `parseJobDetailFromHtml` is implemented against the
schema.org `JobPosting` JSON-LD pattern that a wide swath of job sites use (and that
`arbeitnow-search` confirmed works there) as a reasonable best-effort, but it is
explicitly unverified for StepStone. If you can reach the detail page from your own
network (a residential IP, a different client fingerprint, etc.), please update this
file with what you find and adjust the parser accordingly — do not treat the current
implementation as confirmed.
