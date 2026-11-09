"""調整さんで日程を作成し、回答用URLをDiscordに投稿する。"""

import json
import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cli import run_cli
from services import create_event, post_to_discord, require_webhook_url
from settings import WEEKDAYS


def get_event_info(config, today=None):
    """募集する日付と締切を計算する。"""
    dates = config["dates"]
    if today is None:
        today = datetime.now(ZoneInfo(dates["timezone"])).date()
    # 次の基準曜日までの日数を求める。同じ曜日なら翌週にする。
    days_until_reference = (dates["reference_weekday"] - today.weekday()) % 7
    if days_until_reference == 0:
        days_until_reference = 7

    # 初期設定では翌週の日曜が基準日で、候補はその週の月曜から始まる。
    reference = today + timedelta(days=days_until_reference + 7 * dates["additional_weeks"])
    start = reference + timedelta(days=dates["start_offset_days"])
    deadline = start + timedelta(days=dates["deadline_offset_days"])
    # 設定ファイルの文面で使う変数をまとめる。
    context = {
        "reference": reference,
        "start": start,
        "end": start + timedelta(days=dates["candidate_count"] - 1),
        "deadline": deadline,
        "deadline_weekday": WEEKDAYS[deadline.weekday()],
        "year": reference.year,
        "month": reference.month,
        "week_of_month": (reference.day - 1) // 7 + 1,
    }
    context["deadline_text"] = dates["deadline_template"].format(**context)
    candidates = []
    for offset in range(dates["candidate_count"]):
        candidate = start + timedelta(days=offset)
        candidates.append(dates["candidate_template"].format(
            date=candidate, weekday=WEEKDAYS[candidate.weekday()],
        ))
    return context, candidates


def make_discord_message(event, context, event_url):
    content = event["message_template"].format(
        **context, mention=event["mention"], event_url=event_url,
    ).strip()
    if not 1 <= len(content) <= 2000:
        raise ValueError("Discord投稿文は1〜2000文字にしてください。")
    return content


def build_plan(config, today=None):
    """作成するイベントと投稿文を、外部アクセス前に検証する。"""
    context, candidates = get_event_info(config, today)
    event = config["event"]
    name = event["name_template"].format(**context)
    if not name.strip():
        raise ValueError("イベント名が空です。")
    preview_url = "https://chouseisan.com/s?h=00000000000000000000000000000000"
    message = make_discord_message(event, context, preview_url)
    return context, {
        "name": name, "memo": event["memo"], "candidates": candidates, "message": message,
    }


def run(config, dry_run=False, today=None):
    context, plan = build_plan(config, today)
    if dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    webhook_url = require_webhook_url()

    # 調整さんを作成して、回答用URLを投稿文に入れる。
    logging.info("イベント作成開始: %s", plan["name"])
    event_url = create_event(plan["name"], plan["candidates"], plan["memo"], config["service"])
    message = make_discord_message(config["event"], context, event_url)
    post_to_discord(webhook_url, message, config["service"]["request_timeout_seconds"])
    logging.info("Discord投稿完了: %s", plan["name"])


if __name__ == "__main__":
    sys.exit(run_cli(run))
