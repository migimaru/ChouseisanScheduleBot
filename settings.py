"""共有設定の読み込みと、外部アクセス前の検証。"""

from pathlib import Path
from string import Formatter
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.toml"
WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")
CONTEXT_FIELDS = {
    "reference", "start", "end", "deadline", "year", "month", "week_of_month",
    "deadline_weekday", "deadline_text", "mention", "event_url",
}


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} は {minimum}〜{maximum} の整数で指定してください。")


def check_template(template, fields, name):
    if not isinstance(template, str) or not template.strip():
        raise ValueError(f"{name} は空でない文字列で指定してください。")
    for _, field, spec, conversion in Formatter().parse(template):
        if field is None:
            continue
        root = field.split(".")[0]
        if root not in fields or "[" in field or "{" in spec or conversion:
            raise ValueError(f"{name}: 使用できない変数 {{{field}}} です。")


def load_config(path=DEFAULT_CONFIG):
    with Path(path).open("rb") as file:
        config = tomllib.load(file)
    dates = config["dates"]
    # 以前の設定ファイルではタイムゾーンが [schedule] にある。
    dates.setdefault("timezone", config.get("schedule", {}).get("timezone", "Asia/Tokyo"))
    ZoneInfo(dates["timezone"])
    for key, minimum, maximum in (
        ("reference_weekday", 0, 6), ("additional_weeks", 0, 52),
        ("start_offset_days", -366, 366), ("candidate_count", 1, 31),
        ("deadline_offset_days", -366, 0),
    ):
        integer(dates[key], f"dates.{key}", minimum, maximum)
    check_template(dates["candidate_template"], {"date", "weekday"}, "candidate_template")
    check_template(
        dates["deadline_template"],
        CONTEXT_FIELDS - {"deadline_text", "mention", "event_url"}, "deadline_template",
    )

    service = config["service"]
    base = urlsplit(service["base_url"])
    if (base.scheme != "https" or base.hostname != "chouseisan.com"
            or base.username or base.password or base.port):
        raise ValueError("service.base_url は https://chouseisan.com を指定してください。")
    for key, minimum, maximum in (
        ("wait_seconds", 1, 300), ("request_timeout_seconds", 1, 300),
    ):
        integer(service[key], f"service.{key}", minimum, maximum)

    event = config["event"]
    if not isinstance(event, dict):
        raise ValueError("[event] にイベントを1つ設定してください。")
    check_template(
        event["name_template"], CONTEXT_FIELDS - {"mention", "event_url"}, "name_template",
    )
    check_template(event["message_template"], CONTEXT_FIELDS, "message_template")
    if not isinstance(event["memo"], str) or not isinstance(event["mention"], str):
        raise ValueError("memo と mention は文字列で指定してください。")
    if "{event_url}" not in event["message_template"]:
        raise ValueError("message_template には {event_url} が必要です。")
    return config
