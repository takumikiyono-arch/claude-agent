#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
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

python3 "$SCRIPT_DIR/check_slack_mentions.py"
