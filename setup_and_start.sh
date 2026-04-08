#!/usr/bin/env bash
# setup_and_start.sh — 仮想環境セットアップ＋デーモン起動
# 使い方:
#   SLACK_BOT_TOKEN=xoxp-... bash setup_and_start.sh
#   # または .env に設定後
#   bash setup_and_start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env からトークンを読み込む
if [ -z "${SLACK_BOT_TOKEN:-}" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ] || [ "$SLACK_BOT_TOKEN" = "xoxp-YOUR-TOKEN-HERE" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "  1. .env ファイルを編集して SLACK_BOT_TOKEN を設定するか"
    echo "  2. SLACK_BOT_TOKEN=xoxp-... bash setup_and_start.sh として実行してください。"
    exit 1
fi

# 仮想環境セットアップ
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[INFO] 仮想環境を作成します..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi
"$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
echo "[INFO] 依存パッケージ OK"

# 既存デーモンが動いていれば停止
if [ -f /tmp/slack_reminder.pid ]; then
    OLD_PID=$(cat /tmp/slack_reminder.pid)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[INFO] 既存デーモン (PID $OLD_PID) を停止します..."
        kill "$OLD_PID"
    fi
    rm -f /tmp/slack_reminder.pid
fi

# デーモン起動
export SLACK_BOT_TOKEN
nohup bash "$SCRIPT_DIR/slack_reminder_daemon.sh" >> /tmp/slack_reminder.log 2>&1 &
echo $! > /tmp/slack_reminder.pid
echo "[INFO] デーモン起動完了 (PID $(cat /tmp/slack_reminder.pid))"
echo "[INFO] ログ: tail -f /tmp/slack_reminder.log"
