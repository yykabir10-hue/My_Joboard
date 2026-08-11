"""Tests for tools/pool_to_sqlite.py."""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import pool_to_sqlite  # noqa: E402


class LoadSeen(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def write(self, payload):
        path = self.dir / "seen_jobs.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            pool_to_sqlite.load_seen(self.dir / "nope.json")

    def test_missing_seen_key(self):
        with self.assertRaises(ValueError):
            pool_to_sqlite.load_seen(self.write({"version": 1}))

    def test_reads_the_seen_object(self):
        seen = pool_to_sqlite.load_seen(self.write({"seen": {"a|b": {"title": "X"}}}))
        self.assertEqual(seen, {"a|b": {"title": "X"}})


class Ingest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.db_path = self.dir / "jobs.db"

    def query(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_ingests_every_entry(self):
        seen = {
            "fraunhofer|photonik": {
                "title": "Werkstudent*in Photonik", "company": "Fraunhofer HHI",
                "url": "https://example.com/1", "portal": "linkedin-search",
                "first_seen": "2026-08-08", "status": "seen", "fit": None,
            },
            "zeiss|optik": {
                "title": "Werkstudent Optik", "company": "ZEISS",
                "url": "https://example.com/2", "portal": "xing-search",
                "first_seen": "2026-08-09", "status": "seen", "fit": None,
            },
        }
        count = pool_to_sqlite.ingest(seen, self.db_path)
        self.assertEqual(count, 2)
        rows = self.query("SELECT dedup_key, title, company FROM jobs ORDER BY dedup_key")
        self.assertEqual(rows, [
            ("fraunhofer|photonik", "Werkstudent*in Photonik", "Fraunhofer HHI"),
            ("zeiss|optik", "Werkstudent Optik", "ZEISS"),
        ])

    def test_rerun_is_idempotent_not_duplicating_rows(self):
        seen = {"a|b": {"title": "X", "company": "Y", "url": "u",
                        "portal": "p", "first_seen": "2026-08-08",
                        "status": "seen", "fit": None}}
        pool_to_sqlite.ingest(seen, self.db_path)
        pool_to_sqlite.ingest(seen, self.db_path)
        rows = self.query("SELECT COUNT(*) FROM jobs")
        self.assertEqual(rows, [(1,)])

    def test_rerun_updates_changed_fields(self):
        # Simulates /rank writing a fit score onto an existing seen entry -
        # the next ingest must pick up the change, not freeze the first value.
        seen = {"a|b": {"title": "X", "company": "Y", "url": "u",
                        "portal": "p", "first_seen": "2026-08-08",
                        "status": "seen", "fit": None}}
        pool_to_sqlite.ingest(seen, self.db_path)
        seen["a|b"]["fit"] = {"score": 82, "verdict": "Strong Fit"}
        seen["a|b"]["status"] = "ranked"
        pool_to_sqlite.ingest(seen, self.db_path)
        rows = self.query("SELECT status, fit FROM jobs WHERE dedup_key = 'a|b'")
        self.assertEqual(rows[0][0], "ranked")
        self.assertEqual(json.loads(rows[0][1]), {"score": 82, "verdict": "Strong Fit"})

    def test_also_on_is_stored_as_json(self):
        seen = {"a|b": {"title": "X", "company": "Y", "url": "u",
                        "portal": "p", "first_seen": "2026-08-08", "status": "seen",
                        "fit": None, "also_on": [{"portal": "xing-search", "url": "u2"}]}}
        pool_to_sqlite.ingest(seen, self.db_path)
        rows = self.query("SELECT also_on FROM jobs WHERE dedup_key = 'a|b'")
        self.assertEqual(json.loads(rows[0][0]), [{"portal": "xing-search", "url": "u2"}])

    def test_empty_seen_creates_schema_without_error(self):
        count = pool_to_sqlite.ingest({}, self.db_path)
        self.assertEqual(count, 0)
        self.assertEqual(self.query("SELECT COUNT(*) FROM jobs"), [(0,)])


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def run_cli(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "pool_to_sqlite.py"), *args],
            capture_output=True, text=True)

    def test_missing_seen_file_errors_cleanly(self):
        result = self.run_cli("--seen", str(self.dir / "nope.json"),
                              "--db", str(self.dir / "jobs.db"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no seen store", result.stderr)

    def test_end_to_end(self):
        seen_path = self.dir / "seen_jobs.json"
        seen_path.write_text(json.dumps({"seen": {
            "a|b": {"title": "X", "company": "Y", "url": "u", "portal": "p",
                    "first_seen": "2026-08-08", "status": "seen", "fit": None},
        }}), encoding="utf-8")
        db_path = self.dir / "jobs.db"
        result = self.run_cli("--seen", str(seen_path), "--db", str(db_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("upserted 1 jobs", result.stdout)
        self.assertTrue(db_path.is_file())


if __name__ == "__main__":
    unittest.main()
