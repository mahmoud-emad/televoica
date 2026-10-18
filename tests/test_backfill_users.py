"""Tests for the log backfill script."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_users.py"
spec = importlib.util.spec_from_file_location("backfill_users", SCRIPT)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)

PFX = "televoica.bot.telegram_bot - INFO - "
LOG = (
    f"2026-05-19 10:04:43,835 - {PFX}Downloaded audio file from user 11: /tmp/x\n"
    f"2026-05-19 10:08:03,492 - {PFX}Transcription sent to user 11\n"
    f"2026-06-08 08:13:41,685 - {PFX}Downloaded voice message from user 22: /tmp/y\n"
    f"2026-06-09 09:21:38,377 - {PFX}Downloaded voice message from user 11: /tmp/z\n"
    "2026-06-09 09:22:00,000 - httpx - INFO - HTTP Request: POST https://x\n"
)


def test_parse_log_groups_requests_and_marks_success(tmp_path):
    log = tmp_path / "bot.log"
    log.write_text(LOG)

    reqs = backfill.parse_log(log)

    assert sorted(reqs) == [11, 22]
    assert [r["ok"] for r in reqs[11]] == [True, False]  # second one never got a reply
    assert reqs[11][0]["kind"] == "audio file"
    assert reqs[22][0]["created_at"] == "2026-06-08T08:13:41+00:00"
