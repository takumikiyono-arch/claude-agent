#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
#
# 初回セットアップ:
#   cp .env.example .env
#   # .env に実際の SLACK_BOT_TOKEN を記入
#
# cron 設定 (crontab -e で追加):
#   0 8-19 * * * /home/user/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルからトークンを読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    export SLACK_BOT_TOKEN
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。.env ファイルを確認してください。"
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
