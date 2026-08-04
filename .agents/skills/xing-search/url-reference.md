# Xing — endpoint reference

## robots.txt

`https://www.xing.com/robots.txt`, `User-agent: *` block, disallows:
```
Disallow: /jobs/search/
Disallow: /jobs/search?*
```
along with `/graphql/`, `/xing-one/api`, and most other API-shaped paths. Per repo
policy this means a personal-use-only warning is required (see `SKILL.md`), same
treatment as `linkedin-search`. Note the search-*results* page itself does not
require login to view snippets — confirmed live (fetched without any session cookie,
got real job cards back).

## Search: server-rendered HTML

```
GET https://www.xing.com/jobs/search/ki?keywords=<query>&location=<location>&page=<n>
```

- `keywords`/`location` are plain (URL-encoded) text, no slugification needed (unlike
  StepStone's path-segment scheme).
- `page` confirmed working: page 1 vs `page=2` returned entirely different job IDs.
- **No working job-age/sort parameter found.** Tried `sort=date` — returned byte-identical
  first-page job ordering to no param at all. No other date/age param name was found in
  the static markup (no facet UI with real hrefs present in the raw SSR response,
  similar to StepStone). `--jobage` is a client-side filter on each card's own
  `<time dateTime="...">` value.

### Card markup (per job)

```html
<div data-testid="job-search-result" aria-label="<Title>. Klicke zum Öffnen...">
  <a href="/jobs/<city-title-slug>-<jobID>" target="_blank" class="...CardLink..."></a>
  ...
  <h2 data-testid="job-teaser-list-title">Actual Title</h2>
  <p>Company Name</p>                                          <!-- immediate next sibling -->
  <div class="multi-location-display-styles__Container-...">
    <p>
      <span>City1<!-- -->, </span><span>City2<!-- -->, </span><span>City3</span>
      <b class="...OverflowLabel...">&nbsp;+ 0 weitere</b>       <!-- "+N more", stripped -->
    </p>
  </div>
  ...
  <span data-xds="Marker" role="status"><span>Vollzeit</span></span>   <!-- employment type -->
  <p data-xds="Meta"><time dateTime="2026-07-30T06:01:22Z">Vor 4 Tagen</time></p>  <!-- OR: <p data-xds="Meta"></p> — empty, no date shown -->
</div>
```

Key findings from live inspection (two real searches, 20 cards each):
- **Chunk boundary**: `data-testid="job-search-result"` gave exactly the real card
  count both times (20/20) — unlike StepStone, no CSS-selector pollution was found
  (this is a client-rendered React app, not SSR'd `<style>` blocks with attribute
  selectors), so no extra disambiguation via `href` was needed for splitting, though
  `href` is still required per-card to get the job ID.
- **Company**: the `<p>` immediately following the `data-testid="job-teaser-list-title"`
  `<h2>` — no dedicated `data-testid` of its own, but the sibling relationship is
  reliable (0 nulls across 20 real cards).
- **Location**: single-city cards render as plain text inside the location `<p>`;
  multi-city cards split each city into its own `<span>` with a `<!-- -->` React
  hydration comment between them (`<span>Aschaffenburg<!-- -->, </span>...`) — the
  parser strips all tags/comments and joins the result, giving
  `"Aschaffenburg, Berlin, Oldenburg"`.
- **Sponsored/promoted listings**: confirmed at least one card per typical 20-result
  page whose `href` points to a third-party ad-tracking redirect
  (`https://tnl2.jometer.com/v2/job?jx=...`) instead of `xing.com/jobs/...`. These
  have no stable Xing job ID and are **excluded** from results (see `parseJobCards`).
- **Missing dates**: roughly half of a real 20-card result set had an **empty**
  `<p data-xds="Meta"></p>` — no `<time>` element, no date shown to the user either.
  This is a genuine data characteristic, not a parsing failure — `date` is `null`.

## Detail: server-rendered HTML + JSON-LD (live-verified)

```
GET https://www.xing.com/jobs/<city-title-slug>-<jobID>
```

No login wall for the description — confirmed by fetching a real job page with no
session cookie and getting the full text back. The page embeds a single schema.org
`JobPosting` as JSON-LD:

```html
<script data-ch type="application/ld+json">
{"@context":"https://schema.org/","@type":"JobPosting","title":"...",
 "description":"<p>...</p>","datePosted":"2026-06-30T06:01:22Z",
 "directApply":true,"url":"https://www.xing.com/jobs/...",
 "validThrough":"2026-08-29T06:01:23Z","industry":"Informationsdienste",
 "employmentType":"Vollzeit","hiringOrganization":{"@type":"Organization","name":"..."},
 "jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Berlin","addressRegion":"Berlin","addressCountry":"DE"}}]}
</script>
```

Note the `data-ch` attribute **before** `type=` — a regex assuming
`<script type="application/ld+json">` with no other attributes will match zero
occurrences on this page (this was caught during development). The parser matches
`<script[^>]*type="application/ld\+json"[^>]*>` to tolerate attribute order/extras.

`description` contains real HTML (`<p>`, `<ul>`, `<li>`, `<h2>`, ...) which is
stripped/decoded the same way as the other German-market portal skills.
