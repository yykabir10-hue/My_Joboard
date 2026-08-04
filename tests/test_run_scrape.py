"""Tests for tools/run_scrape.py.

The most important test here is PortalFlagDrift: run_scrape.py hardcodes each
portal's flag names, which duplicates what the portal's own SKILL.md documents.
That duplication is deliberate (explicit and reviewable beats parsing markdown at
runtime) but it can drift. These tests fail the suite when it does, rather than
letting a 6am cron job discover it.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import run_scrape  # noqa: E402


class PortalFlagDrift(unittest.TestCase):
    def test_every_mapped_portal_exists(self):
        for portal in run_scrape.PORTAL_FLAGS:
            with self.subTest(portal=portal):
                self.assertTrue(run_scrape.cli_path(portal).is_file(),
                                f"{portal} has a flag mapping but no cli.ts")

    def test_every_mapped_flag_is_documented(self):
        for portal, flags in run_scrape.PORTAL_FLAGS.items():
            skill = REPO_ROOT / ".agents" / "skills" / portal / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            for field, flag in flags.items():
                if flag is None:
                    continue
                with self.subTest(portal=portal, field=field):
                    self.assertIn(flag, text,
                                  f"{portal} SKILL.md no longer documents {flag}")

    def test_location_required_portals_say_so(self):
        for portal in run_scrape.LOCATION_REQUIRED:
            text = (REPO_ROOT / ".agents" / "skills" / portal / "SKILL.md").read_text("utf-8")
            self.assertIn("required", text.lower())


class ResolvePortals(unittest.TestCase):
    defaults = {"portals": ["a", "b"]}

    def test_defaults_when_unspecified(self):
        self.assertEqual(run_scrape.resolve_portals(self.defaults, {}), ["a", "b"])

    def test_additive(self):
        self.assertEqual(
            run_scrape.resolve_portals(self.defaults, {"portals": ["+c"]}), ["a", "b", "c"])

    def test_subtractive(self):
        self.assertEqual(
            run_scrape.resolve_portals(self.defaults, {"portals": ["-a"]}), ["b"])

    def test_mixed(self):
        self.assertEqual(
            run_scrape.resolve_portals(self.defaults, {"portals": ["-a", "+c"]}), ["b", "c"])

    def test_bare_list_replaces(self):
        self.assertEqual(
            run_scrape.resolve_portals(self.defaults, {"portals": ["z"]}), ["z"])

    def test_addition_is_idempotent(self):
        self.assertEqual(
            run_scrape.resolve_portals(self.defaults, {"portals": ["+a"]}), ["a", "b"])


class BuildCommand(unittest.TestCase):
    defaults = {"jobage": 3, "limit": 25}

    def test_basic_flags(self):
        command = run_scrape.build_command(
            "stepstone-search",
            {"id": "p", "query": "Data Engineer", "location": "Berlin"},
            self.defaults)
        self.assertEqual(command[:2], ["bun", "run"])
        self.assertIn("search", command)
        for pair in (["--query", "Data Engineer"], ["--location", "Berlin"],
                     ["--jobage", "3"], ["--limit", "25"], ["--format", "json"]):
            with self.subTest(pair=pair):
                index = command.index(pair[0])
                self.assertEqual(command[index + 1], pair[1])

    def test_freehire_location_becomes_city(self):
        command = run_scrape.build_command(
            "freehire-search", {"id": "p", "query": "x", "location": "Berlin"}, self.defaults)
        self.assertIn("--city", command)
        self.assertNotIn("--location", command)

    def test_override_beats_profile(self):
        command = run_scrape.build_command(
            "linkedin-search",
            {"id": "p", "query": "x", "location": "Berlin",
             "portal_overrides": {"linkedin-search": {"location": "Berlin, Germany"}}},
            self.defaults)
        self.assertEqual(command[command.index("--location") + 1], "Berlin, Germany")

    def test_unknown_override_keys_pass_through(self):
        command = run_scrape.build_command(
            "freehire-search",
            {"id": "p", "query": "x",
             "portal_overrides": {"freehire-search": {"country": "DE", "category": "ml_ai"}}},
            self.defaults)
        self.assertEqual(command[command.index("--country") + 1], "DE")
        self.assertEqual(command[command.index("--category") + 1], "ml_ai")

    def test_override_colliding_with_a_mapped_flag_is_not_emitted_twice(self):
        # freehire's location flag IS --city, so a profile location plus a
        # {"city": ...} override used to emit --city twice.
        command = run_scrape.build_command(
            "freehire-search",
            {"id": "p", "query": "x", "location": "München",
             "portal_overrides": {"freehire-search": {"city": "Munich"}}},
            self.defaults)
        self.assertEqual(command.count("--city"), 1)
        self.assertEqual(command[command.index("--city") + 1], "Munich")

    def test_false_override_suppresses_a_flag(self):
        command = run_scrape.build_command(
            "stepstone-search",
            {"id": "p", "query": "x",
             "portal_overrides": {"stepstone-search": {"some-flag": False}}},
            self.defaults)
        self.assertNotIn("--some-flag", command)

    def test_boolean_override_becomes_a_bare_flag(self):
        command = run_scrape.build_command(
            "arbeitsagentur-search",
            {"id": "p", "query": "x",
             "portal_overrides": {"arbeitsagentur-search": {"all-offer-types": True}}},
            self.defaults)
        self.assertIn("--all-offer-types", command)
        self.assertNotIn("True", command)

    def test_omitted_fields_emit_no_flag(self):
        command = run_scrape.build_command(
            "stepstone-search", {"id": "p", "query": "x"}, {})
        self.assertNotIn("--location", command)
        self.assertNotIn("--jobage", command)

    def test_linkedin_without_location_is_a_config_error(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.build_command("linkedin-search", {"id": "p", "query": "x"}, self.defaults)

    def test_unmapped_portal_is_a_config_error(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.build_command("nope-search", {"id": "p", "query": "x"}, self.defaults)


class ExcludeTitles(unittest.TestCase):
    def test_plain_match(self):
        self.assertTrue(run_scrape.excluded("Werkstudent Data Engineer", ["werkstudent"]))

    def test_case_and_umlaut_insensitive(self):
        self.assertTrue(run_scrape.excluded("PRAKTIKUM Softwareentwicklung", ["praktikum"]))
        self.assertTrue(run_scrape.excluded("Duales Studium Informatik", ["duales studium"]))

    def test_survives_gender_markers(self):
        self.assertTrue(
            run_scrape.excluded("Werkstudent (m/w/d) Data Engineer", ["werkstudent"]))

    def test_real_job_is_kept(self):
        self.assertFalse(run_scrape.excluded("Senior Data Engineer (m/w/d)", ["werkstudent"]))

    def test_no_terms_excludes_nothing(self):
        self.assertFalse(run_scrape.excluded("Werkstudent", []))
        self.assertFalse(run_scrape.excluded("Werkstudent", None))

    def test_missing_title_is_safe(self):
        self.assertFalse(run_scrape.excluded(None, ["werkstudent"]))


class PortalEnabled(unittest.TestCase):
    def test_reads_the_frontmatter_toggle(self):
        self.assertTrue(run_scrape.portal_enabled("arbeitsagentur-search"))
        # Danish demo portals are disabled in this German-market fork.
        self.assertFalse(run_scrape.portal_enabled("jobindex-search"))

    def test_unknown_portal_is_not_enabled(self):
        self.assertFalse(run_scrape.portal_enabled("does-not-exist"))


class LoadConfig(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def write(self, payload):
        path = self.dir / "profiles.json"
        path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload,
                        encoding="utf-8")
        return path

    def test_missing_file(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.load_config(self.dir / "nope.json")

    def test_invalid_json(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.load_config(self.write("{not json"))

    def test_missing_profiles_array(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.load_config(self.write({"version": 1}))

    def test_duplicate_ids(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.load_config(self.write({"profiles": [
                {"id": "a", "query": "x"}, {"id": "a", "query": "y"}]}))

    def test_profile_without_id(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.load_config(self.write({"profiles": [{"query": "x"}]}))

    def test_profile_without_query_or_location(self):
        with self.assertRaises(run_scrape.ConfigError):
            run_scrape.load_config(self.write({"profiles": [{"id": "a"}]}))

    def test_shipped_config_is_valid(self):
        config = run_scrape.load_config(run_scrape.DEFAULT_CONFIG)
        self.assertTrue(config["profiles"])
        for profile in config["profiles"]:
            for portal in run_scrape.resolve_portals(config["defaults"], profile):
                with self.subTest(profile=profile["id"], portal=portal):
                    run_scrape.build_command(portal, profile, config["defaults"])


class Run(unittest.TestCase):
    config = {
        "defaults": {"jobage": 3, "limit": 5, "portals": ["arbeitsagentur-search"]},
        "profiles": [
            {"id": "on", "query": "Data Engineer", "location": "Berlin",
             "exclude_titles": ["werkstudent"]},
            {"id": "off", "enabled": False, "query": "x", "location": "y"},
        ],
    }

    def test_dry_run_fetches_nothing(self):
        with mock.patch.object(run_scrape, "run_portal") as runner:
            records, report = run_scrape.run(self.config, dry_run=True)
        runner.assert_not_called()
        self.assertEqual(records, [])
        self.assertEqual([e["status"] for e in report if e["profile"] == "on"], ["dry-run"])

    def test_disabled_profile_is_skipped_but_reported(self):
        _, report = run_scrape.run(self.config, dry_run=True)
        off = [e for e in report if e["profile"] == "off"]
        self.assertEqual([e["status"] for e in off], ["disabled"])

    def test_named_profile_overrides_its_disabled_flag(self):
        _, report = run_scrape.run(self.config, only="off", dry_run=True)
        self.assertEqual([e["status"] for e in report], ["dry-run"])

    def test_exclude_titles_applied_and_profile_tagged(self):
        payload = {"results": [
            {"title": "Werkstudent Data Engineer", "company": "A", "url": "1"},
            {"title": "Senior Data Engineer", "company": "B", "url": "2"},
        ]}
        with mock.patch.object(run_scrape, "run_portal", return_value=(payload, None)):
            records, report = run_scrape.run(self.config)
        self.assertEqual([r["title"] for r in records], ["Senior Data Engineer"])
        self.assertEqual(records[0]["profile"], "on")
        entry = [e for e in report if e["profile"] == "on"][0]
        self.assertEqual((entry["returned"], entry["kept"]), (2, 1))

    def test_a_failing_portal_does_not_abort_the_run(self):
        with mock.patch.object(run_scrape, "run_portal", return_value=(None, "boom")):
            records, report = run_scrape.run(self.config)
        self.assertEqual(records, [])
        entry = [e for e in report if e["profile"] == "on"][0]
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["detail"], "boom")


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "run_scrape.py"), *args],
            capture_output=True, text=True)

    def test_init_writes_a_usable_config(self):
        target = self.dir / "profiles.json"
        result = self.run_cli("--init", "--config", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(run_scrape.load_config(target)["profiles"])

    def test_init_refuses_to_clobber(self):
        target = self.dir / "profiles.json"
        self.run_cli("--init", "--config", str(target))
        result = self.run_cli("--init", "--config", str(target))
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stderr)

    def test_missing_config_errors_cleanly(self):
        result = self.run_cli("--config", str(self.dir / "nope.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no config at", result.stderr)

    def test_dry_run_prints_commands(self):
        result = self.run_cli("--dry-run", "--profile", "data-eng-berlin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bun run", result.stdout)
        self.assertIn("--query", result.stdout)

    def test_dry_run_over_the_shipped_config_survives_disabled_profiles(self):
        # A disabled-profile report entry carries no portal; the printer used
        # to KeyError on it, taking down the whole run.
        result = self.run_cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[disabled]", result.stdout)


if __name__ == "__main__":
    unittest.main()
