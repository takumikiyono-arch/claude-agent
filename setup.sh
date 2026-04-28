#!/usr/bin/env bash
# setup.sh — 初回セットアップ用スクリプト
# 使い方:
#   SLACK_BOT_TOKEN=xoxp-xxxx bash setup.sh
#
# 実行後は毎時0分（8:00〜19:00）に check_slack_mentions.py が自動起動します。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN を設定してください。"
    echo "  例: SLACK_BOT_TOKEN=xoxp-... bash setup.sh"
    exit 1
fi

echo "==> 仮想環境を作成..."
python3 -m venv "$SCRIPT_DIR/.venv"
source "$SCRIPT_DIR/.venv/bin/activate"

echo "==> 依存パッケージをインストール..."
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

echo "==> cron ジョブを設定..."
CRON_LINE="0 8-19 * * * SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN} ${SCRIPT_DIR}/run_check.sh >> /tmp/slack_reminder.log 2>&1"

# 既存エントリがあれば削除して再登録
(crontab -l 2>/dev/null | grep -v "slack_reminder\|check_slack_mentions\|run_check.sh") | crontab -
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

echo ""
echo "[OK] セットアップ完了！"
echo "  毎時0分（8:00〜19:00）に未返信メンションをチェックし、あればDMを送ります。"
echo ""
echo "  ログ確認: tail -f /tmp/slack_reminder.log"
echo "  手動テスト: SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN} bash ${SCRIPT_DIR}/run_check.sh"
