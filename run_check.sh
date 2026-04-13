#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
#
# 初期設定:
#   1. cp /home/user/claude-agent/.env.example /home/user/claude-agent/.env
#   2. .env に SLACK_BOT_TOKEN=xoxp-... を記入
#   3. crontab に登録（下記コマンドを実行）:
#        (crontab -l 2>/dev/null; echo "0 8-19 * * * /home/user/claude-agent/run_check.sh >> /tmp/slack_reminder.log 2>&1") | crontab -

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルがあれば読み込む（cron 実行時に環境変数を補完）
if [ -f "$SCRIPT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。.env ファイルを確認してください。" >&2
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
