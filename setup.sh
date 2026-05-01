#!/usr/bin/env bash
# setup.sh — Slack メンションリマインダーの初期セットアップ
# 実行前に SLACK_BOT_TOKEN を環境変数にセットしてください
# 例: export SLACK_BOT_TOKEN=xoxp-xxxx
# 実行: sudo bash setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
    echo "[ERROR] SLACK_BOT_TOKEN が設定されていません。"
    echo "  export SLACK_BOT_TOKEN=xoxp-... を実行してから再度お試しください。"
    exit 1
fi

# 1. Python 依存パッケージのインストール
echo "[INFO] Python パッケージをインストール中..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" -q

# 2. 環境変数ファイルを /etc に配置（systemd 用）
echo "[INFO] 環境変数ファイルを /etc/slack-reminder.env に書き込み中..."
cat > /etc/slack-reminder.env <<EOF
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
EOF
chmod 600 /etc/slack-reminder.env

# 3. systemd ユニットファイルをコピー
echo "[INFO] systemd ユニットファイルをコピー中..."
cp "$SCRIPT_DIR/slack-reminder.service" /etc/systemd/system/
cp "$SCRIPT_DIR/slack-reminder.timer"   /etc/systemd/system/

# 4. systemd をリロードしてタイマーを有効化・起動
echo "[INFO] systemd タイマーを有効化・起動中..."
systemctl daemon-reload
systemctl enable --now slack-reminder.timer

echo ""
echo "=== セットアップ完了 ==="
echo "タイマー状態: $(systemctl is-active slack-reminder.timer)"
echo ""
echo "動作確認:"
echo "  systemctl status slack-reminder.timer   # タイマー状態"
echo "  systemctl list-timers slack-reminder*   # 次回実行時刻"
echo "  journalctl -u slack-reminder.service -f # ログ確認"
echo ""
echo "即時テスト実行:"
echo "  SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN} python3 $SCRIPT_DIR/check_slack_mentions.py"
