#!/usr/bin/env bash
# run_check.sh — 毎時間 /etc/cron.d/slack-reminder から呼び出すラッパー

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env からトークンを読み込む（環境変数が未設定の場合のみ）
if [ -z "${SLACK_BOT_TOKEN:-}" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    # shellcheck disable=SC1090
    set -a; source "$SCRIPT_DIR/.env"; set +a
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。.env ファイルを確認してください。" >&2
    exit 1
fi

# 仮想環境を有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
