import contextlib
import io
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main
from settings import DEFAULT_CONFIG, load_config

class ScheduleBotTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_normal_week(self):
        context, plan = main.build_plan(self.config, date(2026, 11, 5))
        self.assertEqual(context["reference"], date(2026, 11, 15))
        self.assertEqual(context["deadline"], date(2026, 11, 7))
        self.assertEqual(plan["name"], "11月第3週")
        self.assertEqual(plan["candidates"], [
            "11/09(月)", "11/10(火)", "11/11(水)", "11/12(木)",
            "11/13(金)", "11/14(土)", "11/15(日)",
        ])
        self.assertIn("11/7(土)", plan["message"])
        self.assertFalse(plan["message"].startswith("\n"))

    def test_month_and_year_boundaries(self):
        cases = [
            (date(2026, 1, 29), date(2026, 2, 8), "2月第2週", date(2026, 2, 2)),
            (date(2026, 12, 24), date(2027, 1, 3), "1月第1週", date(2026, 12, 28)),
            (date(2028, 2, 24), date(2028, 3, 5), "3月第1週", date(2028, 2, 28)),
        ]
        for today, reference, name, start in cases:
            with self.subTest(today=today):
                context, plan = main.build_plan(self.config, today)
                self.assertEqual(context["reference"], reference)
                self.assertEqual(context["start"], start)
                self.assertEqual(plan["name"], name)

    def test_sunday_uses_following_sunday_then_adds_week_as_original(self):
        context, _ = main.get_event_info(self.config, date(2026, 11, 8))
        self.assertEqual(context["reference"], date(2026, 11, 22))
        self.assertEqual(context["start"], date(2026, 11, 16))

    def test_uses_same_event_text_each_week(self):
        self.config["event"]["message_template"] = "今週の参加確認\n{event_url}"
        for today in [date(2026, 11, 5), date(2026, 11, 12)]:
            _, plan = main.build_plan(self.config, today)
            self.assertEqual(plan["memo"], self.config["event"]["memo"])
            self.assertTrue(plan["message"].startswith("今週の参加確認\n"))

    def test_uses_configured_timezone_at_utc_date_boundary(self):
        class FixedDatetime:
            @staticmethod
            def now(tz):
                return datetime(2026, 11, 7, 16, 0, tzinfo=timezone.utc).astimezone(tz)
        with patch.object(main, "datetime", FixedDatetime):
            context, _ = main.get_event_info(self.config)
        # UTCでは土曜だが、日本では日曜。元のSundayルールを適用。
        self.assertEqual(context["reference"], date(2026, 11, 22))

    def test_deadline_weekday_is_not_hardcoded(self):
        self.config["dates"]["deadline_offset_days"] = -3
        _, plan = main.build_plan(self.config, date(2026, 11, 5))
        self.assertIn("11/6(金)", plan["message"])

    def test_dry_run_never_creates_or_posts(self):
        with patch.object(main, "create_event") as create, patch.object(main, "post_to_discord") as post:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                main.run(self.config, dry_run=True, today=date(2026, 11, 5))
            self.assertEqual(json.loads(output.getvalue())["name"], "11月第3週")
            create.assert_not_called()
            post.assert_not_called()

    def test_missing_webhook_never_creates_event(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main, "create_event") as create:
            with self.assertRaisesRegex(ValueError, "DISCORD_WEBHOOK_URL"):
                main.run(self.config)
            create.assert_not_called()

    def test_invalid_template_is_rejected_before_creating_event(self):
        self.config["event"]["message_template"] = "{unknown}"
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "test"}), patch.object(main, "create_event") as create:
            with self.assertRaises(KeyError):
                main.run(self.config)
            create.assert_not_called()

    def test_creation_failure_never_posts(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "test"}):
            with patch.object(main, "create_event", side_effect=RuntimeError("failed")):
                with patch.object(main, "post_to_discord") as post:
                    with self.assertRaises(RuntimeError):
                        main.run(self.config)
                    post.assert_not_called()

    def test_single_event_is_created_and_posted_once(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "test"}):
            with patch.object(main, "create_event", return_value="https://chouseisan.com/s?h=created") as create:
                with patch.object(main, "post_to_discord") as send:
                    main.run(self.config, today=date(2026, 11, 5))
        create.assert_called_once()
        send.assert_called_once()
        self.assertEqual(create.call_args.args[0], "11月第3週")
        self.assertIn("h=created", send.call_args.args[1])

    def test_discord_errors_do_not_include_secret_url(self):
        import requests
        secret = "https://discord.com/api/webhooks/SECRET"
        with patch.object(requests, "post", side_effect=requests.ConnectionError(secret)):
            with self.assertRaises(RuntimeError) as caught:
                main.post_to_discord(secret, "test", 30)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_discord_payload_and_timeout(self):
        import requests
        with patch.object(requests, "post") as post:
            main.post_to_discord("secret", "message", 30)
        post.assert_called_once_with("secret", json={"content": "message"}, timeout=30)
        post.return_value.raise_for_status.assert_called_once()

    def test_invalid_configs_fail_early(self):
        original = DEFAULT_CONFIG.read_text(encoding="utf-8")
        replacements = [
            ('reference_weekday = 6', 'reference_weekday = 7'),
            ('candidate_count = 7', 'candidate_count = 0'),
            ('{event_url}', '{unknown}'),
            ('{month}', '{unknown}'),
            ('Asia/Tokyo', 'NoSuch/Zone'),
        ]
        for old, new in replacements:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "config.toml"
                path.write_text(original.replace(old, new), encoding="utf-8")
                with self.assertRaises((ValueError, KeyError)):
                    load_config(path)

    def test_browser_form_and_answer_link(self):
        import types
        from unittest.mock import MagicMock
        elements = {key: MagicMock() for key in ["name", "comment", "kouho", "createBtn", "listLink"]}
        for element in elements.values():
            element.is_displayed.return_value = True
            element.is_enabled.return_value = True
        elements["listLink"].get_attribute.return_value = "https://chouseisan.com/s?h=created"
        driver = MagicMock()
        driver.find_element.side_effect = lambda by, key: elements[key]
        chrome_module = types.ModuleType("webdriver_manager.chrome")
        chrome_module.ChromeDriverManager = MagicMock()
        chrome_module.ChromeDriverManager.return_value.install.return_value = "/mock/chromedriver"
        with patch.dict("sys.modules", {"webdriver_manager.chrome": chrome_module}):
            with patch("selenium.webdriver.Chrome") as chrome:
                chrome.return_value.__enter__.return_value = driver
                result = main.create_event("title", ["11/09(月)", "11/10(火)"], "memo", self.config["service"])
        self.assertEqual(result, "https://chouseisan.com/s?h=created")
        elements["name"].send_keys.assert_called_once_with("title")
        elements["comment"].send_keys.assert_called_once_with("memo")
        elements["kouho"].send_keys.assert_called_once_with("11/09(月)\n11/10(火)")
        elements["createBtn"].click.assert_called_once()
        chrome.return_value.__exit__.assert_called_once()

    def test_browser_rejects_unexpected_return_url(self):
        import types
        from unittest.mock import MagicMock
        driver = MagicMock()
        driver.find_element.return_value.is_displayed.return_value = True
        driver.find_element.return_value.is_enabled.return_value = True
        driver.find_element.return_value.get_attribute.return_value = "https://example.com/s?h=unexpected"
        chrome_module = types.ModuleType("webdriver_manager.chrome")
        chrome_module.ChromeDriverManager = MagicMock()
        chrome_module.ChromeDriverManager.return_value.install.return_value = "/mock/chromedriver"
        with patch.dict("sys.modules", {"webdriver_manager.chrome": chrome_module}):
            with patch("selenium.webdriver.Chrome") as chrome:
                chrome.return_value.__enter__.return_value = driver
                with self.assertRaises(RuntimeError):
                    main.create_event("title", ["11/09(月)"], "memo", self.config["service"])

if __name__ == "__main__":
    unittest.main()
