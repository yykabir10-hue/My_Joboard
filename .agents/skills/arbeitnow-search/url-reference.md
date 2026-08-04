# Arbeitnow — endpoint reference

## Search: Job Board API

```
GET https://www.arbeitnow.com/api/job-board-api?page=<n>
```

- No authentication, no API key.
- `?page=` is the only documented/working parameter (confirmed via `meta.info` in the
  response itself: "Jobs are updated every hour and ordered by the `created_at`
  timestamp. Use `?page=` to paginate.").
- **No server-side search/filter param exists.** Empirically tested `?search=`, `?q=`,
  `?tags=`, `?title=`, `?keyword=` — every variant returned the identical result set as
  no params at all (same count, same first job). The API silently ignores unknown
  params rather than erroring. This is why `--query`/`--location`/`--jobage` are all
  client-side filters in this CLI, applied to whichever page was fetched.
- Page size is **not fixed** — observed 175 results on page 1, 100 on page 2. Do not
  assume a constant page size when building pagination UX.
- Response shape:
  ```json
  {
    "data": [
      {
        "slug": "deployment-strategist-berlin-3698",
        "company_name": "Stackgini GmbH",
        "title": "Deployment Strategist (f/m/d)",
        "description": "<p>...full HTML description...</p>",
        "remote": false,
        "url": "https://www.arbeitnow.com/jobs/companies/stackgini-gmbh/deployment-strategist-berlin-3698",
        "tags": ["Business Development"],
        "job_types": ["professional / experienced"],
        "location": "Berlin",
        "created_at": 1785771035
      }
    ],
    "links": { "first": "...", "last": null, "prev": null, "next": "...?page=2" },
    "meta": { "current_page": 1, "per_page": 175, "terms": "...", "info": "..." }
  }
  ```
- `created_at` is **unix seconds** (not milliseconds).
- The search response already includes the **full job description** — no separate
  detail fetch is strictly needed for search results, but `detail` exists for the
  contract and for resolving a bare slug/URL passed in from elsewhere.

## Detail: job page + embedded JSON-LD

There is **no per-slug API lookup** (`/api/job-board-api/<slug>` and
`/api/jobs/<slug>` both 302-redirect, not a direct hit). Instead:

```
GET https://www.arbeitnow.com/jobs/companies/<company-slug>/<job-slug>
```

This is the `url` field each search result already carries. The page is server-rendered
and embeds a single `<script type="application/ld+json">` block with a schema.org
`@graph` containing one `JobPosting` node:

```json
{
  "@context": "https://schema.org/",
  "@graph": [
    {
      "@type": "JobPosting",
      "title": "...",
      "description": "<?xml encoding=\"UTF-8\"><p>...</p>",
      "hiringOrganization": { "name": "..." },
      "jobLocation": { "address": { "addressLocality": "...", "addressRegion": "...", "addressCountry": "..." } },
      "employmentType": "FULL_TIME",
      "datePosted": "2026-08-03 15:14:37+02",
      "validThrough": "2026-10-26T16:30:35.000000Z",
      "url": "..."
    }
  ]
}
```

Parsing this JSON-LD block is more stable than regex-matching the page's CSS classes
(which are minified/hashed Next.js chunk-derived names, e.g. `data-at="job-item"` style
anchors don't appear on the individual job page the way they do on `arbeitnow.com` list
views — this endpoint is a different page template).

Quirks observed:
- `description` starts with a stray `<?xml encoding="UTF-8">` processing-instruction
  string that isn't valid HTML — stripped before further parsing.
- German umlaut/typographic entities (`&auml;`, `&ouml;`, `&uuml;`, `&szlig;`, `&rsquo;`,
  `&ndash;`, ...) appear in descriptions; the basic XML-escape entity set (`&amp;` etc.)
  is not sufficient — see `NAMED_ENTITIES` in `cli/src/helpers.ts`.
- `datePosted`/`validThrough` formats are inconsistent between fields (one is a
  `YYYY-MM-DD HH:MM:SS+TZ` string, the other full ISO-8601) — passed through as-is
  rather than reformatted, since both are human-readable.

## robots.txt

`https://www.arbeitnow.com/robots.txt` is fully permissive for `User-agent: *`
(only a couple of unrelated paths disallowed: `/*?__hstc`, `/jobs/companies/*/apply`).
No personal-use-only warning needed for this source.
