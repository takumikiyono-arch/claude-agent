#!/usr/bin/env bash
# slack_reminder_daemon.sh
# 8:00〜19:00 の間、毎時0分に check_slack_mentions.py を実行するデーモン。
# バックグラウンド起動例:
#   SLACK_BOT_TOKEN=xoxp-... nohup bash slack_reminder_daemon.sh >> /tmp/slack_reminder.log 2>&1 &

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    exit 1
fi

if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "[INFO] Slack リマインドデーモン起動 (PID $$)"

while true; do
    HOUR=$(date +%H | sed 's/^0//')   # 先頭0を除去して数値化
    MINUTE=$(date +%M)

    # 8〜19時の間かつ毎時0分±1分に実行
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -le 19 ] && [ "$MINUTE" -eq 0 ]; then
        echo "[INFO] $(date '+%Y-%m-%d %H:%M') — チェック開始"
        python3 "$SCRIPT_DIR/check_slack_mentions.py" || true
        # 二重実行防止のため70秒待機
        sleep 70
    fi

    # 次の0分まで待つ（最大60秒ポーリング）
    sleep 30
done
