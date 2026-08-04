---
name: scrape
description: >
  Finds new job postings matching your profile via installed portal-search CLIs
  (LinkedIn, local job boards, and any skills added with /add-portal). Deduplicates
  across runs. Triggers on: job scrape, find jobs, search jobs, new jobs, job search,
  scrape jobs, /scrape
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(bun --version), Bash(bun run .agents/skills/*/cli/src/cli.ts *), Bash(python3 tools/dedup_jobs.py *), WebFetch, WebSearch, Agent, AskUserQuestion, mcp__claude_ai_Indeed__search_jobs, mcp__claude_ai_Indeed__get_job_details
---

# Job Scraper

---

## How It Works

This skill searches job portals using the **installed portal-search CLIs** in
`.agents/skills/` (plus connected MCP portals and WebSearch as fallbacks), using
queries from your profile. It deduplicates against previously seen jobs and the
application tracker, and presents new matches with a quick fit assessment.

## Invocation

The user triggers this skill by saying things like:
- "Find new jobs"
- "Scrape for jobs"
- "Any new positions?"
- "/scrape"

Optional arguments:
- A focus area, e.g. "/scrape data science" or "/scrape geophysics"
- "broad" to run all search categories, e.g. "/scrape broad"
- "health" to run the portal health check only (Step 4.75), without searching, deduplicating, or presenting jobs - e.g. "/scrape health", or "/scrape health jobnet" to probe one portal even if disabled

---

## Execution Steps

### Step 0: Load State

1. Read `job_scraper/seen_jobs.json` (create if missing - start with `{"seen": {}}`)
2. Read `job_search_tracker.csv` to extract already-applied companies+roles
3. Read `search-queries.md` (this directory) for the search strategy

### Step 1: Search

Read `search-queries.md` (this directory) for the search strategy. By default, run the top 3 priority query categories. If the user said "broad", run all categories. If the user specified a focus area (e.g. "data science"), prioritize queries from that category.

**Use the installed CLI tools as the primary search mechanism.** Fall back to `WebSearch` only for portals that do not have a CLI skill, or if `bun` is unavailable on the system.

#### 1a. Check bun availability

```bash
bun --version
```

If this fails (bun not installed), skip to **1c (WebSearch fallback)** for all portals and note the fallback in the Step 5 output.

#### 1b. Run CLI tools (primary — run these in parallel where possible)

Discover all installed portal CLI skills by reading every `SKILL.md` found under `.agents/skills/*/SKILL.md`. Each file documents that portal's exact CLI flags and usage examples. **Use each portal's own documented interface — do not guess flags.** This approach automatically includes any new portals added via `/add-portal` without requiring changes to this file.

**Honor the `enabled` toggle.** A portal is enabled unless its `SKILL.md` frontmatter sets `enabled: false` (a missing key means enabled — the default). Skip each disabled portal and record it for the Step 5 summary. A fork can thus keep a portal installed but sit out a run without deleting its directory.

For each **enabled** portal skill:

1. Read its `SKILL.md` to find the correct `bun run …` invocation and supported flags.
2. Translate the query terms from `search-queries.md` into that portal's flag format (e.g. `--key`, `--search-string`, `--query`, filter codes — whatever the portal's SKILL.md specifies).
3. Scope to the last 14 days using the portal's supported recency flag (`--jobage`, `--since <YYYY-MM-DD>`, `--order PublicationDate`, etc. — as documented per portal).
4. Cap results to ~20 per call using the portal's limit flag.
5. Use `--format json` for machine-readable output.

Run all portal CLI calls in parallel where possible using the Agent tool. Collect all `results` arrays into a single pool for Step 2, keeping each result tagged with its source portal skill (for Step 2 `detail` lookups).

If a CLI tool exits with a non-zero code, log the error message and continue — do not abort the whole search.

#### 1b.5. MCP portals (Indeed)

Some portals are reached through a connected MCP tool instead of a CLI skill under
`.agents/skills/` — Indeed is the shipped example. If `mcp__claude_ai_Indeed__search_jobs`
is available in this session, call it directly (no `.agents/skills/` directory needed
for it — scraping Indeed is unreliable/ToS-risky, and the MCP tool is the authorized
channel):

1. For each query/location pair from `search-queries.md`, call `mcp__claude_ai_Indeed__search_jobs` with `search` (the query), `location` (a city or `"remote"`), and `country_code` set to the fork's market (e.g. `"DE"`).
2. For a promising result, use `mcp__claude_ai_Indeed__get_job_details` for the deeper Step 2 fetch instead of `WebFetch` — do not scrape indeed.com URLs directly.
3. Tag results from this path with `portal: "indeed"` the same as CLI results, so dedup/health-check logic treats it uniformly.
4. If the MCP tool isn't available in this session, skip Indeed entirely for this run (do not fall back to WebFetch/WebSearch scraping of indeed.com — its robots.txt blocks most automated paths).

#### 1c. WebSearch fallback

Use `WebSearch` for:
- Portals listed in `search-queries.md` that do **not** have a corresponding directory under `.agents/skills/` and are not covered by an MCP portal (1b.5) — this is also where "Google" coverage comes from: WebSearch queries (including `site:`-scoped ones from `search-queries.md`) rather than a maintained Google Jobs scraper, since Google Jobs has no public API and heavy anti-scraping protections.
- Any portal whose CLI fails at runtime
- When bun is unavailable (Step 1a failed)

Use the site-specific query strings from `search-queries.md` directly as WebSearch queries for these portals.

### Step 2: Fetch & Parse

For each promising result from Step 1:

**From CLI results:** Search output already includes title, company, location, date,
and URL. For jobs worth a deeper look, fetch full detail with that portal's `detail`
command (see its SKILL.md — do not guess flags) to extract **key requirements**,
**application deadline**, and a brief description snippet.

**From WebSearch results:** Use `WebFetch` on the posting URL and extract the same
fields manually.

For every candidate:
- Skip if its URL, or its **normalized dedup key** (below), already exists in `seen_jobs.json`
- Skip if the company+role already appears in `job_search_tracker.csv`

#### The normalized dedup key (required when running 2+ portals)

**Use the shipped implementation — do not hand-apply the rules below.** Save each
portal's `--format json` output to a file, then run:

```bash
python3 tools/dedup_jobs.py merge \
  arbeitsagentur-search=/tmp/aa.json xing-search=/tmp/xing.json stepstone-search=/tmp/ss.json \
  --seen job_scraper/seen_jobs.json
```

It returns `{"meta": {...}, "new": [...], "already_seen": [...]}` — `new` is the
pool to carry into Step 2.5 onward, already collapsed within the run, already
checked against the store, with `also_on` and `dedup_key` filled in. Add
`--update-seen job_scraper/seen_jobs.json` to write the results back (Step 4), or
`--format table` to eyeball it. One-off check: `python3 tools/dedup_jobs.py key
--company "Bertrandt AG" --title "Data Engineer (m/w/d)"`.

The tool is stdlib-only and covered by `tests/test_dedup_jobs.py`, whose cases are
the hand-labelled pairs from the two pressure-test pools. Applying the rules by
hand across ~100 records is slow and drifts between runs; the spec below is the
rationale and the maintenance reference, not a manual procedure.

URL matching alone **never** catches a cross-portal duplicate: the same posting has a
different URL on every board. Raw `company+title` matching misses most of them too,
because each portal renders the same job slightly differently. The key is:

```
dedup_key = normalize(company) + "|" + normalize(title)
```

`normalize()` applies, in order:
1. **Strip invisible characters** — `U+00AD` soft hyphen, `U+200B/C/D`, `U+FEFF`; convert `U+00A0` to a space. (Xing injects soft hyphens into titles and company names for typographic hyphenation: `"Da­ta En­gi­neer"` renders as `"Data Engineer"` but never string-matches it.)
2. **Lowercase** and transliterate German: `ä→ae, ö→oe, ü→ue, ß→ss`, then strip remaining accents. Case alone breaks matches in practice — `"bayoonet AG"` and `"BAYOONET AG"` are the same employer on two portals.
3. **Unify dash variants** — hyphen `-`, en-dash `–`, em-dash `—`, figure dash — to one character. Observed live: `"Securiton GmbH - IPS…"` on StepStone vs `"Securiton GmbH – IPS…"` on Xing, same job.
4. **Title only** — remove gender markers in all observed spellings: `(m/w/d)`, `(w/m/d)`, `(m/f/d)`, `(d/m/w)`, `(w/d/m)`, `(f/m/x)`, `(m/w/i)`, `(all genders)`, `(gn)`, a bare `*` or `(*)`, **and the slashless forms `(mwd)` / `(wmd)`**. Also strip the German gender-inclusive suffix: `Entwickler:in` / `Entwickler*in` → `entwickler`.
5. **Company only** — remove legal-form and group suffixes: `GmbH`, `mbH`, `AG`, `SE`, `KG`, `GmbH & Co. KG`, `OHG`, `GbR`, `e.V.`, `UG`, `gAG`, plus `Gruppe`/`Group`/`Holding`/`Deutschland`. Portals disagree constantly here — `"Bertrandt AG"` (StepStone) vs `"Bertrandt"` (Indeed), `"Bundesdruckerei Gruppe GmbH"` vs `"Bundesdruckerei-Gruppe"`.
6. **Collapse** everything non-alphanumeric to single spaces, trim.

**Match on exact equality of the normalized key. Do not use fuzzy/similarity matching.**

Measured across two independent live pools — `"Data Engineer"`/Berlin (96 records, 6
portals) and `"Softwareentwickler"`/München (86 records) — with duplicates
hand-labelled:

| Strategy | Recall | Wrong merges |
|---|---|---|
| URL or raw company+title (naive) | 13/18 (72%) | 0 |
| **Normalized key, exact match** | **18/18 (100%)** | **0** |
| Normalized + fuzzy ≥ 0.92 | 18/18 | 0 |
| Normalized + fuzzy ≥ 0.88 | 18/18 | **2** |

In **both** pools, every genuine duplicate scored a post-normalization similarity of
exactly **1.0000** — so fuzzy matching adds no recall whatsoever, only risk. The
highest-scoring pair that must *not* merge (`"Data Engineer* / Machine Learning
Engineer*"` vs `"Senior Data Engineer* / Machine Learning Engineer*"` at the same
employer) scored **0.9176**. A threshold below that silently collapses a senior role
into a mid-level one and the user never sees it — strictly worse than showing the same
job twice. Normalized-exact needs no threshold and cannot make that mistake.

**Known residual risk (unresolved by the evidence):** compound-word hyphenation —
`"Softwareentwickler"` vs `"Software-Entwickler"` — normalizes to different keys, since
step 6 turns the hyphen into a space. In both pools every such pair was a genuinely
different job, so there was no case to justify collapsing them, and doing so blindly
risks merging distinct roles. Left deliberately unmerged; revisit only if a real
duplicate is ever observed spanning the two spellings.

Same-portal duplicates exist too — confirmed in both pools (Xing returned one job twice
with an identical URL; StepStone returned two KNDS postings twice each). The same key
handles them, so apply it within a run, not just against `seen_jobs.json`.

Expect roughly **6–14% redundancy** in a multi-portal pool for one query (measured
across the two pools). Cross-portal overlap is lower than it looks, because
`arbeitsagentur-search` surfaces a great deal the commercial boards do not — the
sources are complementary, not repetitive.

When two portals surface the same job, keep the entry whose portal gives the richest
detail (prefer one with a working `detail` command and a full description) and record
the others in that entry's `also_on` list rather than dropping them silently, so the
user can still reach the posting if one portal's link rots.

### Step 2.5: Mass-Posting Detection (within this run)

A distribution pattern worth flagging to the user as a caution signal, not as an accusation against the employer - it describes how a listing is being distributed, not a verdict on whether the company is legitimate. It alone proves nothing is wrong (companies do legitimately hire the same role across several cities); flag it so the user can factor it in when deciding whether to invest time, don't downgrade fit or silently exclude the result because of it.

If two or more results in this run's pool (from the same company, or sharing the same req/job ID visible in the URL or title) have substantially the same description and differ only in city/location/title, don't present them as separate rows. Consolidate into a single row and note the spread, e.g. "posted identically across 6 cities (BR, MX, GT)".

### Step 3: Quick Fit Assessment

For each new job, do a rapid fit check (NOT the full evaluation from `04-job-evaluation.md` - just a quick signal):

- **High match**: Role directly involves your core skills
- **Medium match**: Role is adjacent to your experience
- **Low match**: Role requires significant skills you lack

**Language override:** before assigning a match level, check the posting against `04-job-evaluation.md`'s Language Gate (a required language you haven't declared at all in your CLAUDE.md Languages table). A required language that's entirely undeclared overrides skill fit: mark it **Low** regardless of how well the skills align, and name it in the highlight bullets so it isn't buried under an otherwise-good-looking match. A **declared** language at a requirement that reads higher than your declared level is *not* an override — score fit normally, but add a red-flag bullet under that job's highlights (Step 5) quoting the posting's requirement next to your declared level, so the gap is visible without being auto-downgraded.

### Step 4: Deduplicate & Store

Re-run the Step 2 command with `--update-seen` to persist the pool:

```bash
python3 tools/dedup_jobs.py merge <portal>=<file> … \
  --seen job_scraper/seen_jobs.json --update-seen job_scraper/seen_jobs.json
```

This writes new entries under the normalized key, unions `also_on`, and **never
overwrites an existing entry's other fields** — so a `/rank` score survives a later
`/scrape`. It sets `title`, `company`, `url`, `first_seen`, `portal`, `status`;
fill in `fit` (Step 3) with Edit afterwards, and use the schema below when doing so.

1. Add ALL fetched jobs (new and skipped) to `seen_jobs.json` with structure:
```json
{
  "seen": {
    "<normalized dedup key: normalize(company)|normalize(title) — see Step 2>": {
      "title": "...",
      "company": "...",
      "url": "...",
      "first_seen": "YYYY-MM-DD",
      "fit": "high/medium/low",
      "status": "new/skipped/evaluated/ranked/expired",
      "portal": "<source portal skill, e.g. jobindex-search, or \"indeed\" for the Step 1b.5 MCP path>",
      "also_on": [{"portal": "<other portal>", "url": "<its url for the same job>"}]
    }
  }
}
```

The `portal` field records which CLI skill produced the job (results are already tagged per portal in Step 1b - persist that tag here). Entries written before this field existed lack it; the health check (Step 4.75) attributes those by matching the URL's domain against each portal's base URL, so do not backfill.

`also_on` lists the other portals that surfaced the *same* job in the same run (see the normalized dedup key in Step 2). It is optional and often absent — a job found on one portal only has no `also_on`, and entries written before this field existed lack it. Never backfill it by guessing; it is only ever written from duplicates actually observed together in a run. Two practical uses: a fallback link if one portal's URL rots, and a signal for the Step 4.75 health check (a portal that used to co-occur on many jobs and now co-occurs on none may have started returning junk).

**Do not key `seen_jobs.json` on the raw URL.** Older entries may be keyed that way; read them tolerantly, but write new entries under the normalized key. A URL-keyed store re-adds the same job every time a different portal surfaces it.

`/rank` extends this schema additively: ranked entries also carry `rank_score` (0–100 overall score), `rank_verdict` (fit band, e.g. "strong fit"), `rank_date` (ISO date of ranking), and `strengths`/`gaps` (1-3 verbatim bullets each, copied from the scoring agent's findings). The `status` field is set to `"ranked"`. Do not drop any of these fields when re-writing entries. Entries ranked before `strengths`/`gaps` existed simply lack them; readers tolerate their absence and never backfill by guessing.

2. Only present jobs NOT already in the seen list or tracker.

### Step 4.5: Generate Referral Contact Links (High & Medium Fit Only)

For every job from this run with `fit` of **high** or **medium** (skip low-fit jobs),
build two LinkedIn people-search URLs so the user can find a recruiter or team member to
reach out to for a referral or a warm intro. This is deliberately a link-generation step,
not an automated lookup: no scraping, no third-party API, zero runtime dependencies or
credentials required.

**A. Recruiters / Talent Acquisition (the referral path)**
```
https://www.linkedin.com/search/results/people/?keywords=<url-encoded "<Company Name> recruiter">&origin=GLOBAL_SEARCH_HEADER
```

**B. Role/team peers (informational-outreach / warm-intro path)**
```
https://www.linkedin.com/search/results/people/?keywords=<url-encoded "<Company Name> <role keyword>">&origin=GLOBAL_SEARCH_HEADER
```
Use a short keyword drawn from the posting's title for `<role keyword>` - e.g. a posting
titled "AI Program Manager" becomes `"<Company Name> AI Program Manager"`.

Both links are for the user to open and browse themselves - never fetch or scrape the
LinkedIn people-search result pages programmatically. Never fabricate contacts or claim a
specific person was found; these are search links, not results.

### Step 4.75: Portal Health Check

Scraper-based portal CLIs rot silently: when a portal changes its markup, the parser usually exits 0 with zero results or with null/garbled fields, and the Step 1c fallback never fires because it only triggers on hard failure. This step catches that from evidence the run already holds.

**Free pass (no extra requests).** For each enabled portal that ran in Step 1b:

- **Degraded scan:** inspect the results it returned this run. Flags: `company` null or empty on every result, empty titles, undecoded entities (`&amp;`) or HTML fragments in titles, URLs that do not point at the portal. Any of these means the parser is half-working and `/scrape` is silently collecting junk.
- **Yield history:** if the portal returned zero results across all of this run's queries, check whether `seen_jobs.json` holds prior entries from it (via the `portal` field, or by matching URL domains for entries predating the field). A portal that produced jobs on earlier runs and produces nothing now is suspect - the same queries worked before.

**Escalation (bounded, on suspicion only).** A suspect portal gets **one** sentinel probe: run its documented `search` with the example query from its own SKILL.md (that query provably worked when the skill was registered), the portal's limit flag capped at 3, `--format json`. If that returns nothing, retry **once** with a single common word. Only then is the verdict **broken**. A 429 or block page is **never** evidence of breakage - record the portal as **inconclusive (rate-limited)**, back off, and do not retry.

**Verdicts.** Healthy portals get silence - no table, no line. Anything else surfaces in the Step 5 summary as a health line.

**Probe-only mode (`/scrape health`).** Skip Steps 1-4 and this step's free pass (there is no fresh run to scan); instead probe every installed portal directly - enabled ones by default, a disabled one only when named explicitly (e.g. `/scrape health jobnet`). Each portal gets the sentinel probe above, the degraded criteria applied to whatever it returns, and - since the user explicitly asked for diagnosis - one `detail` fetch on the first result of each healthy portal (description must be readable decoded text; a failure downgrades to degraded). Report all statuses in this mode, including healthy. Volume stays bounded: one search, at most one retry, at most one detail per portal.

### Step 5: Present Results

Present new jobs in a table sorted by fit (high first). When Step 1b skipped
portals (`enabled: false`), report them with the `skipped (disabled):` line below
so opting one out stays visible rather than silent; omit the line when nothing
was skipped. When Step 4.75 found a portal degraded, broken, or inconclusive,
add one `health:` line per suspect portal (healthy portals get no line); after
the report, offer to set that portal's `enabled: false` so `/scrape` stops
running it (and covers it via the Step 1c fallback) until it is fixed - only
edit the toggle with the user's confirmation, and never edit anything else in
the skill.

```
## New Job Matches - YYYY-MM-DD

Found X new positions (Y high, Z medium, W low match).

skipped (disabled): <portal-name>, <portal-name>

health: <portal-name> - degraded (company null on all 12 results); parsing anchors in .agents/skills/<portal-name>/url-reference.md
health: <portal-name> - broken (0 results for the SKILL.md test query and a broader retry); parsing anchors in .agents/skills/<portal-name>/url-reference.md

| # | Fit | Title | Company | Location | Deadline | URL |
|---|-----|-------|---------|----------|----------|-----|
| 1 | High | ... | ... | ... | ... | [Link](...) |

If Step 2.5 flagged a mass-posting pattern, note it in the Title cell (e.g. "Frontend Developer (posted in 6 cities)") rather than burying it. Do the same for a declared-language-insufficient-level flag from the Language Gate (e.g. "Backend Engineer ⚠ fluent English required") - both are signals the user should see at a glance, not just in the detail highlights below.

### High-Match Highlights
For each high-match job, add 2-3 bullet points:
- Why it matches your profile
- Key requirements to check
- Any red flags (including mass-posting signals from Step 2.5)

### Contacts
For each high/medium-fit job from Step 4.5, add a short contacts block with the two
LinkedIn search links:
- Recruiters/TA search link, for the referral path
- Role/team-peer search link, for the warm-intro / informational-outreach path
```

After presenting, ask:
> "Want me to evaluate any of these in detail? Just give me the number(s)."

If the user picks a number, invoke the **job-application-assistant** skill workflow (fit evaluation first, then CV + cover letter if approved).

If the run found many new jobs (roughly 8+), also suggest `/rank` - it batch-scores all new postings against the full fit framework and returns a ranked shortlist, which beats eyeballing a long table. (`/rank` sets the `ranked` and `expired` status values in `seen_jobs.json`; treat both as already-seen for dedup purposes.)

### Step 6: Update Tracker (Optional)

If the user decides to apply to any job, add a row to `job_search_tracker.csv`.

---

## Important Rules

1. **Never fabricate job postings.** Only present jobs from actual CLI search/detail output or WebSearch/WebFetch results.
2. **Respect deduplication.** Always check seen_jobs.json AND job_search_tracker.csv before presenting.
3. **Focus on configured geographic area.** Skip jobs that require relocation or are clearly outside commute range.
4. **Only open positions.** Skip postings with expired deadlines or those marked as closed.
5. **Be efficient with detail fetches.** Don't run `detail` or WebFetch on every search hit — pre-filter by title/snippet, then fetch only promising matches.
6. **Parallel searches.** Run portal CLI searches in parallel; use WebSearch only for gaps the CLIs don't cover.
7. **No automated people lookups.** Referral contacts (Step 4.5) are LinkedIn search links only - never fetch or scrape LinkedIn people-search result pages programmatically.
8. **Health checks are bounded and honest.** Step 4.75 spends at most one probe, one retry, and (in `health` mode) one detail fetch per portal - a diagnosis, not a crawl. A rate-limit is never evidence of breakage. Health verdicts come only from observed CLI output; a portal that could not be tested is reported as inconclusive, never guessed. The `enabled` toggle is the only thing the health check may edit, and only with confirmation.
9. **Flag distribution patterns, never accuse.** The mass-posting signal (Step 2.5) describes how a listing is being distributed, not a claim that the employer is a scam. Never name a company as fraudulent or untrustworthy - present the observation and let the user decide.
