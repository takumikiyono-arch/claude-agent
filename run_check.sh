#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# 使い方:
#   SLACK_BOT_TOKEN=xoxp-... をセットするか、SCRIPT_DIR/.env に記載
#   bash run_check.sh
#
# cron 設定例 (crontab -e):
#   0 8-19 * * * /home/user/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルがあれば読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。.env ファイルか環境変数で設定してください。" >&2
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
