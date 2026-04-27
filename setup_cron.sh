#!/usr/bin/env bash
# setup_cron.sh — cron ジョブを登録するセットアップスクリプト
# 実行: bash setup_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/slack_reminder.log"
CRON_CMD="0 * * * * $SCRIPT_DIR/run_check.sh >> $LOG_FILE 2>&1"
CRON_MARKER="# slack-mention-reminder"

if ! [ -f "$SCRIPT_DIR/.env" ]; then
    echo "[ERROR] .env ファイルが見つかりません。"
    echo "  cp $SCRIPT_DIR/.env.example $SCRIPT_DIR/.env"
    echo "  vi $SCRIPT_DIR/.env  # SLACK_BOT_TOKEN を設定"
    exit 1
fi

chmod +x "$SCRIPT_DIR/run_check.sh"

# 既存の cron に同じエントリがなければ追加
CURRENT_CRON=$(crontab -l 2>/dev/null || true)
if echo "$CURRENT_CRON" | grep -q "slack-mention-reminder"; then
    echo "[INFO] cron ジョブは既に登録済みです。"
else
    (echo "$CURRENT_CRON"; echo "$CRON_CMD $CRON_MARKER") | crontab -
    echo "[INFO] cron ジョブを登録しました:"
    echo "  $CRON_CMD"
fi

echo "[INFO] セットアップ完了。毎時0分に実行され、8〜19時の間のみDMを送信します。"
echo "[INFO] ログ: $LOG_FILE"
