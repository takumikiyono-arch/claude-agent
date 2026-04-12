#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# 使い方:
#   cp .env.template .env && vi .env  # SLACK_BOT_TOKEN を設定
#   bash run_check.sh
#
# cron 設定（自動セットアップ済み）:
#   0 * * * * /path/to/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1
# ※ 時刻判定はスクリプト側でJST 8:00〜19:59 にゲートしています

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルがあれば読み込む（SLACK_BOT_TOKEN を設定）
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
