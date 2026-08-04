#!/usr/bin/env python3
"""Render a scrape pool as an HTML email and send it over SMTP.

    python3 tools/send_digest.py job_scraper/pools/2026-08-04.json --html-out /tmp/d.html
    python3 tools/send_digest.py job_scraper/pools/2026-08-04.json

Reads the pool written by tools/run_scrape.py and mails it to you. Stdlib only,
no model, no API key - so cron can run it unattended.

Credentials come from the environment, or from a .env file beside the repo root
(gitignored, never committed):

    JOBSEARCH_SMTP_HOST      default smtp.gmail.com
    JOBSEARCH_SMTP_PORT      default 587 (STARTTLS); 465 switches to implicit TLS
    JOBSEARCH_SMTP_USER      the sending account
    JOBSEARCH_SMTP_PASSWORD  a Gmail *app password*, not your account password
    JOBSEARCH_DIGEST_TO      recipient; defaults to SMTP_USER
    JOBSEARCH_DIGEST_FROM    sender; defaults to SMTP_USER

Gmail requires an app password with 2FA enabled - a normal account password is
rejected. Generate one at https://myaccount.google.com/apppasswords.

Exit 0 on success, 1 on a config, render, or delivery error.
"""

import argparse
import html
import os
import smtplib
import ssl
import stat
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

DEFAULTS = {
    "JOBSEARCH_SMTP_HOST": "smtp.gmail.com",
    "JOBSEARCH_SMTP_PORT": "587",
}


class DigestError(Exception):
    """Raised when the digest cannot be built or delivered."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def parse_env_file(path):
    """Minimal KEY=VALUE reader. No dependency on python-dotenv."""
    values = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def check_permissions(path, warn=print):
    """Warn if a file holding an app password is readable by anyone else."""
    mode = Path(path).stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        warn(f"warning: {path} is readable by other users; run: chmod 600 {path}")


def load_config(env=None, env_file=ENV_FILE, warn=print):
    """Environment wins over .env, so a cron override needs no file edit."""
    env = os.environ if env is None else env
    values = dict(DEFAULTS)
    if env_file and Path(env_file).is_file():
        check_permissions(env_file, warn)
        values.update(parse_env_file(env_file))
    for key in list(DEFAULTS) + ["JOBSEARCH_SMTP_USER", "JOBSEARCH_SMTP_PASSWORD",
                                 "JOBSEARCH_DIGEST_TO", "JOBSEARCH_DIGEST_FROM"]:
        if env.get(key):
            values[key] = env[key]

    user = values.get("JOBSEARCH_SMTP_USER")
    config = {
        "host": values.get("JOBSEARCH_SMTP_HOST"),
        "port": values.get("JOBSEARCH_SMTP_PORT"),
        "user": user,
        "password": values.get("JOBSEARCH_SMTP_PASSWORD"),
        "to": values.get("JOBSEARCH_DIGEST_TO") or user,
        "sender": values.get("JOBSEARCH_DIGEST_FROM") or user,
    }
    try:
        config["port"] = int(config["port"])
    except (TypeError, ValueError):
        raise DigestError(f"JOBSEARCH_SMTP_PORT must be a number, got {config['port']!r}")
    return config


def require_credentials(config):
    missing = [name for name, key in
               (("JOBSEARCH_SMTP_USER", "user"), ("JOBSEARCH_SMTP_PASSWORD", "password"),
                ("JOBSEARCH_DIGEST_TO", "to"))
               if not config.get(key)]
    if missing:
        raise DigestError(
            "missing SMTP settings: " + ", ".join(missing) +
            f". Set them in {ENV_FILE} (see .env.example) or in the environment."
        )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# Email clients are not browsers: no flexbox, no grid, no <style> reliability.
# Table layout with inline styles is the format that renders everywhere.
CSS_BODY = "margin:0;padding:24px;background:#f5f6f8;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1b1f24"
CSS_CARD = "max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e1e4e8;border-radius:8px;padding:24px"
CSS_TH = "text-align:left;padding:8px 10px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#57606a;border-bottom:2px solid #e1e4e8"
CSS_TD = "padding:10px;border-bottom:1px solid #eaeef2;font-size:14px;vertical-align:top"


def group_by_profile(jobs):
    groups = {}
    for job in jobs:
        groups.setdefault(job.get("profile") or "unassigned", []).append(job)
    return groups


def job_rows_html(jobs):
    rows = []
    for job in jobs:
        title = html.escape(job.get("title") or "(untitled)")
        url = job.get("url") or ""
        link = (f'<a href="{html.escape(url, quote=True)}" '
                f'style="color:#0969da;text-decoration:none">{title}</a>') if url else title
        also = job.get("also_on") or []
        also_note = (f'<div style="color:#57606a;font-size:12px;margin-top:2px">'
                     f'also on {html.escape(", ".join(a.get("portal") or "?" for a in also))}</div>'
                     ) if also else ""
        rows.append(
            f'<tr><td style="{CSS_TD}">{link}{also_note}</td>'
            f'<td style="{CSS_TD}">{html.escape(job.get("company") or "—")}</td>'
            f'<td style="{CSS_TD}">{html.escape(job.get("location") or "—")}</td>'
            f'<td style="{CSS_TD};color:#57606a">{html.escape(job.get("portal") or "—")}</td></tr>'
        )
    return "".join(rows)


def render_html(pool):
    meta = pool.get("meta", {})
    jobs = pool.get("new", [])
    groups = group_by_profile(jobs)

    parts = [
        f'<body style="{CSS_BODY}"><div style="{CSS_CARD}">',
        f'<h1 style="margin:0 0 4px;font-size:20px">Job digest — {html.escape(str(meta.get("date", "")))}</h1>',
        f'<p style="margin:0 0 20px;color:#57606a;font-size:14px">'
        f'<strong>{meta.get("new", len(jobs))} new</strong> · '
        f'{meta.get("unique_jobs", 0)} unique from {meta.get("input_records", 0)} records · '
        f'{meta.get("duplicates_collapsed", 0)} duplicates collapsed '
        f'({meta.get("redundancy_pct", 0)}%)</p>',
    ]

    if not jobs:
        parts.append('<p style="font-size:14px">No new postings today.</p>')

    for profile, items in groups.items():
        parts.append(
            f'<h2 style="margin:24px 0 8px;font-size:15px;border-bottom:1px solid #eaeef2;'
            f'padding-bottom:6px">{html.escape(profile)} '
            f'<span style="color:#57606a;font-weight:400">({len(items)})</span></h2>'
            f'<table style="width:100%;border-collapse:collapse">'
            f'<tr><th style="{CSS_TH}">Role</th><th style="{CSS_TH}">Company</th>'
            f'<th style="{CSS_TH}">Location</th><th style="{CSS_TH}">Source</th></tr>'
            f'{job_rows_html(items)}</table>'
        )

    # A portal that failed silently is the failure mode this whole pipeline is
    # most exposed to, so it is surfaced in the mail rather than left in a log.
    problems = [p for p in pool.get("portals", [])
                if p.get("status") in {"failed", "missing"}]
    if problems:
        lines = "".join(
            f'<li>{html.escape(p.get("portal") or "?")} '
            f'<span style="color:#57606a">({html.escape(p.get("profile") or "")}) — '
            f'{html.escape(p.get("detail") or p.get("status"))}</span></li>'
            for p in problems)
        parts.append(
            f'<div style="margin-top:24px;padding:12px;background:#fff8c5;'
            f'border:1px solid #d4a72c;border-radius:6px">'
            f'<strong style="font-size:14px">Portal problems</strong>'
            f'<ul style="margin:6px 0 0;padding-left:20px;font-size:13px">{lines}</ul></div>')

    parts.append(
        '<p style="margin-top:24px;color:#8b949e;font-size:12px">'
        'Generated by tools/send_digest.py · reply with the numbers you want to pursue</p>'
        '</div></body>')
    return "".join(parts)


def render_text(pool):
    meta = pool.get("meta", {})
    jobs = pool.get("new", [])
    lines = [f"Job digest — {meta.get('date', '')}",
             f"{meta.get('new', len(jobs))} new · {meta.get('unique_jobs', 0)} unique "
             f"from {meta.get('input_records', 0)} records", ""]
    if not jobs:
        lines.append("No new postings today.")
    for profile, items in group_by_profile(jobs).items():
        lines.append(f"## {profile} ({len(items)})")
        for job in items:
            lines.append(f"  - {job.get('title') or '(untitled)'} — "
                         f"{job.get('company') or '—'} — {job.get('location') or '—'} "
                         f"[{job.get('portal') or '—'}]")
            if job.get("url"):
                lines.append(f"    {job['url']}")
        lines.append("")
    problems = [p for p in pool.get("portals", [])
                if p.get("status") in {"failed", "missing"}]
    if problems:
        lines.append("Portal problems:")
        lines += [f"  - {p.get('portal')} ({p.get('profile')}): "
                  f"{p.get('detail') or p.get('status')}" for p in problems]
    return "\n".join(lines)


def build_message(pool, config):
    meta = pool.get("meta", {})
    count = meta.get("new", len(pool.get("new", [])))
    message = EmailMessage()
    message["Subject"] = f"Job digest {meta.get('date', '')} — {count} new"
    message["From"] = config["sender"]
    message["To"] = config["to"]
    message.set_content(render_text(pool))
    message.add_alternative(render_html(pool), subtype="html")
    return message


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def send(message, config):
    context = ssl.create_default_context()
    try:
        if config["port"] == 465:
            with smtplib.SMTP_SSL(config["host"], config["port"], context=context) as server:
                server.login(config["user"], config["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(config["host"], config["port"]) as server:
                server.starttls(context=context)
                server.login(config["user"], config["password"])
                server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        # Never echo the password, not even truncated.
        raise DigestError(
            f"SMTP authentication failed for {config['user']} ({exc.smtp_code}). "
            "Gmail needs an app password with 2FA enabled - a normal account "
            "password is always rejected."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise DigestError(f"could not send via {config['host']}:{config['port']}: {exc}") from exc


def main(argv=None):
    import json

    parser = argparse.ArgumentParser(
        prog="send_digest.py", description="Email a scrape pool as an HTML digest.")
    parser.add_argument("pool", help="pool JSON written by run_scrape.py --out")
    parser.add_argument("--html-out", metavar="PATH",
                        help="write the rendered HTML here and send nothing "
                             "(no credentials needed - use this to preview)")
    parser.add_argument("--to", help="override the recipient")
    args = parser.parse_args(argv)

    try:
        pool = json.loads(Path(args.pool).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: no pool file at {args.pool}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"error: {args.pool} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if args.html_out:
        Path(args.html_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html_out).write_text(render_html(pool), encoding="utf-8")
        print(f"wrote {args.html_out} ({len(pool.get('new', []))} jobs) - nothing sent")
        return 0

    try:
        config = load_config(warn=lambda m: print(m, file=sys.stderr))
        if args.to:
            config["to"] = args.to
        require_credentials(config)
        send(build_message(pool, config), config)
    except DigestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"sent digest to {config['to']} ({len(pool.get('new', []))} jobs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
