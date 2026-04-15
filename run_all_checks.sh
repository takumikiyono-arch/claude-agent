#!/usr/bin/env bash
# run_all_checks.sh — 全リマインドチェックをまとめて実行するラッパー
#
# 実行する処理:
#   1. Slack メンション未返信チェック (check_slack_mentions.py)
#   2. Slack 送信メッセージ未返信チェック (check_slack_sent.py)   ← 1日閾値
#   3. Gmail 送信メール未返信チェック    (check_gmail_sent.py)    ← 3日閾値
#
# 必須環境変数:
#   SLACK_BOT_TOKEN          Slack API トークン (xoxp-... or xoxb-...)
#
# Gmail 用環境変数 (オプション):
#   GOOGLE_CREDENTIALS_PATH  credentials.json のパス (デフォルト: credentials.json)
#   GOOGLE_TOKEN_PATH        token.json のパス        (デフォルト: token.json)
#
# 使い方:
#   export SLACK_BOT_TOKEN=xoxp-...
#   export GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
#   bash run_all_checks.sh
#
# cron 設定例 (crontab -e) — 毎時 0 分に実行:
#   0 * * * * SLACK_BOT_TOKEN=xoxp-... GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json /path/to/claude-agent/run_all_checks.sh >> /var/log/reminder_checks.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 仮想環境があれば有効化
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "========================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 全リマインドチェック開始"
echo "========================================"

echo ""
echo "--- [1/3] Slack メンション未返信チェック ---"
python3 "$SCRIPT_DIR/check_slack_mentions.py" || echo "[WARN] check_slack_mentions.py が異常終了しました"

echo ""
echo "--- [2/3] Slack 送信メッセージ未返信チェック (1日) ---"
python3 "$SCRIPT_DIR/check_slack_sent.py" || echo "[WARN] check_slack_sent.py が異常終了しました"

echo ""
echo "--- [3/3] Gmail 送信メール未返信チェック (3日) ---"
python3 "$SCRIPT_DIR/check_gmail_sent.py" || echo "[WARN] check_gmail_sent.py が異常終了しました"

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 全チェック完了"
