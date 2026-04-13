#!/usr/bin/env bash
# start_reminder.sh
# Slack メンションリマインダーのデーモンを起動するセットアップスクリプト。
#
# 使い方:
#   bash start_reminder.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$HOME/.slack-reminder.env"
LOG_FILE="/tmp/slack_reminder.log"
PID_FILE="/tmp/slack_reminder.pid"

# ── 1. トークン確認 ────────────────────────────────────────────────────────────
if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    if [ -f "$ENV_FILE" ]; then
        # shellcheck disable=SC1090
        source "$ENV_FILE"
    fi
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "======================================================"
    echo "  SLACK_BOT_TOKEN が設定されていません"
    echo "======================================================"
    echo ""
    echo "以下の手順で設定してください:"
    echo ""
    echo "  1. ~/.slack-reminder.env ファイルを作成:"
    echo "     echo 'SLACK_BOT_TOKEN=xoxp-...' > ~/.slack-reminder.env"
    echo "     chmod 600 ~/.slack-reminder.env"
    echo ""
    echo "  2. このスクリプトを再実行:"
    echo "     bash $0"
    echo ""
    exit 1
fi

# ── 2. 既存デーモン確認 ────────────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[INFO] デーモンは既に起動中です (PID: $OLD_PID)"
        echo "       ログ: $LOG_FILE"
        exit 0
    else
        echo "[INFO] 古いPIDファイルを削除します (PID: $OLD_PID)"
        rm -f "$PID_FILE"
    fi
fi

# ── 3. デーモン起動 ────────────────────────────────────────────────────────────
export SLACK_BOT_TOKEN
nohup bash "$SCRIPT_DIR/slack_reminder_daemon.sh" >> "$LOG_FILE" 2>&1 &
DAEMON_PID=$!
echo "$DAEMON_PID" > "$PID_FILE"

echo "======================================================"
echo "  Slack リマインドデーモン起動完了"
echo "======================================================"
echo "  PID  : $DAEMON_PID"
echo "  ログ : $LOG_FILE"
echo "  動作 : 毎時0分 (8:00〜19:00)"
echo ""
echo "  停止するには:"
echo "    kill \$(cat $PID_FILE)"
echo ""
echo "  ログ確認:"
echo "    tail -f $LOG_FILE"
