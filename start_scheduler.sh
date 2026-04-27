#!/usr/bin/env bash
# start_scheduler.sh — スケジューラーをバックグラウンドで起動する
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/scheduler.pid"
LOG_FILE="$SCRIPT_DIR/scheduler.log"

# 既に起動中かチェック
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[INFO] スケジューラーは既に起動中です (PID $PID)"
        exit 0
    else
        echo "[WARN] 古いPIDファイルを削除します"
        rm -f "$PID_FILE"
    fi
fi

# .env が存在するかチェック
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "[ERROR] .env ファイルが見つかりません。"
    echo "        $SCRIPT_DIR/.env を作成して SLACK_BOT_TOKEN=xoxp-... を記載してください。"
    exit 1
fi

PYTHON="$SCRIPT_DIR/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="$(which python3)"
fi

nohup "$PYTHON" "$SCRIPT_DIR/reminder_scheduler.py" >> "$LOG_FILE" 2>&1 &
echo "[INFO] スケジューラー起動完了 (PID $!)"
echo "[INFO] ログ: $LOG_FILE"
