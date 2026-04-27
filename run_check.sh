#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# セットアップ:
#   1. cp .env.example .env && vi .env  # SLACK_BOT_TOKEN を設定
#   2. bash setup_cron.sh               # cron を登録

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env があれば読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
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
