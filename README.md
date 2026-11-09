# ChouseisanScheduleBot

毎週開催し、スタッフの都合に合わせて開催曜日を決めるVRChatイベント向けのBotです。
翌週の候補日をまとめた調整さんを作成し、スタッフが回答できるようDiscordにURLを投稿します。

## 設定する場所

| 変更したいもの | ファイル |
| --- | --- |
| 投稿する曜日・時刻 | `.github/workflows/schedule.yml` の `cron` |
| 調整さんの名前・説明、Discordの投稿文 | `config.toml` の `[event]` |
| 募集対象の日付・締切 | `config.toml` の `[dates]` |

募集の投稿は初期設定で **毎週木曜08:30（日本時間）** です。1回の実行で1件の調整さんを作ります。
調整さんの説明文には **22:00〜23:00開催・21:45集合** の例を入れています。
イベントに合わせて `[event]` の `memo` を編集してください。
Discordの投稿文にも開催時刻を載せたい場合は、`message_template` にその案内を追記できます。
メンションする場合は `[event]` の `mention` にロールIDを設定します。

## GitHub Actionsで使う

1. 自分のGitHubリポジトリにこのコードを配置します。
2. Settings → Secrets and variables → Actions で `DISCORD_WEBHOOK_URL` を登録します。
3. `config.toml` と `.github/workflows/schedule.yml` を編集してコミットします。
4. Actions → Post Schedule → Run workflow でプレビューできます。
   実際に作成・投稿する場合は `post` にチェックを付けます。

定期実行はデフォルトブランチの `schedule.yml` に従います。

### 投稿する曜日・時刻を変更する

`.github/workflows/schedule.yml` の `cron` を編集します。書式は「分 時 日 月 曜日」です。
毎週実行するなら、真ん中の `* *` はそのままにします。
曜日は日曜が `0`、月曜が `1`、土曜が `6` です。全曜日の番号はファイル内のコメントにあります。

たとえば、月曜19:15に投稿するなら `cron: '15 19 * * 1'` と書きます。
`timezone` を変更する場合は、日付計算用の `config.toml` の `[dates].timezone` も同じ値にします。

[GitHub公式のschedule仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 募集対象の日付

初期設定では、次の計算をします。

1. 実行日より後に来る日曜日を探す。同じ日曜日は採用しない。
2. その1週間後を基準日とする。
3. 基準日の6日前（月曜日）から7日間を候補日にする。
4. 候補初日の2日前を締切にする。
5. 基準日の月と日から「○月第○週」というイベント名を作る。

例：2026/11/5(木)の実行では、
イベント名は「11月第3週」、候補日は11/9(月)〜11/15(日)、締切は11/7(土)です。
月末や年末でも**日曜日の基準日**でタイトルを決めます。
日曜に手動実行した場合は、元の仕様どおり翌々週日曜を基準にします。

| 設定 | 意味 |
| --- | --- |
| `reference_weekday` | 基準曜日。月=0〜日=6 |
| `additional_weeks` | 次の基準曜日から何週先か |
| `start_offset_days` | 基準日から候補初日までの日数 |
| `candidate_count` | 候補日数 |
| `deadline_offset_days` | 候補初日から締切までの日数。0なら同日 |
| `candidate_template` | 候補日の表示。例：`{date:%m/%d}({weekday})` |
| `deadline_template` | 締切の文面 |

日付計算には `[dates].timezone` を使います。
「第○週」は `(基準日の日 - 1) // 7 + 1` で、ISO週番号ではありません。

## 文面の変数

| 変数 | 内容 |
| --- | --- |
| `{year}`、`{month}`、`{week_of_month}` | 基準日の年・月・第○週 |
| `{reference:%Y/%m/%d}` | 基準日 |
| `{start:%m/%d}`、`{end:%m/%d}` | 候補初日・最終日 |
| `{deadline.month}`、`{deadline.day}` | 締切の月・日 |
| `{deadline_weekday}` | 締切の曜日 |
| `{deadline_text}` | 組み立てた締切文。イベント名と投稿文で使用可 |
| `{mention}` | メンション。投稿文で使用可 |
| `{event_url}` | 調整さんの回答用URL。投稿文に必須 |

`memo` はそのまま調整さんに入力する説明文です。変数を展開しません。
`candidate_template` では `{date}` と `{weekday}` を使用します。
文字として波括弧を書きたい場合は `{{`、`}}` と重ねてください。

## ローカルで確認・実行する

```console
python -m pip install -r requirements.txt
python main.py --dry-run --date 2026-11-05
python -m unittest discover -s tests -v
```

`--dry-run` は調整さんの作成・Discord投稿・ブラウザー起動をしません。
表示されるURLはダミーです。`--date` はdry-runでのみ使用できます。
実行例の `python` はPython 3.9以上を指します。複数バージョンがあるWindowsでは
`py -3.11` などに置き換えてください。

実際にローカル実行する場合：

```powershell
$env:DISCORD_WEBHOOK_URL = "自分のWebhook URL"
python main.py
```

`.env` の自動読み込みはしません。
ローカルでの `python main.py` は直ちに1回実行します。常駐して時刻を待つ処理はありません。

## Pythonを改変する

まず `main.py` を開きます。候補日や締切を変える場合は `get_event_info`、
調整さんの作成から投稿までの流れは `run` を見てください。

| ファイル | 役割 |
| --- | --- |
| `main.py` | 日付計算、文面の組み立て、作成と投稿の順序 |
| `services.py` | 調整さんへの入力とDiscordへの送信 |
| `settings.py` | 設定ファイルの読み込みとチェック |
| `cli.py` | コマンドライン引数とエラーの表示 |

作成・投稿をやり直すと、新しい調整さんが作られます。

MIT License。詳細は `LICENSE` を参照してください。
