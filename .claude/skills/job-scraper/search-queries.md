# Search Queries for Job Scraper

<!-- SETUP: Customize these queries based on your skills, target roles, and location -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first: `arbeitsagentur-search`, `stepstone-search`, `xing-search`, plus the country-agnostic `linkedin-search` and `freehire-search` (both already cover Germany with no changes). Indeed is reached via a connected MCP tool instead of a CLI — see `job-scraper/SKILL.md` Step 1b.5. You do **not** need a matching `site:` line below for any of these to run.

**Prefer `arbeitsagentur-search` as the primary German source.** It is the federal employment agency's official API — the largest German job database, with genuine server-side date filtering and full plain-text descriptions — and unlike the HTML-scraping portals it cannot break from a markup change. Treat `stepstone-search`/`xing-search` as breadth on top of it, not as the backbone.

The four Danish demo portals (`jobindex-search`, `jobnet-search`, `jobbank-search`, `jobdanmark-search`) are installed but disabled (`enabled: false`) in this fork — re-enable them if you also want Danish coverage.

The `site:` query templates in this file are the **WebSearch fallback** — for company career pages, Google-Jobs-style broad discovery, or when a CLI fails. This is also what "Google" coverage means in this framework: there is no dedicated Google Jobs scraper (no public API, heavy anti-scraping on Google's side), so Google-style discovery runs through `WebSearch` with these query strings.

**Language scope:** write every query category in every language listed in your CLAUDE.md Languages table. Germany's job boards are predominantly German-language even for English-friendly roles (StepStone/Xing postings mix both) — include German-language query variants even if your own CV/CLAUDE.md language is English, since many strong-fit postings simply won't surface otherwise. A posting requiring a language you have *not* declared, as a job condition, is excluded before scoring; a posting requiring a *higher level* than you declared in a language you *do* work in is flagged for your own judgment, not excluded — see `04-job-evaluation.md`'s Language Gate, the single source of truth for this rule.

## Search Sites

Primary (German job boards, all covered by an installed CLI or MCP tool — no `site:` line needed):
- **arbeitsagentur.de** - the federal employment agency's official job board, Germany's largest job database; `arbeitsagentur-search` CLI (official public API — **start here**)
- **stepstone.de** - one of Germany's largest general job boards; `stepstone-search` CLI
- **xing.com/jobs** - DACH professional network; `xing-search` CLI (personal-use only, see its SKILL.md)
- **arbeitnow.com** - installed but **disabled by default** (see `job_scraper/search-profiles.json`'s `_comment`): a prior probe with process-engineering queries returned 0 results every time on a tech/remote board. Not yet re-probed with photonics/Werkstudent queries - worth testing before assuming it carries nothing for this field either.
- **linkedin.com/jobs** - filter to Germany / a German city; `linkedin-search` CLI (personal-use only)
- **indeed.com/de** (or `de.indeed.com`) - reached via the connected Indeed MCP tool (`country_code: "DE"`), not a CLI — see `job-scraper/SKILL.md` Step 1b.5
- **[YOUR_INDUSTRY_JOB_BOARD]** - a niche/industry board for your field, e.g. `get-in-it.de` (IT), `honeypot.io` (tech) (optional — scaffold with `/add-portal`)

Secondary (company career pages / broad discovery via WebSearch):
- Direct WebSearch queries with `site:` filters for known target companies, or as a backstop when a CLI degrades (see `job-scraper/SKILL.md` Step 4.75 health check)

## Query Categories

Queries are grouped by priority. Write **each category in every language from your Languages table** (see Language scope above). Combine each query with your location terms (e.g. your city, region, or metro area) where the site supports it.

### Priority 1: Photonics / Optics / Laser Werkstudent roles

Core title phrasings, taken from the werkstudent_digest_2026-08-08.txt scrape already reviewed and mirrored into `job_scraper/search-profiles.json`. Student/Werkstudent/Hilfskraft roles are the **target** here, not noise - do not filter them out.

```
"Werkstudent Photonik" OR "Werkstudent*in Photonik"
"Werkstudent Optik" OR "Werkstudent*in Optik"
"Werkstudent Laser" OR "Werkstudent*in Laser"
"Studentische Hilfskraft" Photonik OR Laser OR Optik
site:stepstone.de "Werkstudent" Photonik OR Optik OR Laser
site:xing.com/jobs "Werkstudent" Photonik OR Optik OR Laser
site:linkedin.com/jobs "Werkstudent" Photonics OR Optics OR Laser Germany
"Praktikum" Photonik OR Optik OR Laser Deutschland
"Bachelorarbeit" OR "Masterarbeit" Photonik OR Laser OR Optoelektronik
```

### Priority 2: Photonics-adjacent physics/engineering Werkstudent roles

Secondary net per CLAUDE.md's Target Sectors - X-ray/industrial metrology, semiconductor, quantum, precision positioning, general photonics-company R&D.

```
"Werkstudent" Röntgentechnik OR "Industrielle Röntgentechnik"
"Werkstudent" Halbleitertechnik OR Quantum OR "Quantum Computing"
"Werkstudent" Nanopositionierung OR "Precision Positioning"
site:xing.com/jobs "Werkstudent" Elektrotechnik Fraunhofer
"Working Student" Photonics OR Quantum Germany
```

### Priority 3: Company-specific discovery (WebSearch fallback)

Companies that recur across the digest as strong-fit employers - use when a CLI portal degrades or to catch roles not yet indexed by the CLIs above.

```
site:careers.zeiss.com Werkstudent
site:jenoptik.com Werkstudent OR careers
site:toptica.com career Werkstudent OR Praktikant
site:jobs.dlr.de Werkstudent Photonik OR Laser OR Optik
"Fraunhofer" "Studentische Hilfskraft" Photonik OR Laser
```

## Location Filter

Nationwide search, per the user's explicit preference during `/setup` (willing to relocate/commute for the right role) - matches the scope already used in `job_scraper/search-profiles.json` and the digest already reviewed.
- Steinfurt, NRW (home base) and surrounding areas
- Nationwide Germany - no location filter applied by default (mirrors the digest's coverage of Aachen, Berlin, Stuttgart, Munich, and elsewhere)
- Re-run `/setup --section search` to switch to a commutable-region-only filter if this becomes too broad in practice

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
