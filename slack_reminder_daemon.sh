#!/usr/bin/env bash
# slack_reminder_daemon.sh
# 8:00〜19:00 の間、毎時0分に Slack メンションチェックを実行するデーモン。
# バックグラウンド起動例:
#   nohup bash /home/user/claude-agent/slack_reminder_daemon.sh >> /tmp/slack_reminder.log 2>&1 &

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[INFO] Slack リマインドデーモン起動 (PID $$)"

while true; do
    HOUR=$(date +%-H)   # 先頭ゼロなし (0-23)
    MINUTE=$(date +%-M)

    # 8〜19時の間かつ毎時0分に実行
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -le 19 ] && [ "$MINUTE" -eq 0 ]; then
        echo "[INFO] $(date '+%Y-%m-%d %H:%M') — チェック開始"
        bash "$SCRIPT_DIR/run_check.sh" || true
        # 二重実行防止のため70秒待機してから次のポーリングへ
        sleep 70
    fi

    # 30秒ごとに時刻をチェック
    sleep 30
done
