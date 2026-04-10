#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
#
# SLACK_BOT_TOKEN の設定方法（どちらか一方）:
#   1) スクリプトと同じディレクトリに .env ファイルを作成:
#        echo "SLACK_BOT_TOKEN=xoxp-..." > /home/user/claude-agent/.env
#   2) cron で直接渡す:
#        0 8-19 * * * SLACK_BOT_TOKEN=xoxp-... /home/user/claude-agent/run_check.sh
#
# cron 設定例 (crontab -e):
#   0 8-19 * * * /home/user/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルが存在すれば読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    set -o allexport
    source "$SCRIPT_DIR/.env"
    set +o allexport
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "        $SCRIPT_DIR/.env に SLACK_BOT_TOKEN=xoxp-... を記載するか"
    echo "        環境変数で渡してください。"
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
