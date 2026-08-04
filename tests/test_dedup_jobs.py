"""Tests for tools/dedup_jobs.py.

The must-merge and must-not-merge pairs below are not invented: each one was
observed live and hand-labelled during the two dedup pressure tests
("Data Engineer"/Berlin, 96 records; "Softwareentwickler"/Munchen, 86 records)
and is recorded in .claude/skills/job-scraper/SKILL.md Step 2. They are the
regression suite for the normalization rule - if a future edit to normalize()
breaks one of these, it breaks a case that really happens.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dedup_jobs  # noqa: E402


class NormalizeTitle(unittest.TestCase):
    def test_strips_xing_soft_hyphens(self):
        # Xing hyphenates typographically; this renders as "Data Engineer" but
        # never string-matches it.
        self.assertEqual(
            dedup_jobs.normalize_title("Da­ta En­gi­neer"),
            dedup_jobs.normalize_title("Data Engineer"),
        )

    def test_strips_zero_width_and_bom(self):
        self.assertEqual(
            dedup_jobs.normalize_title("Data​ Eng﻿ineer"), "data engineer"
        )

    def test_nbsp_becomes_a_plain_space(self):
        self.assertEqual(dedup_jobs.normalize_title("Data Engineer"), "data engineer")

    def test_transliterates_german(self):
        self.assertEqual(
            dedup_jobs.normalize_title("Softwareentwickler für Großsysteme"),
            "softwareentwickler fuer grosssysteme",
        )

    def test_slashed_gender_markers(self):
        base = dedup_jobs.normalize_title("Data Engineer")
        for marker in ["(m/w/d)", "(w/m/d)", "(m/f/d)", "(d/m/w)", "(w/d/m)",
                       "(f/m/x)", "(m/w/i)", "m/w/d"]:
            with self.subTest(marker=marker):
                self.assertEqual(dedup_jobs.normalize_title(f"Data Engineer {marker}"), base)

    def test_slashless_gender_markers(self):
        # Indeed emits these with the separators stripped out.
        base = dedup_jobs.normalize_title("Data Engineer")
        for marker in ["(mwd)", "(wmd)", "(gn)", "(all genders)"]:
            with self.subTest(marker=marker):
                self.assertEqual(dedup_jobs.normalize_title(f"Data Engineer {marker}"), base)

    def test_german_inclusive_suffix(self):
        expected = dedup_jobs.normalize_title("Entwickler")
        for form in ["Entwickler:in", "Entwickler*in", "Entwickler:innen", "Entwickler*innen"]:
            with self.subTest(form=form):
                self.assertEqual(dedup_jobs.normalize_title(form), expected)

    def test_bare_star_marker(self):
        self.assertEqual(
            dedup_jobs.normalize_title("Data Engineer*"),
            dedup_jobs.normalize_title("Data Engineer"),
        )

    def test_seniority_is_never_erased(self):
        # The highest-scoring must-NOT-merge pair from the pools (0.9176 fuzzy).
        # Merging these hides a real job, which is worse than a visible duplicate.
        self.assertNotEqual(
            dedup_jobs.normalize_title("Data Engineer* / Machine Learning Engineer*"),
            dedup_jobs.normalize_title("Senior Data Engineer* / Machine Learning Engineer*"),
        )

    def test_compound_hyphenation_stays_unmerged(self):
        # Documented residual risk: in both pools every such pair was a genuinely
        # different job, so these deliberately do not merge.
        self.assertNotEqual(
            dedup_jobs.normalize_title("Softwareentwickler"),
            dedup_jobs.normalize_title("Software-Entwickler"),
        )


class NormalizeCompany(unittest.TestCase):
    def test_case_only_difference(self):
        # bayoonet on two portals.
        self.assertEqual(
            dedup_jobs.normalize_company("bayoonet AG"),
            dedup_jobs.normalize_company("BAYOONET AG"),
        )

    def test_legal_suffix_dropped(self):
        # "Bertrandt AG" on StepStone vs "Bertrandt" on Indeed.
        self.assertEqual(
            dedup_jobs.normalize_company("Bertrandt AG"),
            dedup_jobs.normalize_company("Bertrandt"),
        )

    def test_group_suffix_and_hyphenation(self):
        self.assertEqual(
            dedup_jobs.normalize_company("Bundesdruckerei Gruppe GmbH"),
            dedup_jobs.normalize_company("Bundesdruckerei-Gruppe"),
        )

    def test_compound_legal_form(self):
        self.assertEqual(
            dedup_jobs.normalize_company("Muster GmbH & Co. KG"),
            dedup_jobs.normalize_company("Muster"),
        )

    def test_legal_form_inside_a_word_is_kept(self):
        # "Agentur" must not lose an "ag"; token boundaries are enforced.
        self.assertEqual(dedup_jobs.normalize_company("Agentur Seven"), "agentur seven")

    def test_distinct_employers_stay_distinct(self):
        self.assertNotEqual(
            dedup_jobs.normalize_company("Siemens AG"),
            dedup_jobs.normalize_company("Siemens Energy AG"),
        )


class DedupKey(unittest.TestCase):
    def test_dash_variant_pair(self):
        # "Securiton GmbH - IPS..." (StepStone) vs "... – ..." (Xing), same job.
        self.assertEqual(
            dedup_jobs.dedup_key("Securiton GmbH - IPS", "Servicetechniker (m/w/d)"),
            dedup_jobs.dedup_key("Securiton GmbH – IPS", "Servicetechniker (w/m/d)"),
        )

    def test_key_shape(self):
        self.assertEqual(
            dedup_jobs.dedup_key("Bertrandt AG", "Data Engineer (m/w/d)"),
            "bertrandt|data engineer",
        )

    def test_missing_fields_do_not_crash(self):
        self.assertEqual(dedup_jobs.dedup_key(None, None), "|")


class MergePool(unittest.TestCase):
    def test_collapses_cross_portal_duplicate(self):
        records = [
            {"portal": "stepstone-search", "company": "Bertrandt AG",
             "title": "Data Engineer (m/w/d)", "url": "https://stepstone.de/1"},
            {"portal": "arbeitsagentur-search", "company": "Bertrandt",
             "title": "Data Engineer*", "url": "https://arbeitsagentur.de/2"},
        ]
        unique, stats = dedup_jobs.merge_pool(records)
        self.assertEqual(stats["unique_jobs"], 1)
        self.assertEqual(stats["duplicates_collapsed"], 1)
        # arbeitsagentur outranks stepstone: full descriptions, working detail.
        self.assertEqual(unique[0]["portal"], "arbeitsagentur-search")
        self.assertEqual(unique[0]["also_on"],
                         [{"portal": "stepstone-search", "url": "https://stepstone.de/1"}])

    def test_same_portal_identical_row_twice(self):
        # Xing returned one job twice with an identical URL; StepStone returned
        # two KNDS postings twice each. Both pools showed this.
        row = {"portal": "xing-search", "company": "ACME GmbH",
               "title": "Data Engineer", "url": "https://xing.com/1"}
        unique, stats = dedup_jobs.merge_pool([row, dict(row)])
        self.assertEqual(stats["unique_jobs"], 1)
        self.assertNotIn("also_on", unique[0])

    def test_distinct_jobs_survive(self):
        records = [
            {"portal": "xing-search", "company": "ACME GmbH",
             "title": "Data Engineer* / Machine Learning Engineer*", "url": "a"},
            {"portal": "xing-search", "company": "ACME GmbH",
             "title": "Senior Data Engineer* / Machine Learning Engineer*", "url": "b"},
        ]
        unique, stats = dedup_jobs.merge_pool(records)
        self.assertEqual(stats["unique_jobs"], 2)
        self.assertEqual(stats["duplicates_collapsed"], 0)

    def test_redundancy_percentage(self):
        records = [
            {"portal": "xing-search", "company": "A GmbH", "title": "Dev", "url": "1"},
            {"portal": "stepstone-search", "company": "A", "title": "Dev (m/w/d)", "url": "2"},
            {"portal": "xing-search", "company": "B AG", "title": "Ops", "url": "3"},
            {"portal": "xing-search", "company": "C AG", "title": "QA", "url": "4"},
        ]
        _, stats = dedup_jobs.merge_pool(records)
        self.assertEqual(stats["redundancy_pct"], 25.0)

    def test_empty_pool(self):
        unique, stats = dedup_jobs.merge_pool([])
        self.assertEqual(unique, [])
        self.assertEqual(stats["redundancy_pct"], 0.0)


class ExtractRecords(unittest.TestCase):
    def test_portal_cli_envelope(self):
        payload = {"meta": {"count": 1}, "results": [{"title": "Dev"}]}
        records = dedup_jobs.extract_records(payload, "xing-search")
        self.assertEqual(records[0]["portal"], "xing-search")

    def test_bare_list_and_mcp_shape(self):
        self.assertEqual(len(dedup_jobs.extract_records([{"title": "a"}], "p")), 1)
        self.assertEqual(len(dedup_jobs.extract_records({"jobs": [{"title": "a"}]}, "p")), 1)

    def test_row_level_portal_tag_wins(self):
        payload = {"results": [{"title": "Dev", "portal": "indeed"}]}
        self.assertEqual(dedup_jobs.extract_records(payload, "xing-search")[0]["portal"], "indeed")

    def test_ignores_non_dict_rows(self):
        self.assertEqual(dedup_jobs.extract_records(["nope", {"title": "a"}], "p"),
                         [{"title": "a", "portal": "p"}])


class SeenStore(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.path = self.dir / "seen_jobs.json"

    def test_missing_file_is_an_empty_store(self):
        self.assertEqual(dedup_jobs.load_seen(self.path), {"seen": {}})

    def test_legacy_url_keyed_entry_is_recognised(self):
        self.path.write_text(json.dumps({"seen": {
            "https://stepstone.de/1": {"company": "Bertrandt AG", "title": "Data Engineer (m/w/d)"}
        }}), encoding="utf-8")
        keys = dedup_jobs.seen_keys(dedup_jobs.load_seen(self.path))
        self.assertIn("bertrandt|data engineer", keys)

    def test_update_preserves_rank_fields(self):
        # /rank writes these onto the same entries; re-running /scrape must not
        # wipe a ranking.
        store = {"seen": {"bertrandt|data engineer": {
            "title": "Data Engineer", "company": "Bertrandt", "rank_score": 87,
            "rank_verdict": "strong fit", "status": "ranked",
        }}}
        added = dedup_jobs.update_seen(store, [{
            "dedup_key": "bertrandt|data engineer", "company": "Bertrandt",
            "title": "Data Engineer", "url": "https://x/1",
            "also_on": [{"portal": "xing-search", "url": "https://xing.com/9"}],
        }])
        entry = store["seen"]["bertrandt|data engineer"]
        self.assertEqual(added, 0)
        self.assertEqual(entry["rank_score"], 87)
        self.assertEqual(entry["status"], "ranked")
        self.assertEqual(entry["also_on"][0]["portal"], "xing-search")

    def test_update_adds_new_entry_under_normalized_key(self):
        store = {"seen": {}}
        added = dedup_jobs.update_seen(
            store,
            [{"company": "Bertrandt AG", "title": "Data Engineer (m/w/d)",
              "url": "https://x/1", "portal": "stepstone-search"}],
            today="2026-08-04",
        )
        self.assertEqual(added, 1)
        entry = store["seen"]["bertrandt|data engineer"]
        self.assertEqual(entry["first_seen"], "2026-08-04")
        self.assertEqual(entry["portal"], "stepstone-search")

    def test_also_on_is_not_duplicated_across_runs(self):
        store = {"seen": {"a|b": {"also_on": [{"portal": "xing-search", "url": "u"}]}}}
        dedup_jobs.update_seen(store, [{"dedup_key": "a|b",
                                        "also_on": [{"portal": "xing-search", "url": "u"}]}])
        self.assertEqual(len(store["seen"]["a|b"]["also_on"]), 1)

    def test_malformed_store_is_rejected(self):
        self.path.write_text('{"seen": []}', encoding="utf-8")
        with self.assertRaises(ValueError):
            dedup_jobs.load_seen(self.path)


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "dedup_jobs.py"), *args],
            capture_output=True, text=True,
        )

    def write(self, name, payload):
        path = self.dir / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_merge_end_to_end(self):
        a = self.write("a.json", {"results": [
            {"company": "Bertrandt AG", "title": "Data Engineer (m/w/d)", "url": "https://s/1"}]})
        b = self.write("b.json", {"results": [
            {"company": "Bertrandt", "title": "Data Engineer*", "url": "https://a/2"},
            {"company": "Siemens AG", "title": "Softwareentwickler:in", "url": "https://a/3"}]})
        seen = self.dir / "seen.json"

        result = self.run_cli("merge", f"stepstone-search={a}", f"arbeitsagentur-search={b}",
                              "--seen", str(seen), "--update-seen", str(seen))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["meta"]["input_records"], 3)
        self.assertEqual(payload["meta"]["unique_jobs"], 2)
        self.assertEqual(payload["meta"]["new"], 2)

        # Second run against the now-populated store finds nothing new.
        again = self.run_cli("merge", f"stepstone-search={a}", f"arbeitsagentur-search={b}",
                             "--seen", str(seen))
        self.assertEqual(json.loads(again.stdout)["meta"]["new"], 0)

    def test_bare_path_infers_portal_from_stem(self):
        path = self.write("xing-search.json", {"results": [{"company": "A", "title": "Dev"}]})
        result = self.run_cli("merge", str(path), "--seen", str(self.dir / "none.json"))
        self.assertEqual(json.loads(result.stdout)["new"][0]["portal"], "xing-search")

    def test_key_subcommand(self):
        result = self.run_cli("key", "--company", "Bertrandt AG", "--title", "Data Engineer (m/w/d)")
        self.assertEqual(result.stdout.strip(), "bertrandt|data engineer")

    def test_missing_input_file_errors_cleanly(self):
        result = self.run_cli("merge", str(self.dir / "nope.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no such file", result.stderr)

    def test_invalid_json_errors_cleanly(self):
        path = self.dir / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        result = self.run_cli("merge", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid JSON", result.stderr)

    def test_table_format(self):
        path = self.write("p.json", {"results": [{"company": "A GmbH", "title": "Dev"}]})
        result = self.run_cli("merge", str(path), "--seen", str(self.dir / "none.json"),
                              "--format", "table")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 records -> 1 unique", result.stdout)


if __name__ == "__main__":
    unittest.main()
