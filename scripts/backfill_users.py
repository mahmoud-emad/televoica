#!/usr/bin/env python3
"""Backfill the user database from an existing bot log.

Older versions of the bot did not keep a user list, but their logs record
every request ("Downloaded voice message from user <id>"). This imports that
history so the database knows past users from day one.

Usage:
    python scripts/backfill_users.py /var/log/televoica/bot.log
    python scripts/backfill_users.py bot.log --fetch-profiles   # needs TELEGRAM_BOT_TOKEN

Safe to re-run: users that already have recorded requests are skipped.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from televoica.bot.registry import UserRegistry  # noqa: E402
from televoica.config.settings import load_config  # noqa: E402

LINE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - televoica\.bot\.telegram_bot - INFO - "
    r"(?:(?P<dl>Downloaded (?P<kind>[a-z ]+) from user (?P<dl_uid>\d+):)"
    r"|(?P<sent>Transcription sent to user (?P<sent_uid>\d+)))"
)


def parse_log(path: Path) -> dict[int, list[dict]]:
    """Group requests per user. A request is a download, ok if a reply followed."""
    requests: dict[int, list[dict]] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            ts = datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if m["dl"]:
                uid = int(m["dl_uid"])
                requests.setdefault(uid, []).append(
                    {"kind": m["kind"], "ok": False, "created_at": ts.isoformat(timespec="seconds")}
                )
            else:
                uid = int(m["sent_uid"])
                if requests.get(uid):
                    requests[uid][-1]["ok"] = True
    return requests


def fetch_profile(token: str, user_id: int) -> dict:
    """Name/username from Telegram; works for anyone who has messaged the bot."""
    url = f"https://api.telegram.org/bot{token}/getChat?chat_id={user_id}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
            return json.load(resp).get("result") or {}
    except (urllib.error.URLError, ValueError, OSError):
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("log", type=Path, help="bot log file")
    parser.add_argument("--fetch-profiles", action="store_true", help="look up names via Telegram")
    args = parser.parse_args()

    settings = load_config()
    registry = UserRegistry(settings.data_dir / "televoica.db")
    token = os.getenv("TELEGRAM_BOT_TOKEN") if args.fetch_profiles else None
    if args.fetch_profiles and not token:
        sys.exit("--fetch-profiles needs TELEGRAM_BOT_TOKEN in the environment")

    imported = 0
    for user_id, reqs in parse_log(args.log).items():
        existing = registry.get(user_id)
        if existing and existing["request_count"] > 0:
            print(f"skip {user_id}: already has {existing['request_count']} recorded requests")
            continue
        profile = fetch_profile(token, user_id) if token else {}
        registry.upsert(
            user_id,
            username=profile.get("username"),
            first_name=profile.get("first_name"),
            last_name=profile.get("last_name"),
            seen_at=reqs[0]["created_at"],
        )
        for r in reqs:
            registry.record_request(user_id, r["kind"], r["ok"], created_at=r["created_at"])
        imported += 1
        print(f"imported {user_id}: {len(reqs)} requests")
    print(f"done: {imported} users imported; {registry.stats()}")


if __name__ == "__main__":
    main()
