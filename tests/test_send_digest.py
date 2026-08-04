"""Tests for tools/send_digest.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import send_digest  # noqa: E402

POOL = {
    "meta": {"date": "2026-08-04", "input_records": 10, "unique_jobs": 9,
             "duplicates_collapsed": 1, "redundancy_pct": 10.0, "new": 2},
    "portals": [
        {"profile": "data-eng-berlin", "portal": "xing-search", "status": "ok"},
        {"profile": "data-eng-berlin", "portal": "freehire-search",
         "status": "failed", "detail": "timed out after 90s"},
    ],
    "new": [
        {"title": "Data Engineer (m/w/d)", "company": "Bertrandt AG", "location": "Berlin",
         "portal": "arbeitsagentur-search", "url": "https://example.com/1",
         "profile": "data-eng-berlin",
         "also_on": [{"portal": "xing-search", "url": "https://example.com/2"}]},
        {"title": "Softwareentwickler", "company": "ACME GmbH", "location": "München",
         "portal": "stepstone-search", "url": "https://example.com/3",
         "profile": "softwareentwickler-muenchen"},
    ],
}


class ParseEnvFile(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def write(self, text):
        path = self.dir / ".env"
        path.write_text(text, encoding="utf-8")
        return path

    def test_basic_pairs(self):
        path = self.write("A=1\nB=two\n")
        self.assertEqual(send_digest.parse_env_file(path), {"A": "1", "B": "two"})

    def test_comments_and_blanks_ignored(self):
        path = self.write("# note\n\nA=1\n")
        self.assertEqual(send_digest.parse_env_file(path), {"A": "1"})

    def test_quotes_stripped(self):
        path = self.write("A='one'\nB=\"two\"\n")
        self.assertEqual(send_digest.parse_env_file(path), {"A": "one", "B": "two"})

    def test_value_containing_equals_is_preserved(self):
        # App passwords and tokens can contain '='.
        path = self.write("A=ab=cd=\n")
        self.assertEqual(send_digest.parse_env_file(path)["A"], "ab=cd=")


class LoadConfig(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.env_file = self.dir / ".env"
        self.env_file.write_text(
            "JOBSEARCH_SMTP_USER=file@example.com\nJOBSEARCH_SMTP_PASSWORD=filepw\n",
            encoding="utf-8")
        self.env_file.chmod(0o600)

    def test_defaults_applied(self):
        config = send_digest.load_config(env={}, env_file=None)
        self.assertEqual(config["host"], "smtp.gmail.com")
        self.assertEqual(config["port"], 587)

    def test_env_file_is_read(self):
        config = send_digest.load_config(env={}, env_file=self.env_file)
        self.assertEqual(config["user"], "file@example.com")

    def test_environment_overrides_the_file(self):
        # So a cron entry can point at a different account without editing .env.
        config = send_digest.load_config(
            env={"JOBSEARCH_SMTP_USER": "env@example.com"}, env_file=self.env_file)
        self.assertEqual(config["user"], "env@example.com")

    def test_recipient_defaults_to_sender(self):
        config = send_digest.load_config(env={}, env_file=self.env_file)
        self.assertEqual(config["to"], "file@example.com")
        self.assertEqual(config["sender"], "file@example.com")

    def test_invalid_port_is_an_error(self):
        with self.assertRaises(send_digest.DigestError):
            send_digest.load_config(env={"JOBSEARCH_SMTP_PORT": "abc"}, env_file=None)

    def test_world_readable_env_file_warns(self):
        self.env_file.chmod(0o644)
        warnings = []
        send_digest.load_config(env={}, env_file=self.env_file, warn=warnings.append)
        self.assertTrue(any("chmod 600" in w for w in warnings))

    def test_secure_env_file_does_not_warn(self):
        warnings = []
        send_digest.load_config(env={}, env_file=self.env_file, warn=warnings.append)
        self.assertEqual(warnings, [])

    def test_missing_credentials_are_named(self):
        with self.assertRaises(send_digest.DigestError) as ctx:
            send_digest.require_credentials(send_digest.load_config(env={}, env_file=None))
        self.assertIn("JOBSEARCH_SMTP_USER", str(ctx.exception))


class RenderHtml(unittest.TestCase):
    def test_contains_jobs_and_counts(self):
        out = send_digest.render_html(POOL)
        self.assertIn("Data Engineer (m/w/d)", out)
        self.assertIn("Bertrandt AG", out)
        self.assertIn("https://example.com/1", out)
        self.assertIn("2 new", out)

    def test_groups_by_profile(self):
        out = send_digest.render_html(POOL)
        self.assertIn("data-eng-berlin", out)
        self.assertIn("softwareentwickler-muenchen", out)

    def test_also_on_is_surfaced(self):
        self.assertIn("also on xing-search", send_digest.render_html(POOL))

    def test_failed_portal_is_reported(self):
        out = send_digest.render_html(POOL)
        self.assertIn("Portal problems", out)
        self.assertIn("timed out after 90s", out)

    def test_healthy_portals_add_no_noise(self):
        pool = dict(POOL, portals=[{"profile": "p", "portal": "xing-search", "status": "ok"}])
        self.assertNotIn("Portal problems", send_digest.render_html(pool))

    def test_untrusted_text_is_escaped(self):
        # Titles and company names come from scraped pages - never trusted.
        pool = {"meta": {"date": "2026-08-04", "new": 1},
                "new": [{"title": "<script>alert(1)</script>", "company": "A & B",
                         "location": "X", "portal": "p", "url": "https://e/1"}]}
        out = send_digest.render_html(pool)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("A &amp; B", out)

    def test_malicious_url_is_attribute_escaped(self):
        pool = {"meta": {"date": "d", "new": 1},
                "new": [{"title": "T", "company": "C", "location": "L", "portal": "p",
                         "url": 'https://e/1" onmouseover="alert(1)'}]}
        self.assertNotIn('onmouseover="alert(1)"', send_digest.render_html(pool))

    def test_empty_pool_renders(self):
        out = send_digest.render_html({"meta": {"date": "2026-08-04", "new": 0}, "new": []})
        self.assertIn("No new postings today.", out)

    def test_missing_fields_do_not_crash(self):
        out = send_digest.render_html({"meta": {}, "new": [{}]})
        self.assertIn("(untitled)", out)


class RenderText(unittest.TestCase):
    def test_plain_text_alternative(self):
        out = send_digest.render_text(POOL)
        self.assertIn("Data Engineer (m/w/d)", out)
        self.assertIn("https://example.com/1", out)
        self.assertNotIn("<td", out)

    def test_failed_portal_in_text(self):
        self.assertIn("Portal problems:", send_digest.render_text(POOL))


class BuildMessage(unittest.TestCase):
    config = {"user": "me@example.com", "password": "pw", "to": "me@example.com",
              "sender": "me@example.com", "host": "h", "port": 587}

    def test_subject_and_headers(self):
        message = send_digest.build_message(POOL, self.config)
        self.assertEqual(message["Subject"], "Job digest 2026-08-04 — 2 new")
        self.assertEqual(message["To"], "me@example.com")

    def test_multipart_alternative(self):
        message = send_digest.build_message(POOL, self.config)
        types = {part.get_content_type() for part in message.walk()}
        self.assertIn("text/plain", types)
        self.assertIn("text/html", types)


class Send(unittest.TestCase):
    config = {"user": "me@example.com", "password": "pw", "to": "me@example.com",
              "sender": "me@example.com", "host": "smtp.example.com", "port": 587}

    def test_starttls_path(self):
        with mock.patch("smtplib.SMTP") as server:
            send_digest.send(send_digest.build_message(POOL, self.config), self.config)
        server.return_value.__enter__.return_value.starttls.assert_called_once()

    def test_implicit_tls_on_465(self):
        config = dict(self.config, port=465)
        with mock.patch("smtplib.SMTP_SSL") as server:
            send_digest.send(send_digest.build_message(POOL, config), config)
        server.return_value.__enter__.return_value.login.assert_called_once()

    def test_auth_failure_message_never_leaks_the_password(self):
        import smtplib
        error = smtplib.SMTPAuthenticationError(535, b"denied")
        with mock.patch("smtplib.SMTP") as server:
            server.return_value.__enter__.return_value.login.side_effect = error
            with self.assertRaises(send_digest.DigestError) as ctx:
                send_digest.send(send_digest.build_message(POOL, self.config), self.config)
        message = str(ctx.exception)
        self.assertNotIn("pw", message.split("app password")[0].replace("password", ""))
        self.assertIn("app password", message)


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.pool = self.dir / "pool.json"
        self.pool.write_text(json.dumps(POOL), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "send_digest.py"), *args],
            capture_output=True, text=True)

    def test_html_out_needs_no_credentials(self):
        out = self.dir / "digest.html"
        result = self.run_cli(str(self.pool), "--html-out", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Bertrandt AG", out.read_text(encoding="utf-8"))
        self.assertIn("nothing sent", result.stdout)

    def test_missing_pool_errors_cleanly(self):
        result = self.run_cli(str(self.dir / "nope.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no pool file", result.stderr)

    def test_invalid_json_errors_cleanly(self):
        bad = self.dir / "bad.json"
        bad.write_text("{nope", encoding="utf-8")
        result = self.run_cli(str(bad))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
