#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
#
# cron 設定例 (crontab -e):
#   0 * * * * SLACK_BOT_TOKEN=xoxp-... /path/to/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# ① Slack: 自分宛のメンションで未返信（1時間以上）
python3 "$SCRIPT_DIR/check_slack_mentions.py"

# ② Slack: 自分が送信したメッセージで返信待ち（1日以上）
python3 "$SCRIPT_DIR/check_slack_sent.py"

# ③ Gmail: 自分が送信したメールで返信待ち（3日以上）
#    ※ gmail_credentials.json または gmail_token.json が必要
if [ -f "$SCRIPT_DIR/gmail_credentials.json" ] || [ -f "$SCRIPT_DIR/gmail_token.json" ]; then
    python3 "$SCRIPT_DIR/check_gmail_sent.py"
else
    echo "[INFO] gmail_credentials.json が未設定のため Gmail チェックをスキップ。"
    echo "[INFO] セットアップ方法は check_gmail_sent.py の冒頭コメントを参照してください。"
fi
