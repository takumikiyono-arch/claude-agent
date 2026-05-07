#!/usr/bin/env bash
# run_check.sh — cron / 手動実行ラッパー
#
# 実行する 2 つのチェック:
#   1. check_slack_mentions.py    — 自分宛メンションへの未返信 (1時間以上)
#   2. check_pending_replies.py   — 自分の送信メッセージへの未返信
#                                   Slack: 1日以上 / Gmail: 3日以上
#
# 使い方:
#   export SLACK_BOT_TOKEN=xoxp-...
#   bash run_check.sh
#
# cron 設定例 (crontab -e):
#   0 * * * * SLACK_BOT_TOKEN=xoxp-... /path/to/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "=== [1/2] Slack メンション未返信チェック ==="
python3 "$SCRIPT_DIR/check_slack_mentions.py"

echo "=== [2/2] 送信メッセージ・メール未返信チェック ==="
python3 "$SCRIPT_DIR/check_pending_replies.py"
