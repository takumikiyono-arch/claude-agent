#!/usr/bin/env bash
# start.sh — Slack リマインドデーモンを起動する
# 使い方:
#   bash start.sh          # .env からトークンを読み込んで起動
#   SLACK_BOT_TOKEN=xoxp-... bash start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGFILE="/tmp/slack_reminder.log"
PIDFILE="/tmp/slack_reminder.pid"

# .env ファイルがあれば読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +o allexport
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "  .env.template を .env にコピーしてトークンを設定してください:"
    echo "    cp $SCRIPT_DIR/.env.template $SCRIPT_DIR/.env"
    echo "    vi $SCRIPT_DIR/.env"
    exit 1
fi

# 既存デーモンの確認
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[INFO] デーモンはすでに起動中です (PID $(cat "$PIDFILE"))。"
    exit 0
fi

export SLACK_BOT_TOKEN

echo "[INFO] デーモンをバックグラウンドで起動します... (ログ: $LOGFILE)"
nohup bash "$SCRIPT_DIR/slack_reminder_daemon.sh" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "[INFO] 起動完了 (PID $(cat "$PIDFILE"))"
echo "[INFO] ログ確認: tail -f $LOGFILE"
echo "[INFO] 停止するには: kill $(cat "$PIDFILE")"
