#!/usr/bin/env python3
"""
Slack 送信メッセージ 未返信リマインダー
--------------------------------------
自分 (MY_USER_ID) がチャンネルや DM に送ったメッセージのうち、
THRESHOLD_SEC (1日) 以上返信がないものを検索し、
未対応があれば自分自身に Slack DM でリマインドを送る。

対象:
  - チャンネルのトップレベル投稿 → スレッドに自分以外の返信が 0 件
  - DM / グループDM       → 自分の最後のメッセージ以降に相手の返信が 0 件
"""

import os
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID    = "U0973MEH3V0"
THRESHOLD_SEC = 24 * 60 * 60       # 1 日
LOOKBACK_SEC  = 7 * 24 * 60 * 60   # 過去 7 日間をスキャン
ACTIVE_HOURS  = range(8, 20)       # 8:00〜19:59 のみ実行
# ─────────────────────────────────────────────────────────────────────────────

client = WebClient(token=SLACK_TOKEN)


def get_dm_channel(user_id: str) -> str:
    resp = client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM sent.")


def has_others_replied_in_thread(channel: str, thread_ts: str) -> bool:
    """スレッド内に自分以外の返信があれば True を返す"""
    try:
        for page in client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:
                    continue  # 親メッセージ自体はスキップ
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def find_unanswered_channel_messages(now_ts: float) -> list[dict]:
    """
    参加チャンネルで自分が送ったトップレベルメッセージのうち、
    THRESHOLD_SEC 以上スレッド返信 (他者) がないものを返す。
    """
    cutoff  = now_ts - THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_SEC
    results = []

    channels = []
    try:
        for page in client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")

    print(f"[INFO] チャンネル {len(channels)} 件をスキャン中 (送信メッセージ)...")

    for ch in channels:
        ch_id   = ch["id"]
        ch_name = ch.get("name", ch_id)
        try:
            for page in client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # 自分のメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue
                    # スレッド返信はスキップ（トップレベルのみ）
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:
                        continue  # まだ猶予期間内

                    # スレッドに他者の返信があれば対応済み
                    if has_others_replied_in_thread(ch_id, msg["ts"]):
                        continue

                    elapsed  = int((now_ts - msg_ts) / 3600)
                    msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    results.append({
                        "type":         "channel",
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "text":         msg.get("text", "")[:120],
                        "elapsed_h":    elapsed,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                    })

        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for #{ch_name}: {e}")

    return results


def find_unanswered_dm_messages(now_ts: float) -> list[dict]:
    """
    DM / グループDM で自分の最後のメッセージ以降に
    THRESHOLD_SEC 以上相手からの返信がないものを返す。
    """
    cutoff  = now_ts - THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_SEC
    results = []

    dms = []
    try:
        for page in client.conversations_list(
            types="im,mpim",
            exclude_archived=True,
        ):
            dms.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list (im) failed: {e}")

    print(f"[INFO] DM会話 {len(dms)} 件をスキャン中 (送信メッセージ)...")

    for dm in dms:
        dm_id = dm["id"]
        # 自分自身との DM はスキップ
        if dm.get("user") == MY_USER_ID:
            continue

        messages = []
        try:
            for page in client.conversations_history(
                channel=dm_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                messages.extend(page["messages"])
        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for DM {dm_id}: {e}")
            continue

        if not messages:
            continue

        # 古い順に並べ替え
        messages.sort(key=lambda m: float(m["ts"]))

        # 自分の最後のメッセージを探す
        last_my_msg = None
        for msg in reversed(messages):
            if msg.get("user") == MY_USER_ID:
                last_my_msg = msg
                break

        if last_my_msg is None:
            continue

        last_my_ts = float(last_my_msg["ts"])
        if last_my_ts > cutoff:
            continue  # まだ猶予期間内

        # 自分の最後のメッセージ以降に相手の返信があるか
        replied = any(
            msg.get("user") != MY_USER_ID and float(msg["ts"]) > last_my_ts
            for msg in messages
        )
        if replied:
            continue

        elapsed   = int((now_ts - last_my_ts) / 3600)
        msg_time  = datetime.fromtimestamp(last_my_ts, tz=timezone.utc)
        other_user = dm.get("user", "unknown")

        results.append({
            "type":         "dm",
            "channel_id":   dm_id,
            "channel_name": f"DM with <@{other_user}>",
            "ts":           last_my_msg["ts"],
            "text":         last_my_msg.get("text", "")[:120],
            "elapsed_h":    elapsed,
            "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
        })

    return results


def build_reminder_text(items: list[dict]) -> str:
    lines = [
        f":mailbox_with_no_mail: *返信待ちの Slack メッセージが {len(items)} 件あります*（1日以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        link = (
            f"https://slack.com/archives/{item['channel_id']}/p{item['ts'].replace('.', '')}"
        )
        dest = f"<#{item['channel_id']}>" if item["type"] == "channel" else item["channel_name"]
        lines.append(
            f"*{i}.* {dest} – {item['msg_time_utc']}"
            f"（{item['elapsed_h']}時間以上前）\n"
            f"   内容: _{item['text']}…_\n"
            f"   {link}\n"
        )
    return "\n".join(lines)


def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時のみ）のためスキップ。")
        return

    print(f"[INFO] Slack送信メッセージチェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    unanswered = []
    unanswered.extend(find_unanswered_channel_messages(now_ts))
    unanswered.extend(find_unanswered_dm_messages(now_ts))

    if not unanswered:
        print("[INFO] 返信待ちの送信メッセージなし。リマインドは送りません。")
        return

    print(f"[INFO] {len(unanswered)} 件の返信待ちを検出。DMを送信します。")
    send_dm(build_reminder_text(unanswered))


if __name__ == "__main__":
    main()
