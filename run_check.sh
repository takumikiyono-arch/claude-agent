#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# 使い方:
#   1) ~/.slack-reminder.env に SLACK_BOT_TOKEN=xoxp-... を書く（推奨）
#   2) または export SLACK_BOT_TOKEN=xoxp-... してから bash run_check.sh
#
# cron 設定例 (crontab -e):
#   0 * * * * /path/to/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルが存在すれば読み込む
ENV_FILE="$HOME/.slack-reminder.env"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

# トークン未設定チェック
if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "        $ENV_FILE に 'SLACK_BOT_TOKEN=xoxp-...' を記載してください。"
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
