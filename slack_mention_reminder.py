#!/usr/bin/env python3
"""
Slack Mention Reminder
自分宛のメンションで未返信・未スタンプのものをDMでリマインドします。
8:00〜19:00の間、毎時間実行することを想定しています。

必要な環境変数:
  SLACK_USER_TOKEN  - ユーザートークン (xoxp-...) ※search:read, im:write, reactions:read, channels:history, groups:history スコープが必要
"""

import os
import sys
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def is_reminder_time():
    """8:00〜19:00の間かチェック"""
    hour = datetime.now().hour
    return 8 <= hour < 19


def get_my_user_id(client):
    result = client.auth_test()
    return result["user_id"]


def get_unresponded_mentions(client, user_id, lookback_hours=24):
    """未返信・未スタンプのメンションを取得"""
    unresponded = []
    cutoff_ts = (datetime.now() - timedelta(hours=lookback_hours)).timestamp()

    try:
        result = client.search_messages(
            query=f"<@{user_id}>",
            count=50,
            sort="timestamp",
            sort_dir="desc",
        )
    except SlackApiError as e:
        print(f"[ERROR] メッセージ検索失敗: {e}", file=sys.stderr)
        return []

    for match in result.get("messages", {}).get("matches", []):
        ts = float(match["ts"])

        # 指定期間より古いものはスキップ
        if ts < cutoff_ts:
            continue

        # 自分が送ったメッセージはスキップ
        if match.get("user") == user_id:
            continue

        channel_id = match["channel"]["id"]
        msg_ts = match["ts"]

        # --- スタンプチェック ---
        has_reacted = False
        try:
            r = client.reactions_get(channel=channel_id, timestamp=msg_ts)
            for reaction in r.get("message", {}).get("reactions", []):
                if user_id in reaction.get("users", []):
                    has_reacted = True
                    break
        except SlackApiError:
            pass

        if has_reacted:
            continue

        # --- スレッド返信チェック ---
        has_replied = False
        thread_ts = match.get("thread_ts")
        if thread_ts:
            try:
                replies = client.conversations_replies(
                    channel=channel_id, ts=thread_ts
                )
                for reply in replies.get("messages", []):
                    if reply.get("user") == user_id and reply["ts"] != msg_ts:
                        has_replied = True
                        break
            except SlackApiError:
                pass

        if has_replied:
            continue

        unresponded.append(
            {
                "text": match.get("text", "")[:120],
                "channel_name": match["channel"].get("name", channel_id),
                "sender": match.get("username") or match.get("user", "Unknown"),
                "time": datetime.fromtimestamp(ts).strftime("%m/%d %H:%M"),
                "permalink": match.get("permalink", ""),
            }
        )

    return unresponded


def send_dm_reminder(client, user_id, mentions):
    """自分宛にDMでリマインドを送信"""
    if not mentions:
        return

    lines = [f":bell: *未返信メンション {len(mentions)} 件があります*\n"]

    for m in mentions[:10]:
        link = f"<{m['permalink']}|開く>" if m["permalink"] else ""
        lines.append(
            f"• *#{m['channel_name']}* _{m['time']}_ @{m['sender']}\n"
            f"  `{m['text'].strip()[:80]}` {link}"
        )

    if len(mentions) > 10:
        lines.append(f"\n_...他 {len(mentions) - 10} 件_")

    text = "\n".join(lines)

    try:
        dm = client.conversations_open(users=[user_id])
        dm_channel = dm["channel"]["id"]
        client.chat_postMessage(
            channel=dm_channel,
            text=text,
            mrkdwn=True,
        )
        print(f"[OK] DM送信完了: {len(mentions)} 件のリマインド")
    except SlackApiError as e:
        print(f"[ERROR] DM送信失敗: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if not is_reminder_time():
        print(f"[SKIP] リマインド時間外です ({datetime.now().strftime('%H:%M')})")
        return

    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        print("[ERROR] 環境変数 SLACK_USER_TOKEN が設定されていません", file=sys.stderr)
        sys.exit(1)

    client = WebClient(token=token)

    try:
        user_id = get_my_user_id(client)
    except SlackApiError as e:
        print(f"[ERROR] 認証失敗: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] ユーザーID: {user_id} ({datetime.now().strftime('%Y-%m-%d %H:%M')})")

    mentions = get_unresponded_mentions(client, user_id)

    if mentions:
        send_dm_reminder(client, user_id, mentions)
    else:
        print("[OK] 未返信メンションはありません")


if __name__ == "__main__":
    main()
