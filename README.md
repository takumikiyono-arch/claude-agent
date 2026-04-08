# Slack Mention Reminder

自分宛のメンションに返信・スタンプ未対応のものがあれば、8:00〜19:00 の間、毎時間 DM でリマインドを送るツールです。

## 仕組み

- `check_slack_mentions.py` が参加済みチャンネルを全スキャン
- 自分宛メンション（`<@USER_ID>`）のうち、1時間以上経過しているものを対象に
  - スレッド返信があるか
  - リアクションを付けているか
  を確認し、どちらもなければ未対応として DM に通知

## 必要なもの

- Python 3.10+
- `SLACK_BOT_TOKEN` 環境変数（`xoxp-...` または `xoxb-...`）
- Slack スコープ: `channels:history`, `groups:history`, `reactions:read`, `conversations:open`, `chat:write`, `users:read`

## セットアップ

```bash
pip install -r requirements.txt
export SLACK_BOT_TOKEN=xoxp-xxxxxxx
```

`check_slack_mentions.py` 内の `MY_USER_ID` を自分の Slack User ID に変更してください。

## スケジューリング方法（3択）

### 1. cron（最もシンプル）

```bash
crontab -e
```

以下を追加:

```
0 8-19 * * * SLACK_BOT_TOKEN=xoxp-... /path/to/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1
```

### 2. systemd timer（Linux サーバー向け）

```bash
# トークンファイルを作成
echo "SLACK_BOT_TOKEN=xoxp-..." | sudo tee /etc/slack-reminder.env
sudo chmod 600 /etc/slack-reminder.env

# サービス・タイマーをインストール
sudo cp slack-reminder.service slack-reminder.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now slack-reminder.timer

# 状態確認
sudo systemctl list-timers slack-reminder.timer
```

### 3. デーモンスクリプト（systemd 不要）

```bash
SLACK_BOT_TOKEN=xoxp-... nohup bash slack_reminder_daemon.sh >> /tmp/slack_reminder.log 2>&1 &
```

## 設定値

| 変数 | デフォルト | 説明 |
|---|---|---|
| `MY_USER_ID` | `U0973MEH3V0` | 自分の Slack User ID |
| `THRESHOLD_SEC` | `3600`（1時間） | この時間以上経過した未対応メンションをリマインド対象とする |
| `LOOKBACK_SEC` | `86400`（24時間） | 何時間前まで遡ってスキャンするか |
| `ACTIVE_HOURS` | `range(8, 20)` | 実行する時間帯（8〜19時） |
