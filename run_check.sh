#!/usr/bin/env bash
# run_check.sh — 毎時間 cron から呼び出すラッパー
# 使い方:
#   /home/user/.slack-reminder.env に SLACK_BOT_TOKEN=xoxp-... を書いておく
#   または環境変数で直接渡す: SLACK_BOT_TOKEN=xoxp-... bash run_check.sh
#
# cron 設定:
#   /etc/cron.d/slack-reminder で 0 8-19 * * * root ... として実行

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 固定パスの env ファイルがあればトークンを読み込む（root で実行される場合も対応）
ENV_FILE="/home/user/.slack-reminder.env"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/check_slack_mentions.py"
