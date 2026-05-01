#!/usr/bin/env bash
# run_awaiting_check.sh — 返信待ちリマインダーの実行ラッパー
#
# 必須環境変数:
#   SLACK_BOT_TOKEN   xoxp-... (ユーザートークン) または xoxb-... (ボットトークン)
#
# オプション環境変数:
#   GMAIL_TOKEN_PATH  token.json のパス（デフォルト: スクリプトと同じディレクトリの token.json）
#
# cron 設定例 (crontab -e):
#   0 * * * * SLACK_BOT_TOKEN=xoxp-... GMAIL_TOKEN_PATH=/path/to/token.json \
#             /path/to/claude-agent/run_awaiting_check.sh >> /var/log/awaiting_reminder.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# GMAIL_TOKEN_PATH のデフォルトをスクリプトと同じディレクトリに設定
export GMAIL_TOKEN_PATH="${GMAIL_TOKEN_PATH:-$SCRIPT_DIR/token.json}"

python3 "$SCRIPT_DIR/check_awaiting_replies.py"
