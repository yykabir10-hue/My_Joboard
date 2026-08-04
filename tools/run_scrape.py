#!/usr/bin/env python3
"""Run every enabled search profile across every enabled portal, headlessly.

    python3 tools/run_scrape.py --dry-run
    python3 tools/run_scrape.py --profile data-eng-berlin
    python3 tools/run_scrape.py --out job_scraper/pools/$(date +%F).json --update-seen

This is the deterministic half of `/scrape`: config in, deduplicated pool out.
It needs no model and no API key, so it is what a cron job actually runs. Fit
assessment, ranking, and CV work stay with the model - see
.claude/skills/job-scraper/SKILL.md.

Why a config file rather than flags: the same logical search is spelled
differently on every portal (LinkedIn needs "Berlin, Germany" where StepStone
needs "berlin"; freehire has no --location at all and takes --city). Those
per-portal spellings belong in data, not in a shell script that drifts.

Stdlib only. Exit 0 on success, 1 on a config or usage error.
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dedup_jobs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "job_scraper" / "search-profiles.json"
DEFAULT_SEEN = ROOT / "job_scraper" / "seen_jobs.json"

# How each portal spells the four logical search fields. Kept here rather than
# parsed out of SKILL.md so the mapping is explicit and reviewable - and pinned
# by tests/test_run_scrape.py, which fails if a flag named here stops appearing
# in that portal's SKILL.md.
#
# `location: None` means the portal takes no location flag at all; use
# `portal_overrides` for whatever it does support instead.
PORTAL_FLAGS = {
    "arbeitsagentur-search": {"query": "--query", "location": "--location",
                              "jobage": "--jobage", "limit": "--limit"},
    "arbeitnow-search":      {"query": "--query", "location": "--location",
                              "jobage": "--jobage", "limit": "--limit"},
    "stepstone-search":      {"query": "--query", "location": "--location",
                              "jobage": "--jobage", "limit": "--limit"},
    "xing-search":           {"query": "--query", "location": "--location",
                              "jobage": "--jobage", "limit": "--limit"},
    "linkedin-search":       {"query": "--query", "location": "--location",
                              "jobage": "--jobage", "limit": "--limit"},
    # freehire has no --location; its city facet is --city.
    "freehire-search":       {"query": "--query", "location": "--city",
                              "jobage": "--jobage", "limit": "--limit"},
}

# linkedin-search documents --location as required.
LOCATION_REQUIRED = {"linkedin-search"}


class ConfigError(Exception):
    """Raised when search-profiles.json cannot be used as written."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXAMPLE_CONFIG = {
    "version": 1,
    "defaults": {
        "jobage": 3,
        "limit": 25,
        "portals": ["arbeitsagentur-search", "arbeitnow-search", "freehire-search"],
    },
    "profiles": [
        {
            "id": "data-eng-berlin",
            "enabled": True,
            "query": "Data Engineer",
            "location": "Berlin",
            "portals": ["+stepstone-search", "+xing-search"],
            "portal_overrides": {
                "linkedin-search": {"location": "Berlin, Germany"},
                "freehire-search": {"country": "DE", "category": "ml_ai"},
                "arbeitsagentur-search": {"radius": 30},
            },
            "exclude_titles": ["werkstudent", "praktikum", "ausbildung", "duales studium"],
        }
    ],
}


def load_config(path):
    path = Path(path)
    if not path.is_file():
        raise ConfigError(
            f"no config at {path}. Create one with: "
            f"python3 tools/run_scrape.py --init"
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(config, dict) or not isinstance(config.get("profiles"), list):
        raise ConfigError(f"{path}: expected an object with a 'profiles' array")

    seen_ids = set()
    for profile in config["profiles"]:
        if not isinstance(profile, dict):
            raise ConfigError(f"{path}: every profile must be an object")
        pid = profile.get("id")
        if not pid:
            raise ConfigError(f"{path}: every profile needs an 'id'")
        if pid in seen_ids:
            raise ConfigError(f"{path}: duplicate profile id {pid!r}")
        seen_ids.add(pid)
        if not profile.get("query") and not profile.get("location"):
            raise ConfigError(f"{path}: profile {pid!r} needs a 'query' or a 'location'")
    return config


def resolve_portals(defaults, profile):
    """Apply a profile's `portals` list on top of the defaults.

    Entries prefixed `+` add to the defaults and `-` removes from them; a list
    with no prefixes replaces the defaults outright.
    """
    base = list(defaults.get("portals", []))
    requested = profile.get("portals")
    if not requested:
        return base

    if any(p.startswith(("+", "-")) for p in requested):
        result = list(base)
        for entry in requested:
            if entry.startswith("+"):
                name = entry[1:]
                if name not in result:
                    result.append(name)
            elif entry.startswith("-"):
                name = entry[1:]
                if name in result:
                    result.remove(name)
            elif entry not in result:
                result.append(entry)
        return result
    return list(requested)


def cli_path(portal):
    return ROOT / ".agents" / "skills" / portal / "cli" / "src" / "cli.ts"


def portal_enabled(portal):
    """Honor the `enabled:` frontmatter toggle, same as /scrape Step 1b."""
    skill = ROOT / ".agents" / "skills" / portal / "SKILL.md"
    if not skill.is_file():
        return False
    for line in skill.read_text(encoding="utf-8").splitlines():
        if line.startswith("enabled:"):
            return not line.split(":", 1)[1].strip().lower().startswith("false")
        if line.startswith("---") and line.strip() == "---":
            continue
    return True


def build_command(portal, profile, defaults):
    """Assemble one portal's `search` invocation for one profile."""
    flags = PORTAL_FLAGS.get(portal)
    if flags is None:
        raise ConfigError(
            f"portal {portal!r} has no flag mapping in PORTAL_FLAGS - add one "
            f"(and a SKILL.md-drift test case) before using it in a profile"
        )

    # Defaults first, then the profile's own - so a facet that every profile
    # needs (freehire's --country, linkedin's required location) is written once
    # in `defaults`, and a profile can still override any single key.
    overrides = dict((defaults.get("portal_overrides") or {}).get(portal, {}))
    overrides.update((profile.get("portal_overrides") or {}).get(portal, {}))
    values = {
        "query": overrides.pop("query", profile.get("query")),
        "location": overrides.pop("location", profile.get("location")),
        "jobage": overrides.pop("jobage", profile.get("jobage", defaults.get("jobage"))),
        "limit": overrides.pop("limit", profile.get("limit", defaults.get("limit"))),
    }

    if portal in LOCATION_REQUIRED and not values["location"]:
        raise ConfigError(
            f"profile {profile['id']!r}: {portal} requires a location - set one on "
            f"the profile or in portal_overrides"
        )

    # Built as flag -> value so a passthrough key can *replace* a mapped flag
    # rather than emit it twice. This is not hypothetical: freehire's location
    # flag is --city, so a profile location of "München" plus an override of
    # {"city": "Munich"} would otherwise produce --city twice.
    resolved = {}
    for field, flag in flags.items():
        value = values.get(field)
        if flag is None or value is None or value == "":
            continue
        resolved[flag] = value

    # Anything left in the override block is passed through verbatim, so a
    # portal-specific facet (freehire's --category, arbeitsagentur's --radius)
    # needs no change here. Later wins: an explicit override beats the mapping.
    for key, value in overrides.items():
        if value is None or value is False:
            continue
        resolved[key if key.startswith("-") else f"--{key}"] = value

    command = ["bun", "run", str(cli_path(portal)), "search"]
    for flag, value in resolved.items():
        if value is True:
            command.append(flag)
        else:
            command += [flag, str(value)]

    command += ["--format", "json"]
    return command


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_portal(command, timeout):
    """Run one portal CLI. Never raises - a dead portal must not kill the run."""
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, "bun not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return None, (detail[-1] if detail else f"exit {proc.returncode}")
    try:
        return json.loads(proc.stdout or "{}"), None
    except json.JSONDecodeError as exc:
        return None, f"unparseable output: {exc}"


def excluded(title, terms):
    """Drop obvious non-matches before any model spend.

    Compared on the normalized title so umlauts, punctuation, and gender
    markers cannot smuggle a "Werkstudent" posting past the filter.
    """
    if not terms:
        return False
    haystack = dedup_jobs.normalize_title(title or "")
    return any(dedup_jobs.normalize_title(term) in haystack for term in terms)


def run(config, only=None, dry_run=False, timeout=120):
    defaults = config.get("defaults", {})
    records, report = [], []

    if only is not None:
        known = [p.get("id") for p in config["profiles"]]
        if only not in known:
            # Silently scraping nothing because of a typo'd profile name is the
            # kind of failure a cron job hides for weeks.
            raise ConfigError(
                f"no profile with id {only!r}. Available: " + ", ".join(sorted(known))
            )

    for profile in config["profiles"]:
        if only and profile["id"] != only:
            continue
        if not only and not profile.get("enabled", True):
            report.append({"profile": profile["id"], "status": "disabled"})
            continue

        for portal in resolve_portals(defaults, profile):
            entry = {"profile": profile["id"], "portal": portal}

            if not cli_path(portal).is_file():
                entry.update(status="missing", detail="no cli.ts")
                report.append(entry)
                continue
            if not portal_enabled(portal):
                entry.update(status="disabled")
                report.append(entry)
                continue

            command = build_command(portal, profile, defaults)
            entry["command"] = " ".join(command)
            if dry_run:
                entry["status"] = "dry-run"
                report.append(entry)
                continue

            payload, error = run_portal(command, timeout)
            if error:
                entry.update(status="failed", detail=error)
                report.append(entry)
                continue

            found = dedup_jobs.extract_records(payload, portal)
            kept = [r for r in found
                    if not excluded(r.get("title"), profile.get("exclude_titles"))]
            for record in kept:
                record["profile"] = profile["id"]
            records.extend(kept)
            entry.update(status="ok", returned=len(found), kept=len(kept))
            report.append(entry)

    return records, report


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_scrape.py",
        description="Run every enabled search profile across every enabled portal.",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--profile", help="run only this profile id (ignores its enabled flag)")
    parser.add_argument("--seen", default=str(DEFAULT_SEEN))
    parser.add_argument("--update-seen", action="store_true",
                        help="write the pool back into the seen store")
    parser.add_argument("--out", help="write the pool JSON here (default: stdout)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the commands that would run, fetch nothing")
    parser.add_argument("--timeout", type=int, default=120, help="per-portal seconds")
    parser.add_argument("--init", action="store_true",
                        help="write an example config and exit")
    args = parser.parse_args(argv)

    if args.init:
        target = Path(args.config)
        if target.exists():
            print(f"error: {target} already exists", file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(EXAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target}")
        return 0

    try:
        config = load_config(args.config)
        records, report = run(config, only=args.profile,
                              dry_run=args.dry_run, timeout=args.timeout)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    unique, stats = dedup_jobs.merge_pool(records)

    if args.dry_run:
        for entry in report:
            target = f"{entry['profile']}"
            if entry.get("portal"):
                target += f" / {entry['portal']}"
            print(f"[{entry['status']}] {target}")
            if entry.get("command"):
                print(f"    {entry['command']}")
        return 0

    try:
        store = dedup_jobs.load_seen(args.seen)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    known = dedup_jobs.seen_keys(store)
    new = [r for r in unique if r["dedup_key"] not in known]
    stats.update(new=len(new), already_seen=len(unique) - len(new))

    if args.update_seen:
        stats["seen_entries_added"] = dedup_jobs.update_seen(store, unique)
        Path(args.seen).parent.mkdir(parents=True, exist_ok=True)
        Path(args.seen).write_text(
            json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    pool = {"meta": {"date": date.today().isoformat(), **stats},
            "portals": report, "new": new}
    text = json.dumps(pool, indent=2, ensure_ascii=False) + "\n"

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        failed = [e for e in report if e["status"] in {"failed", "missing"}]
        print(f"{stats['input_records']} records -> {stats['unique_jobs']} unique, "
              f"{stats['new']} new -> {args.out}"
              + (f" ({len(failed)} portal(s) failed)" if failed else ""))
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
