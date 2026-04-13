#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# 使い方:
#   export SLACK_BOT_TOKEN=xoxp-...
#   bash run_check.sh
#
# cron 設定例 (crontab -e):
#   0 8-19 * * * /path/to/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルがあれば読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +o allexport
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
