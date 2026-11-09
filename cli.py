"""コマンドライン引数と実行時エラーの表示。"""

import argparse
import logging
import sys
from datetime import date

from settings import DEFAULT_CONFIG, load_config


def run_cli(run, argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="調整さんで日程を作成し、回答用URLをDiscordに投稿する。")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="設定ファイルのパス")
    parser.add_argument("--dry-run", action="store_true", help="表示のみ。外部サービスへアクセスしない")
    parser.add_argument("--date", type=date.fromisoformat, help="dry-run用の実行日（YYYY-MM-DD）")
    args = parser.parse_args(argv)
    if args.date and not args.dry_run:
        parser.error("--date は --dry-run と一緒に指定してください。")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        run(load_config(args.config), args.dry_run, args.date)
    except Exception as error:
        logging.error("%s", error)
        return 1
    return 0
