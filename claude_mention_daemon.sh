#!/usr/bin/env bash
# claude_mention_daemon.sh
# JST 8:00〜19:00 の間、毎時0分に claude CLI を使って
# 未返信メンションをチェックし、あればDMでリマインドを送るデーモン。
#
# 起動方法:
#   nohup bash /home/user/claude-agent/claude_mention_daemon.sh >> /tmp/claude_mention_daemon.log 2>&1 &
#   echo $! > /tmp/claude_mention_daemon.pid

set -euo pipefail

CLAUDE_BIN="/opt/node22/bin/claude"
WORK_DIR="/home/user/claude-agent"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S JST')]"

echo "$LOG_PREFIX Slack リマインドデーモン起動 (PID $$)"

run_check() {
    local hour_jst
    hour_jst=$(TZ=Asia/Tokyo date +%H | sed 's/^0*//' || echo "0")

    # 8〜19時以外はスキップ
    if [ "${hour_jst:-0}" -lt 8 ] || [ "${hour_jst:-0}" -ge 20 ]; then
        echo "$LOG_PREFIX JST ${hour_jst}時 — 実行時間外のためスキップ"
        return
    fi

    echo "$LOG_PREFIX JST ${hour_jst}時 — メンションチェック開始"

    local today
    today=$(TZ=Asia/Tokyo date '+%Y-%m-%d')
    local week_ago
    week_ago=$(TZ=Asia/Tokyo date -d '7 days ago' '+%Y-%m-%d' 2>/dev/null || TZ=Asia/Tokyo date -v-7d '+%Y-%m-%d' 2>/dev/null || echo "")

    local PROMPT
    PROMPT="以下の手順でSlackの未返信メンションをチェックしてください。

現在のJST時刻: $(TZ=Asia/Tokyo date '+%Y-%m-%d %H:%M JST')

手順:
1. Slack検索で自分(U0973MEH3V0)宛のメンション(to:me after:${week_ago:-2026-04-09})を取得する
2. 各メッセージについて、コンテキストを見て自分(U0973MEH3V0)が返信またはリアクションしているか確認する
3. ボット(Make, Google Calendar, セキュリオ等)からのメッセージは除外する
4. 未返信・未スタンプのメンションがあれば、自分のDM(チャンネルID: U0973MEH3V0)に以下の形式でリマインドを送る:
   「⏰ 未返信のメンションがあります！
   以下のメッセージに返信またはスタンプがありません:
   - [送信者名]: [メッセージ概要] [パーマリンク]」
5. 未返信がなければ何も送らずに終了する。

重要: DMの送信先はU0973MEH3V0です。リマインドが不要な場合は何も送らないでください。"

    timeout 120 "$CLAUDE_BIN" -p "$PROMPT" --output-format text 2>&1 || {
        echo "$LOG_PREFIX [ERROR] claude CLI 実行エラー (exit: $?)"
    }

    echo "$LOG_PREFIX チェック完了"
}

LAST_RUN_HOUR=-1

while true; do
    CURRENT_MIN=$(date +%M | sed 's/^0*//' || echo "0")
    CURRENT_HOUR_JST=$(TZ=Asia/Tokyo date +%H | sed 's/^0*//' || echo "0")

    # 毎時0分±2分に実行（二重実行防止）
    if [ "${CURRENT_MIN:-0}" -le 2 ] && [ "${CURRENT_HOUR_JST:-0}" != "${LAST_RUN_HOUR}" ]; then
        LAST_RUN_HOUR="${CURRENT_HOUR_JST:-0}"
        run_check
        sleep 120  # 2分待機して二重実行防止
    fi

    sleep 30
done
