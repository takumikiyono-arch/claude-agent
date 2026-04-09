#!/usr/bin/env python3
"""
Slack Sent-Message Reminder
-----------------------------
自分(MY_USER_ID)が送信したメッセージのうち、1日以上返信がないものを検索し、
自分自身に Slack DM でリマインドを送る。

対象:
  - チャンネル投稿: スレッド返信が1件もない自分の投稿
  - DM: 自分が最後に送ったまま1日以上返信がないDM

環境変数:
  SLACK_BOT_TOKEN  xoxp-... (User Token) — channels.history / im.history 権限が必要
"""

import os
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN   = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID    = "U0973MEH3V0"
THRESHOLD_SEC = 24 * 60 * 60     # 1日 = 86400 秒
LOOKBACK_SEC  = 7 * 24 * 60 * 60 # 過去7日分をスキャン
# ─────────────────────────────────────────────────────────────────────────────

client = WebClient(token=SLACK_TOKEN)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def get_dm_channel(user_id: str) -> str:
    resp = client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def has_reply_from_others(channel: str, thread_ts: str) -> bool:
    """スレッドに自分以外のユーザーの返信があれば True を返す。"""
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


def fetch_joined_channels() -> list[dict]:
    channels: list[dict] = []
    try:
        for page in client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")
    return channels


def fetch_dm_conversations() -> list[dict]:
    dms: list[dict] = []
    try:
        for page in client.conversations_list(types="im"):
            dms.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list (im) failed: {e}")
    return dms


# ── チャンネル投稿チェック ─────────────────────────────────────────────────────

def find_unanswered_channel_messages(now_ts: float) -> list[dict]:
    """
    チャンネルで自分が送ったトップレベルメッセージのうち、
    1日以上スレッド返信がないものを返す。
    """
    cutoff = now_ts - THRESHOLD_SEC
    oldest = now_ts - LOOKBACK_SEC
    results: list[dict] = []

    channels = fetch_joined_channels()
    print(f"[INFO] チャンネル {len(channels)} 件をスキャン中...")

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
                    # スレッド返信（親ではないもの）はスキップ
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue
                    # 自分が送ったメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:
                        continue  # まだ1日経っていない

                    # 他者からの返信があればスキップ
                    if has_reply_from_others(ch_id, msg["ts"]):
                        continue

                    text     = msg.get("text", "")
                    msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    elapsed  = int((now_ts - msg_ts) / 3600)

                    results.append({
                        "kind":         "channel",
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "text":         text[:120],
                        "elapsed_h":    elapsed,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                    })
        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for #{ch_name}: {e}")

    return results


# ── DM チェック ───────────────────────────────────────────────────────────────

def find_unanswered_dms(now_ts: float) -> list[dict]:
    """
    DM 会話で自分が最後にメッセージを送ったまま1日以上返信がないものを返す。
    """
    cutoff  = now_ts - THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_SEC
    results: list[dict] = []

    dms = fetch_dm_conversations()
    print(f"[INFO] DM {len(dms)} 件をスキャン中...")

    for dm in dms:
        dm_id   = dm["id"]
        partner = dm.get("user", "")
        if partner == MY_USER_ID:
            continue  # 自分へのDMはスキップ

        try:
            resp     = client.conversations_history(
                channel=dm_id,
                oldest=str(oldest),
                latest=str(now_ts),
                limit=20,
            )
            messages = resp.get("messages", [])
            if not messages:
                continue

            # conversations_history は新しい順に返す
            last_msg = messages[0]
            if last_msg.get("user") != MY_USER_ID:
                continue  # 相手が最後に返信済み

            msg_ts = float(last_msg["ts"])
            if msg_ts > cutoff:
                continue  # まだ1日経っていない

            text     = last_msg.get("text", "")
            msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
            elapsed  = int((now_ts - msg_ts) / 3600)

            results.append({
                "kind":         "dm",
                "channel_id":   dm_id,
                "dm_partner":   partner,
                "ts":           last_msg["ts"],
                "text":         text[:120],
                "elapsed_h":    elapsed,
                "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
            })
        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for DM {dm_id}: {e}")

    return results


# ── DM 送信 ───────────────────────────────────────────────────────────────────

def build_reminder_text(ch_items: list[dict], dm_items: list[dict]) -> str:
    total = len(ch_items) + len(dm_items)
    lines = [
        f":hourglass_flowing_sand: *返信待ちのSlackメッセージが {total} 件あります*（1日以上経過）\n"
    ]

    if ch_items:
        lines.append("*チャンネル投稿:*")
        for i, item in enumerate(ch_items, 1):
            link = (
                f"https://slack.com/archives/{item['channel_id']}"
                f"/p{item['ts'].replace('.', '')}"
            )
            lines.append(
                f"*{i}.* <#{item['channel_id']}> – {item['msg_time_utc']}"
                f"（{item['elapsed_h']}時間以上前）\n"
                f"   内容: _{item['text'][:80]}_\n"
                f"   {link}\n"
            )

    if dm_items:
        lines.append("*DM:*")
        for i, item in enumerate(dm_items, 1):
            link = (
                f"https://slack.com/archives/{item['channel_id']}"
                f"/p{item['ts'].replace('.', '')}"
            )
            lines.append(
                f"*{i}.* <@{item['dm_partner']}> へのDM – {item['msg_time_utc']}"
                f"（{item['elapsed_h']}時間以上前）\n"
                f"   内容: _{item['text'][:80]}_\n"
                f"   {link}\n"
            )

    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


# ── エントリーポイント ─────────────────────────────────────────────────────────

def main() -> None:
    now_ts   = time.time()
    ch_items = find_unanswered_channel_messages(now_ts)
    dm_items = find_unanswered_dms(now_ts)
    total    = len(ch_items) + len(dm_items)

    if total == 0:
        print("[INFO] 未返信の送信済みSlackメッセージなし。")
        return

    print(
        f"[INFO] {total} 件の未返信メッセージを検出"
        f"（チャンネル:{len(ch_items)}, DM:{len(dm_items)}）。DMを送信します。"
    )
    send_dm(build_reminder_text(ch_items, dm_items))


if __name__ == "__main__":
    main()
