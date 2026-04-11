#!/usr/bin/env bash
# slack_reminder_daemon.sh
# 8:00〜19:00 の間、毎時0分に check_slack_mentions.py を実行するデーモン。
#
# 起動方法:
#   1. /home/user/.slack-reminder.env に SLACK_BOT_TOKEN=xoxp-... を設定
#   2. nohup bash /home/user/claude-agent/slack_reminder_daemon.sh >> /tmp/slack_reminder.log 2>&1 &

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 固定パスの env ファイルがあればトークンを読み込む
ENV_FILE="/home/user/.slack-reminder.env"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "        /home/user/.slack-reminder.env に SLACK_BOT_TOKEN=xoxp-... を書いてください。"
    exit 1
fi

if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "[INFO] Slack リマインドデーモン起動 (PID $$)"

while true; do
    HOUR=$(date +%-H)   # 先頭0なしの時刻（例: 8, 19）
    MINUTE=$(date +%-M) # 先頭0なしの分

    # 8〜19時の間かつ毎時0分に実行
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -le 19 ] && [ "$MINUTE" -eq 0 ]; then
        echo "[INFO] $(date '+%Y-%m-%d %H:%M') — チェック開始"
        python3 "$SCRIPT_DIR/check_slack_mentions.py" || true
        # 二重実行防止のため70秒待機
        sleep 70
    fi

    # 30秒ごとにポーリング
    sleep 30
done
