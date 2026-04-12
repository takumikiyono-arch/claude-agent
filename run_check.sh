#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
#
# トークン設定ファイル: ~/.slack_reminder_env
#   SLACK_BOT_TOKEN=xoxp-xxxxxxxxxxxx-...
#
# cron 設定 (自動設定済み):
#   0 8-19 * * * /home/user/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HOME}/.slack_reminder_env"

# トークン設定ファイルを読み込む
if [ -f "$ENV_FILE" ]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "        ${ENV_FILE} に以下の内容を記載してください:"
    echo "        SLACK_BOT_TOKEN=xoxp-xxxxxxxxxxxx-..."
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
