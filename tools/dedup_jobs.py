#!/usr/bin/env python3
"""Deduplicate job postings across portals, and merge them into seen_jobs.json.

Run from anywhere:
    python3 tools/dedup_jobs.py merge xing=xing.json stepstone=stepstone.json
    python3 tools/dedup_jobs.py key --company "Bertrandt AG" --title "Data Engineer (m/w/d)"

Why this exists
---------------
`/scrape` runs 5-7 portals per query and the same posting appears on several of
them under a different URL every time. URL matching never catches that, and raw
`company + title` matching misses most of it, because each board renders the
same job slightly differently.

The normalization below is not guesswork - it is the rule measured across two
hand-labelled live pools ("Data Engineer"/Berlin, 96 records; "Softwareentwickler"/
Munchen, 86 records), documented in .claude/skills/job-scraper/SKILL.md:

    strategy                          recall    wrong merges
    URL or raw company+title          13/18     0
    normalized key, exact match       18/18     0     <- this file
    normalized + fuzzy >= 0.88        18/18     2

In both pools every genuine duplicate scored a post-normalization similarity of
exactly 1.0000, so fuzzy matching buys no recall and only risks collapsing a
senior role into a mid-level one. Hence: exact equality on the normalized key,
no thresholds anywhere in this file.

Stdlib only. Exit 0 on success, 1 on a usage or input error.
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Normalization - the six steps specified in job-scraper/SKILL.md Step 2
# ---------------------------------------------------------------------------

# Step 1. Xing injects U+00AD into titles and company names for typographic
# hyphenation: "Da­ta En­gi­neer" renders as "Data Engineer" but
# never string-matches it.
INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"), None)

# Step 2. German transliteration, applied before accent stripping so the umlaut
# becomes "ae" (how German itself spells it) rather than a bare "a".
UMLAUTS = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
}

# Step 3. Observed live: "Securiton GmbH - IPS..." on StepStone vs
# "Securiton GmbH – IPS..." on Xing - the same job.
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")

# Step 4. Gender markers, in every spelling observed across the two pools.
# Slashed - (m/w/d), (w/m/d), (m/f/d), (d/m/w), (w/d/m), (f/m/x), (m/w/i) -
# with the brackets optional, since some portals drop them.
_GENDER_SLASHED = re.compile(r"[(\[]?\s*[mwfdxign]\s*(?:/\s*[mwfdxign]\s*){1,2}[)\]]?")
# Slashless - Indeed emits "(mwd)" with the separators stripped out entirely.
_GENDER_SLASHLESS = re.compile(r"[(\[]\s*(?:mwd|wmd|mfd|fmd|dmw|wdm|fmx|mwi|gn)\s*[)\]]")
_GENDER_WORDED = re.compile(r"[(\[]\s*(?:all\s+genders?|alle\s+geschlechter)\s*[)\]]")
# German gender-inclusive suffix: "Entwickler:in", "Entwickler*in",
# "Entwickler:innen" -> "entwickler". Must run before the bare-* rule below,
# which would otherwise eat the "*" and strand a dangling "in".
_GENDER_SUFFIX = re.compile(r"[:*_]in(?:nen)?\b")
# A bare trailing "*" or "(*)" used as a shorthand gender marker.
_GENDER_STAR = re.compile(r"\(\s*\*\s*\)|\*")

# Step 5. Legal-form and group suffixes. Portals disagree constantly here:
# "Bertrandt AG" (StepStone) vs "Bertrandt" (Indeed); "Bundesdruckerei Gruppe
# GmbH" vs "Bundesdruckerei-Gruppe". Matched as whole tokens only.
LEGAL_FORMS = [
    "gmbh & co. kg", "gmbh & co kg", "ag & co. kg", "ag & co kg", "co. kg", "co kg",
    "gmbh", "mbh", "ohg", "gbr", "kgaa", "kg", "gag", "ag", "se", "ug", "e.v.", "ev",
    "gruppe", "group", "holding", "deutschland", "germany",
]


def strip_invisibles(text):
    """Step 1: drop zero-width/soft-hyphen characters, NBSP -> plain space."""
    return text.translate(INVISIBLE).replace(" ", " ")


def _fold(text):
    """Steps 2-3: lowercase, transliterate German, strip accents, unify dashes."""
    text = text.lower()
    for src, dst in UMLAUTS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.translate(DASHES)


def _collapse(text):
    """Step 6: everything non-alphanumeric becomes a single space; trim."""
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_title(title):
    """Normalize a job title for dedup (steps 1-4, then 6)."""
    text = _fold(strip_invisibles(title or ""))
    text = _GENDER_SUFFIX.sub("", text)
    text = _GENDER_WORDED.sub(" ", text)
    text = _GENDER_SLASHLESS.sub(" ", text)
    text = _GENDER_SLASHED.sub(" ", text)
    text = _GENDER_STAR.sub(" ", text)
    return _collapse(text)


def normalize_company(company):
    """Normalize a company name for dedup (steps 1-3, 5, then 6)."""
    text = _fold(strip_invisibles(company or ""))
    # Longest first, so "gmbh & co. kg" is consumed before the bare "gmbh".
    for form in sorted(LEGAL_FORMS, key=len, reverse=True):
        text = re.sub(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", " ", text)
    return _collapse(text)


def dedup_key(company, title):
    """The cross-portal identity of a posting. Compare with exact equality."""
    return f"{normalize_company(company)}|{normalize_title(title)}"


# ---------------------------------------------------------------------------
# Pool merging
# ---------------------------------------------------------------------------

# When the same job lands from several portals, keep the record from the portal
# that gives the richest detail. Ordered by what each portal actually delivers:
# arbeitsagentur returns full plain-text descriptions from the federal API;
# arbeitnow inlines the whole description in search output; stepstone sits low
# because its `detail` endpoint is unreachable (connection reset - see its
# SKILL.md), so a stepstone record cannot be deepened later.
PORTAL_PRIORITY = [
    "arbeitsagentur-search", "arbeitnow-search", "linkedin-search",
    "xing-search", "indeed", "freehire-search", "stepstone-search",
]


def portal_rank(portal):
    name = (portal or "").strip()
    for index, known in enumerate(PORTAL_PRIORITY):
        if name == known or name == known.removesuffix("-search"):
            return index
    return len(PORTAL_PRIORITY)


def extract_records(payload, portal):
    """Pull job records out of a portal's `--format json` output.

    Tolerates the three shapes actually produced in this repo: the portal CLI
    envelope {"meta":..., "results":[...]}, an MCP tool's {"jobs":[...]}, and a
    bare list.
    """
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("results") or payload.get("jobs") or payload.get("data") or []
    else:
        rows = []

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = dict(row)
        record["portal"] = row.get("portal") or portal
        records.append(record)
    return records


def merge_pool(records):
    """Collapse duplicates within a pool.

    Returns (unique, stats). Each unique record carries its `dedup_key` and an
    `also_on` list naming the other portals that surfaced the same job - never
    dropping the alternate URLs, so a rotted link on one board still has a
    working route on another.
    """
    groups = {}
    order = []
    for record in records:
        key = dedup_key(record.get("company"), record.get("title"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(record)

    unique = []
    for key in order:
        members = sorted(groups[key], key=lambda r: portal_rank(r.get("portal")))
        best = dict(members[0])
        best["dedup_key"] = key

        also_on = []
        seen_portals = {best.get("portal")}
        for other in members[1:]:
            portal = other.get("portal")
            url = other.get("url")
            if (portal, url) in {(a.get("portal"), a.get("url")) for a in also_on}:
                continue
            if portal == best.get("portal") and url == best.get("url"):
                continue  # same portal returned the identical row twice
            also_on.append({"portal": portal, "url": url})
            seen_portals.add(portal)
        if also_on:
            best["also_on"] = also_on
        unique.append(best)

    collapsed = len(records) - len(unique)
    stats = {
        "input_records": len(records),
        "unique_jobs": len(unique),
        "duplicates_collapsed": collapsed,
        "redundancy_pct": round(100 * collapsed / len(records), 1) if records else 0.0,
    }
    return unique, stats


def load_seen(path):
    """Read seen_jobs.json, tolerating a missing file and legacy URL keys."""
    if not path or not Path(path).is_file():
        return {"seen": {}}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("seen"), dict):
        raise ValueError(f"{path}: expected an object with a 'seen' object")
    return data


def seen_keys(store):
    """Every key a stored entry can be recognised by.

    Entries written before the normalized key existed are keyed on the raw URL.
    Read them tolerantly - recompute their real key from the stored company and
    title - but never rewrite them here; that is `--update-seen`'s job.
    """
    keys = set()
    for stored_key, entry in store.get("seen", {}).items():
        keys.add(stored_key)
        if isinstance(entry, dict) and (entry.get("company") or entry.get("title")):
            keys.add(dedup_key(entry.get("company"), entry.get("title")))
    return keys


def update_seen(store, records, today=None):
    """Merge records into the seen store without dropping any existing field.

    `/rank` writes rank_score, rank_verdict, strengths, and gaps onto these same
    entries. This only ever adds or refreshes `also_on`, so re-running /scrape
    cannot wipe a ranking.
    """
    today = today or date.today().isoformat()
    seen = store.setdefault("seen", {})
    added = 0
    for record in records:
        key = record.get("dedup_key") or dedup_key(record.get("company"), record.get("title"))
        entry = seen.get(key)
        if entry is None:
            seen[key] = {
                "title": record.get("title"),
                "company": record.get("company"),
                "url": record.get("url"),
                "first_seen": today,
                "fit": record.get("fit"),
                "status": record.get("status", "new"),
                "portal": record.get("portal"),
                **({"also_on": record["also_on"]} if record.get("also_on") else {}),
            }
            added += 1
        elif record.get("also_on"):
            merged = list(entry.get("also_on", []))
            existing = {(a.get("portal"), a.get("url")) for a in merged}
            for alt in record["also_on"]:
                if (alt.get("portal"), alt.get("url")) not in existing:
                    merged.append(alt)
            entry["also_on"] = merged
    return added


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_input_spec(spec):
    """Accept `portal=path.json`, or a bare path whose stem names the portal."""
    if "=" in spec:
        portal, _, path = spec.partition("=")
        return portal.strip(), Path(path)
    path = Path(spec)
    return path.stem, path


def render_table(records):
    if not records:
        return "No jobs."
    lines = [
        f"{'PORTAL':<22} {'TITLE':<44} {'COMPANY':<26} ALSO ON",
        "-" * 108,
    ]
    for record in records:
        also = ",".join(a.get("portal") or "?" for a in record.get("also_on", [])) or "-"
        lines.append(
            f"{(record.get('portal') or '-')[:22]:<22} "
            f"{(record.get('title') or '-')[:44]:<44} "
            f"{(record.get('company') or '-')[:26]:<26} {also}"
        )
    return "\n".join(lines)


def cmd_merge(args):
    records = []
    for spec in args.inputs:
        portal, path = parse_input_spec(spec)
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 1
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            print(f"error: {path} is not valid JSON: {exc}", file=sys.stderr)
            return 1
        records.extend(extract_records(payload, portal))

    unique, stats = merge_pool(records)

    try:
        store = load_seen(args.seen)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    known = seen_keys(store)

    new = [r for r in unique if r["dedup_key"] not in known]
    already = [r for r in unique if r["dedup_key"] in known]
    stats["already_seen"] = len(already)
    stats["new"] = len(new)

    if args.update_seen:
        target = args.update_seen
        stats["seen_entries_added"] = update_seen(store, unique)
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

    if args.format == "table":
        print(render_table(new))
        print(
            f"\n{stats['input_records']} records -> {stats['unique_jobs']} unique "
            f"({stats['duplicates_collapsed']} duplicates, {stats['redundancy_pct']}%); "
            f"{stats['new']} new, {stats['already_seen']} already seen"
        )
    else:
        print(json.dumps({"meta": stats, "new": new, "already_seen": already},
                         indent=2, ensure_ascii=False))
    return 0


def cmd_key(args):
    print(dedup_key(args.company, args.title))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dedup_jobs.py",
        description="Deduplicate job postings across portals using the normalized key.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    merge = sub.add_parser("merge", help="collapse duplicates across portal result files")
    merge.add_argument(
        "inputs", nargs="+",
        help="portal result files, as `portal-name=path.json` or a bare path "
             "whose filename stem names the portal",
    )
    merge.add_argument("--seen", default="job_scraper/seen_jobs.json",
                       help="seen_jobs.json to check against (default: %(default)s)")
    merge.add_argument("--update-seen", nargs="?", const="job_scraper/seen_jobs.json",
                       default=None, metavar="PATH",
                       help="write merged jobs back into the seen store")
    merge.add_argument("--format", choices=["json", "table"], default="json")
    merge.set_defaults(func=cmd_merge)

    key = sub.add_parser("key", help="print the normalized dedup key for one posting")
    key.add_argument("--company", required=True)
    key.add_argument("--title", required=True)
    key.set_defaults(func=cmd_key)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
