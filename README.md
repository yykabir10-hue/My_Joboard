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
| **stepstone** | HTML (SSR) | Strong general coverage. `search` works; `detail` is blocked upstream at the connection level |
| **freehire** | Public JSON API | ~50 ATS platforms, faceted by skill/seniority/category |
| **xing** | HTML → schema.org JSON-LD | ⚠️ Personal use only — opted into core profiles only |
| **linkedin** | HTML | ⚠️ Personal use only — opted into core profiles only |
| **Indeed** | MCP connector (`country_code: "DE"`) | Never scraped directly |
| **Google** | `WebSearch` + `site:` queries | Fallback discovery; no Google Jobs scraper exists |
| **arbeitnow** | Public JSON API | **Installed but unused.** Probed with `Verfahrensingenieur`, `Process Engineer` and `Werkstudent Verfahrenstechnik` it returned 0 results every time — a tech/remote board that carries nothing for process engineering |

`arbeitsagentur`, `stepstone` and `freehire` are the daily backbone. The two
personal-use portals are opted in per profile rather than fired on every search,
to keep request volume low.

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
search is spelled differently on every portal** — LinkedIn requires a location string where the others treat it as optional,
and freehire has no location flag at all (it takes `--city`/`--country`).
That lives in `portal_overrides`, not in a shell script.

Deduplication is a separate tool you can run standalone:

```bash
python3 tools/dedup_jobs.py merge arbeitsagentur-search=a.json stepstone-search=b.json
python3 tools/dedup_jobs.py key --company "Sika Group" --title "Verfahrensingenieur (m/w/d)"
```

---

## Daily digest (cron)

`tools/daily_run.sh` scrapes, deduplicates against everything seen before, and
emails what's new. No model and no API key — just `bun`, `python3`, and SMTP.

**1. Credentials.** Gmail needs an *app password* (2FA must be on); a normal
account password is always rejected. Generate one at
<https://myaccount.google.com/apppasswords>.

```bash
cp .env.example .env
chmod 600 .env          # send_digest.py warns if others can read it
$EDITOR .env
```

`.env` is gitignored, and that rule is pinned in `tools/security_guards.py` so it
cannot be quietly removed later.

**2. Test without sending.**

```bash
./tools/daily_run.sh --dry-run      # scrapes, renders, sends nothing
```

Writes `job_scraper/logs/<date>.html` — open it to see exactly what the mail
looks like. Then send one for real:

```bash
python3 tools/send_digest.py job_scraper/pools/$(date +%F).json
```

**3. Schedule it.**

```bash
crontab -e
30 7 * * *  /home/<you>/ai-job-search/tools/daily_run.sh
```

The script sets `PATH` explicitly rather than sourcing `~/.bashrc` — cron runs
with a minimal environment, and a script that only works because of an
interactive shell's PATH is one that passes your test and fails at 07:30. It
also takes an `flock` so a slow run can never overlap the next one and race on
`seen_jobs.json`, and prunes logs and pools older than 30 days.

**On WSL:** cron only runs while WSL is running. This machine has `systemd=true`
in `/etc/wsl.conf` and `cron` active, so it works once WSL is up. If you want it
to survive a reboot without opening a terminal, add a Windows Task Scheduler
entry at logon running `wsl.exe -d Ubuntu -- true` to start the VM.

**What lands in your inbox:** new roles grouped by search profile, each linking
to the posting, with `also on <portal>` where several boards carried the same
job — plus a **Portal problems** block if any portal failed or timed out, since
a silently broken scraper is the failure mode this pipeline is most exposed to.

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
