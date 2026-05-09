#!/usr/bin/env bash
# run_check.sh — 毎時間 systemd timer / cron から呼び出すラッパー
#
# 実行する2つのチェック:
#   1. check_slack_mentions.py   — 自分宛メンションへの未返信リマインド
#   2. check_unanswered_sent.py  — 自分が送ったSlack/Gmailへの未返信リマインド
#
# 使い方（cron例）:
#   0 * * * * SLACK_BOT_TOKEN=xoxp-... /path/to/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="

echo "--- [1/2] Slack メンション未返信チェック ---"
python3 "$SCRIPT_DIR/check_slack_mentions.py"

echo "--- [2/2] 送信済みSlack/Gmail 未返信チェック ---"
python3 "$SCRIPT_DIR/check_unanswered_sent.py"
