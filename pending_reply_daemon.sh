#!/usr/bin/env bash
# pending_reply_daemon.sh
# 8:00〜19:00 の間、毎時0分に check_pending_replies.py を実行するデーモン。
#
# バックグラウンド起動例:
#   SLACK_BOT_TOKEN=xoxp-... \
#   GMAIL_MY_EMAIL=you@gmail.com \
#   nohup bash pending_reply_daemon.sh >> /tmp/pending_reply.log 2>&1 &

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    exit 1
fi

if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "[INFO] 未返信リマインドデーモン起動 (PID $$)"

while true; do
    HOUR=$(date +%-H)   # 先頭0なしの時
    MINUTE=$(date +%M)

    # 8〜19時の間かつ毎時0分±1分に実行
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -le 19 ] && [ "$MINUTE" -eq 0 ]; then
        echo "[INFO] $(date '+%Y-%m-%d %H:%M') — チェック開始"
        python3 "$SCRIPT_DIR/check_pending_replies.py" || true
        # 二重実行防止のため70秒待機
        sleep 70
    fi

    sleep 30
done
