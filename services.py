"""調整さんの作成とDiscordへの送信。"""

import os
from urllib.parse import urljoin, urlsplit


def require_webhook_url():
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("環境変数 DISCORD_WEBHOOK_URL が設定されていません。")
    return webhook_url


def create_event(event_name, candidates, memo, service_config):
    # dry-run と日付計算にはブラウザー関連の依存を必要としない。
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    for arg in ["--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]:
        options.add_argument(arg)
    service = Service(ChromeDriverManager().install())
    with webdriver.Chrome(service=service, options=options) as driver:
        driver.set_page_load_timeout(service_config["wait_seconds"])
        wait = WebDriverWait(driver, service_config["wait_seconds"])
        driver.get(service_config["base_url"])
        wait.until(EC.visibility_of_element_located((By.ID, "name"))).send_keys(event_name)
        driver.find_element(By.ID, "comment").send_keys(memo)
        candidates_box = driver.find_element(By.ID, "kouho")
        candidates_box.clear()
        candidates_box.send_keys("\n".join(candidates))
        wait.until(EC.element_to_be_clickable((By.ID, "createBtn"))).click()
        href = wait.until(
            lambda browser: browser.find_element(By.ID, "listLink").get_attribute("href"),
        )
        event_url = urljoin(service_config["base_url"], href)
        parsed = urlsplit(event_url)
        if (parsed.scheme != "https" or parsed.hostname != "chouseisan.com"
                or parsed.path != "/s" or not parsed.query):
            raise RuntimeError("調整さんの回答用URLを取得できませんでした。")
        return event_url


def post_to_discord(webhook_url, content, timeout):
    import requests

    try:
        response = requests.post(webhook_url, json={"content": content}, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as error:
        # requestsの例外には秘密のWebhook URLが含まれるため表示しない。
        status = error.response.status_code if error.response is not None else "接続失敗"
        raise RuntimeError(f"Discord送信に失敗しました（{status}）。") from None
