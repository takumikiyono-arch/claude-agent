#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# セットアップ:
#   1. slack_token.conf に SLACK_BOT_TOKEN を記入
#   2. crontab -e で以下を追加:
#      0 8-19 * * * /home/user/claude-agent/run_check.sh >> /var/log/slack_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# トークン設定ファイルを読み込む（環境変数未設定の場合）
if [ -z "${SLACK_BOT_TOKEN:-}" ] && [ -f "$SCRIPT_DIR/slack_token.conf" ]; then
    # コメント行・空行を除外して source
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$SCRIPT_DIR/slack_token.conf" | grep -v '^\s*$')
    set +a
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。slack_token.conf を確認してください。" >&2
    exit 1
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
