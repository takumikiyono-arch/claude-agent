#!/usr/bin/env bash
# stop_scheduler.sh — スケジューラーを停止する
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/scheduler.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[INFO] PIDファイルが見つかりません。スケジューラーは停止中です。"
    exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "[INFO] スケジューラーを停止しました (PID $PID)"
    rm -f "$PID_FILE"
else
    echo "[INFO] プロセス $PID は既に停止しています"
    rm -f "$PID_FILE"
fi
