#!/usr/bin/env python3
"""Load job_scraper/seen_jobs.json into a queryable SQLite database.

    python3 tools/pool_to_sqlite.py
    python3 tools/pool_to_sqlite.py --seen job_scraper/seen_jobs.json --db job_scraper/jobs.db

Why seen_jobs.json rather than the daily pool files: pools are one JSON file
per day, pruned after 30 days by daily_run.sh / the GitHub Actions workflow,
and each only holds that day's *new* jobs. seen_jobs.json is the one file that
already accumulates every job ever seen, with a first_seen date on each entry
- it is the actual "history across days" the sqlite database exists to make
queryable, not a substitute for it.

Idempotent: re-running does not duplicate rows. Each dedup_key upserts, so
this is safe to run after every scrape (a status/fit update from /rank shows
up on the next ingest) and safe to run twice on the same seen_jobs.json.

Stdlib only (sqlite3 is part of the standard library). Exit 0 on success, 1 on
a missing/invalid seen_jobs.json.

Example queries once built:
    sqlite3 job_scraper/jobs.db "SELECT company, title, first_seen FROM jobs \\
        WHERE first_seen >= date('now', '-7 days') ORDER BY first_seen DESC;"
    sqlite3 job_scraper/jobs.db "SELECT portal, COUNT(*) FROM jobs GROUP BY portal;"
    sqlite3 job_scraper/jobs.db "SELECT company, COUNT(*) AS n FROM jobs \\
        GROUP BY company ORDER BY n DESC LIMIT 10;"
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEEN = ROOT / "job_scraper" / "seen_jobs.json"
DEFAULT_DB = ROOT / "job_scraper" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    dedup_key   TEXT PRIMARY KEY,
    title       TEXT,
    company     TEXT,
    url         TEXT,
    portal      TEXT,
    first_seen  TEXT,
    status      TEXT,
    fit         TEXT,
    also_on     TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs (first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs (company);
"""

UPSERT = """
INSERT INTO jobs (dedup_key, title, company, url, portal, first_seen, status, fit, also_on)
VALUES (:dedup_key, :title, :company, :url, :portal, :first_seen, :status, :fit, :also_on)
ON CONFLICT(dedup_key) DO UPDATE SET
    title=excluded.title, company=excluded.company, url=excluded.url,
    portal=excluded.portal, first_seen=excluded.first_seen,
    status=excluded.status, fit=excluded.fit, also_on=excluded.also_on;
"""


def load_seen(path):
    if not path.is_file():
        raise ValueError(f"no seen store at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("seen"), dict):
        raise ValueError(f"{path}: expected an object with a 'seen' object")
    return data["seen"]


def ingest(seen, db_path):
    """Upsert every entry in `seen` into the jobs table. Returns row count."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        rows = []
        for dedup_key, entry in seen.items():
            fit = entry.get("fit")
            also_on = entry.get("also_on")
            rows.append({
                "dedup_key": dedup_key,
                "title": entry.get("title"),
                "company": entry.get("company"),
                "url": entry.get("url"),
                "portal": entry.get("portal"),
                "first_seen": entry.get("first_seen"),
                "status": entry.get("status"),
                "fit": json.dumps(fit, ensure_ascii=False) if fit is not None else None,
                "also_on": json.dumps(also_on, ensure_ascii=False) if also_on else None,
            })
        conn.executemany(UPSERT, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pool_to_sqlite.py",
        description="Load job_scraper/seen_jobs.json into a queryable SQLite database.",
    )
    parser.add_argument("--seen", default=str(DEFAULT_SEEN))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args(argv)

    try:
        seen = load_seen(Path(args.seen))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    count = ingest(seen, db_path)
    print(f"upserted {count} jobs -> {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
