#!/bin/bash
# Slack メンションリマインダー cron 設定スクリプト
#
# 使い方:
#   export SLACK_USER_TOKEN="xoxp-your-token-here"
#   bash setup_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/slack_mention_reminder.py"
LOG_PATH="$SCRIPT_DIR/reminder.log"
ENV_FILE="$SCRIPT_DIR/.env"

# トークンチェック
if [ -z "$SLACK_USER_TOKEN" ]; then
    echo "Error: SLACK_USER_TOKEN 環境変数を設定してください"
    echo "  export SLACK_USER_TOKEN='xoxp-...'"
    exit 1
fi

# .env ファイルにトークンを保存
cat > "$ENV_FILE" <<EOF
SLACK_USER_TOKEN=$SLACK_USER_TOKEN
EOF
chmod 600 "$ENV_FILE"
echo "トークンを $ENV_FILE に保存しました"

# Python 依存パッケージのインストール
pip install -q -r "$SCRIPT_DIR/requirements.txt"

# 既存のcronエントリを削除してから追加
CRON_COMMENT="# slack-mention-reminder"
CRON_JOB="0 8-19 * * * . $ENV_FILE && python3 $SCRIPT_PATH >> $LOG_PATH 2>&1"

(crontab -l 2>/dev/null | grep -v "slack-mention-reminder" | grep -v "$SCRIPT_PATH"; \
 echo "$CRON_COMMENT"; \
 echo "$CRON_JOB") | crontab -

echo ""
echo "cron 設定完了:"
crontab -l | grep -A1 "slack-mention-reminder"
echo ""
echo "毎時0分 (8:00〜19:00) にリマインドが実行されます"
echo "ログ: $LOG_PATH"
echo ""
echo "動作テスト:"
echo "  python3 $SCRIPT_PATH"
