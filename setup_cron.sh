#!/usr/bin/env bash
# Slack メンションリマインダーの cron ジョブを登録するスクリプト
# 毎時0分、8〜19時の間に check_slack_mentions.py を実行する

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"
CRON_JOB="0 8-19 * * * SLACK_BOT_TOKEN=\"\${SLACK_BOT_TOKEN}\" $PYTHON $SCRIPT_DIR/check_slack_mentions.py >> $SCRIPT_DIR/slack_reminder.log 2>&1"

# 環境変数が設定されているか確認
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN 環境変数が設定されていません。"
    echo "  export SLACK_BOT_TOKEN=xoxp-... を実行してから再度このスクリプトを実行してください。"
    exit 1
fi

# 既存の同じジョブが登録されていれば削除してから追加
(crontab -l 2>/dev/null | grep -v "check_slack_mentions.py"; echo "0 8-19 * * * SLACK_BOT_TOKEN=\"$SLACK_BOT_TOKEN\" $PYTHON $SCRIPT_DIR/check_slack_mentions.py >> $SCRIPT_DIR/slack_reminder.log 2>&1") | crontab -

echo "[OK] cron ジョブを登録しました。"
echo "     スケジュール: 毎時0分（8:00〜19:00）"
echo ""
echo "現在の crontab:"
crontab -l
