#!/usr/bin/env bash
# install.sh — Slack メンションリマインダーのセットアップスクリプト
# 使用前に SLACK_BOT_TOKEN を設定してください。
# 必要な Slack スコープ:
#   channels:history, groups:history, im:history, mpim:history
#   channels:read, groups:read
#   reactions:read
#   im:write (DM送信用)
#   users:read (オプション)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Slack Mention Reminder セットアップ ==="

# 1. Python 依存ライブラリのインストール
echo "[1/3] Python ライブラリをインストール中..."
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    python3 -m venv "$SCRIPT_DIR/.venv"
fi
source "$SCRIPT_DIR/.venv/bin/activate"
pip install -q -r "$SCRIPT_DIR/requirements.txt"
echo "      完了"

# ── systemd が使える場合（Linux サーバー向け） ──────────────────────────────
if command -v systemctl &>/dev/null && [ "${USE_SYSTEMD:-1}" = "1" ]; then
    echo "[2/3] systemd timer を設定中..."

    # SLACK_BOT_TOKEN の確認
    if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
        echo "      [ERROR] SLACK_BOT_TOKEN が設定されていません。"
        echo "      export SLACK_BOT_TOKEN=xoxp-... を実行してから再試行してください。"
        exit 1
    fi

    # 環境変数ファイルを /etc/ に配置（root 権限が必要）
    echo "SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}" | sudo tee /etc/slack-reminder.env > /dev/null
    sudo chmod 600 /etc/slack-reminder.env

    # サービス・タイマーファイルをコピーして有効化
    sudo cp "$SCRIPT_DIR/slack-reminder.service" /etc/systemd/system/
    sudo cp "$SCRIPT_DIR/slack-reminder.timer"   /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now slack-reminder.timer
    echo "      完了 — タイマーが有効になりました。"
    echo "      確認: systemctl status slack-reminder.timer"

# ── systemd が使えない場合はデーモンスクリプトで代替 ────────────────────────
else
    echo "[2/3] バックグラウンドデーモンを起動中..."
    if [ -z "${SLACK_BOT_TOKEN:-}" ]; then
        echo "      [ERROR] SLACK_BOT_TOKEN が設定されていません。"
        exit 1
    fi
    export SLACK_BOT_TOKEN
    nohup bash "$SCRIPT_DIR/slack_reminder_daemon.sh" \
        >> /tmp/slack_reminder.log 2>&1 &
    echo "      PID $! でデーモンを起動しました。"
    echo "      ログ: tail -f /tmp/slack_reminder.log"
fi

echo "[3/3] セットアップ完了！"
echo "      毎時0分（8:00〜19:00）に未返信メンションをチェックし、"
echo "      未対応のものがあれば Slack DM でお知らせします。"
