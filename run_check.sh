#!/usr/bin/env bash
# run_check.sh — 毎時間 cron / systemd から呼び出すラッパー
#
# 実行するスクリプト:
#   1. check_slack_mentions.py    : 自分宛メンションの未返信リマインド
#   2. check_awaiting_replies.py  : 自分が送ったSlack(1日)/Gmail(3日)の未返信リマインド
#
# 使い方:
#   export SLACK_BOT_TOKEN=xoxp-...
#   export GMAIL_TOKEN_FILE=/path/to/token.json          # 省略可（デフォルト: token.json）
#   export GMAIL_CREDENTIALS_FILE=/path/to/credentials.json  # 省略可
#   bash run_check.sh
#
# cron 設定例 (crontab -e):
#   0 8-19 * * 1-5 SLACK_BOT_TOKEN=xoxp-... bash /path/to/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "=== check_slack_mentions ($(date '+%Y-%m-%d %H:%M')) ==="
python3 "$SCRIPT_DIR/check_slack_mentions.py"

echo "=== check_awaiting_replies ($(date '+%Y-%m-%d %H:%M')) ==="
python3 "$SCRIPT_DIR/check_awaiting_replies.py"
