# German AI Job Search

*A job search agent for the German market that runs on your machine.*

An AI-powered job application workspace built on [Claude Code](https://claude.com/claude-code).
It searches German job boards, deduplicates results across them, scores fit against your
profile, and drafts tailored CVs and cover letters.

> Independent personal project. Not affiliated with, endorsed by, or maintained by Anthropic.
> Anthropic and Claude Code are referenced only to describe the toolchain this workflow uses.

---

## Job sources

| Source | Mechanism | Notes |
|---|---|---|
| **arbeitsagentur** | Official federal API | **Primary source.** Germany's largest job database. Real server-side date filtering, full plain-text descriptions, and immune to markup changes |
| **arbeitnow** | Public JSON API | Germany-focused tech and remote roles |
| **freehire** | Public JSON API | ~50 ATS platforms, faceted by skill/seniority/category |
| **stepstone** | HTML (SSR) | `search` works; `detail` is blocked upstream at the connection level |
| **xing** | HTML → schema.org JSON-LD | ⚠️ Personal use only |
| **linkedin** | HTML | ⚠️ Personal use only |
| **Indeed** | MCP connector (`country_code: "DE"`) | Never scraped directly |
| **Google** | `WebSearch` + `site:` queries | Fallback discovery; no Google Jobs scraper exists |

The three API-backed sources are the automation backbone — safe to poll daily. The
HTML-scraped ones are opt-in per search profile and kept low-volume.

---

## Setup

```bash
bun --version          # required by the portal CLIs
python3 --version      # required by the pipeline tools
```

Then run `/setup` in Claude Code to fill in your candidate profile. Until you do,
`CLAUDE.md` is all `[PLACEHOLDER]` tokens and fit scoring has nothing to score against.

---

## Daily workflow

| Command | What it does |
|---|---|
| `/scrape` | Search every enabled portal, deduplicate, present new matches with a fit signal |
| `/scrape health` | Probe every portal without searching — catches scrapers that have silently rotted |
| `/rank` | Batch-score new postings into a ranked shortlist |
| `/apply <n>` | Full evaluation → tailored CV + cover letter → compile → verify |
| `/outcome` | Record what happened to an application |
| `/upskill` | Compare tracked postings against your profile to find skill gaps |
| `/html-report` | Self-contained HTML dashboard of the whole pipeline |

---

## Headless pipeline

The deterministic half of `/scrape` runs without a model or an API key, which is what
a cron job can use:

```bash
# Configure once
$EDITOR job_scraper/search-profiles.json

# See what would run, fetch nothing
python3 tools/run_scrape.py --dry-run

# Real run: every enabled profile across every enabled portal
python3 tools/run_scrape.py --out job_scraper/pools/$(date +%F).json --update-seen
```

`search-profiles.json` holds the searches. The key thing it encodes: **the same logical
search is spelled differently on every portal** — LinkedIn needs `"Berlin, Germany"` where
StepStone needs `"Berlin"`, and freehire has no location flag at all (it takes `--city`).
That lives in `portal_overrides`, not in a shell script.

Deduplication is a separate tool you can run standalone:

```bash
python3 tools/dedup_jobs.py merge arbeitsagentur-search=a.json xing-search=b.json
python3 tools/dedup_jobs.py key --company "Bertrandt AG" --title "Data Engineer (m/w/d)"
```

---

## Repo structure

```
.agents/skills/<portal>-search/   portal CLIs (search + detail, zero runtime deps)
.claude/skills/                   job-scraper, job-application-assistant, upskill
.claude/commands/                 /rank, /apply, /outcome, /html-report, …
tools/run_scrape.py               headless collector: profiles → portals → pool
tools/dedup_jobs.py               cross-portal deduplication
job_scraper/search-profiles.json  the searches cron runs
job_scraper/seen_jobs.json        dedup state (gitignored)
cv/ cover_letters/                LaTeX templates
tests/                            Python tool tests
```

---

## Design notes

**Two layers.** Anything mechanical and repeatable is code that can be unit-tested;
anything requiring judgement stays with the model. Deduplication started as prose in a
skill file and got promoted to `tools/dedup_jobs.py` once pressure testing proved it was
a deterministic rule.

**Deduplication is normalized-exact, never fuzzy.** Measured across two hand-labelled live
pools, every genuine cross-portal duplicate scored a post-normalization similarity of
exactly 1.0000, while the highest pair that must *not* merge scored 0.9176. Fuzzy matching
adds no recall and only risks collapsing a senior role into a mid-level one — and an
over-merge permanently hides a real job, which is worse than showing a duplicate.

**Portals fail loudly and in isolation.** Each is a self-contained skill behind the same
contract, with an `enabled:` toggle. One broken portal never takes down a run, and the
health check exists because a rotted scraper otherwise exits 0 with zero results.

**No `process.exit()` in a portal CLI.** When stdout is a pipe, writes are asynchronous and
exiting immediately truncates output at the 64KB pipe buffer — invisible interactively,
fatal under automation. `tests/test_portal_cli_contract.py` enforces this.

**Access rules are surfaced, not bypassed.** Portals that disallow automated search in
robots.txt carry a personal-use warning. StepStone's `detail` endpoint blocks at the
connection level and is documented as unverified rather than worked around.

---

## Credits

Built on the [ai-job-search](https://github.com/MadsLorentzen/ai-job-search) framework by
Mads Lorentzen (MIT). This repo adapts it to the German market and adds the headless
pipeline. See `LICENSE`.
