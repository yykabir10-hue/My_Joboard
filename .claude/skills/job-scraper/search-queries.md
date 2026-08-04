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
- **arbeitnow.com** - installed but **not used for this search**: probed with `Verfahrensingenieur`, `Process Engineer` and `Werkstudent Verfahrenstechnik` it returned 0 results every time. It is a tech/remote board and carries nothing for process engineering.
- **linkedin.com/jobs** - filter to Germany / a German city; `linkedin-search` CLI (personal-use only)
- **indeed.com/de** (or `de.indeed.com`) - reached via the connected Indeed MCP tool (`country_code: "DE"`), not a CLI — see `job-scraper/SKILL.md` Step 1b.5
- **[YOUR_INDUSTRY_JOB_BOARD]** - a niche/industry board for your field, e.g. `get-in-it.de` (IT), `honeypot.io` (tech) (optional — scaffold with `/add-portal`)

Secondary (company career pages / broad discovery via WebSearch):
- Direct WebSearch queries with `site:` filters for known target companies, or as a backstop when a CLI degrades (see `job-scraper/SKILL.md` Step 4.75 health check)

## Query Categories

Queries are grouped by priority. Write **each category in every language from your Languages table** (see Language scope above). Combine each query with your location terms (e.g. your city, region, or metro area) where the site supports it.

### Priority 1: Process / chemical engineering roles

Core title phrasings, taken from live German postings (see `job_scraper/search-profiles.json`).

```
site:stepstone.de "Verfahrensingenieur" OR "Prozessingenieur"
site:xing.com/jobs "Chemieingenieur"
site:indeed.com/de "Verfahrensingenieur (m/w/d)"
site:linkedin.com/jobs "Process Engineer" Germany
"Verfahrenstechniker" Stellenangebote Deutschland
```

### Priority 2: Simulation and process design

```
"Prozesssimulation" OR "Process Simulation" Stellenangebote
"Massen- und Energiebilanzen" Verfahrenstechnik
"Aspen Plus" OR "Prozess-Simulationssoftware" Stellenangebote
site:linkedin.com/jobs "Process Design & Optimization" Germany
```

### Priority 3: Werkstudent / Praktikum / Abschlussarbeit

Student and thesis roles are targets, not noise - do **not** filter these out.

```
"Werkstudent Verfahrenstechnik" OR "Werkstudent*in Energietechnik"
"Praktikum Verfahrenstechnik" OR "Pflichtpraktikum" Verfahrenstechnik
"Praktikum/Abschlussarbeit" Verfahrenstechnik OR Energietechnik
site:stepstone.de Werkstudent Verfahrenstechnik
```

### Priority 4: Domain specialisations

Gas processing, thermal separation, and energy transition.

```
"Biogasaufbereitung" OR "Gasreinigungsanlagen" Stellenangebote
"CO2-Verflüssigung" OR "Verfahrensfließbild" OR "R&I Fließbild"
"Destillation" OR "Rektifikation" Verfahrensingenieur
"Trenntechnik" OR "Wärmetauscher" OR "Lösungsmittelrückgewinnung"
"HAZOP" OR "DGRL" OR "ATEX" OR "DVGW" OR "AD2000" Ingenieur
"Erneuerbare Energien" OR "Energiewende" Ingenieur
```

## Location Filter

When evaluating results, verify the job location is within reasonable commute distance from your home. Define acceptable areas:
- [YOUR_CITY] and surrounding areas
- [ACCEPTABLE_AREA_1]
- [ACCEPTABLE_AREA_2]
- [BORDERLINE_AREA] (borderline - ~X min by transit)
- [TOO_FAR_AREA] (too far)

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
