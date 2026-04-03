#!/usr/bin/env python3
"""
Slack Mention Reminder
----------------------
自分(@U0973MEH3V0)宛のメンションのうち、3時間以上返信もスタンプもしていないものを
検索し、未対応のものがあれば自分自身にDMでリマインドを送る。
"""

import os
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN   = os.environ["SLACK_BOT_TOKEN"]   # xoxp-... or xoxb-... token
MY_USER_ID    = "U0973MEH3V0"
THRESHOLD_SEC = 3 * 60 * 60   # 3 hours
LOOKBACK_SEC  = 24 * 60 * 60  # how far back to scan (24 h)
# ─────────────────────────────────────────────────────────────────────────────

client = WebClient(token=SLACK_TOKEN)


def get_dm_channel(user_id: str) -> str:
    """Open (or reuse) a DM channel with the given user and return its ID."""
    resp = client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def user_reacted(channel: str, ts: str) -> bool:
    """Return True if MY_USER_ID has added any reaction to the message."""
    try:
        resp = client.reactions_get(channel=channel, timestamp=ts)
        msg = resp.get("message", {})
        for reaction in msg.get("reactions", []):
            if MY_USER_ID in reaction.get("users", []):
                return True
    except SlackApiError:
        pass
    return False


def user_replied_in_thread(channel: str, thread_ts: str) -> bool:
    """Return True if MY_USER_ID has posted any reply in the thread."""
    try:
        for page in client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                # Skip the parent message itself
                if msg.get("ts") == thread_ts:
                    continue
                if msg.get("user") == MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def fetch_joined_channels() -> list[dict]:
    """Return all public/private channels the bot/user has joined."""
    channels = []
    try:
        for page in client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")
    return channels


def find_unanswered_mentions(now_ts: float) -> list[dict]:
    """
    Scan all joined channels for messages that:
      - mention MY_USER_ID
      - are older than THRESHOLD_SEC
      - have NOT been replied to or reacted to by MY_USER_ID
    """
    cutoff     = now_ts - THRESHOLD_SEC
    oldest     = now_ts - LOOKBACK_SEC
    unanswered = []

    channels = fetch_joined_channels()
    print(f"[INFO] Scanning {len(channels)} channel(s)...")

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
                    # Only top-level messages (not thread replies)
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    text = msg.get("text", "")
                    if f"<@{MY_USER_ID}>" not in text:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:
                        # Newer than 3 h – still within grace period
                        continue

                    # Check whether the user already responded
                    if user_replied_in_thread(ch_id, msg["ts"]):
                        continue
                    if user_reacted(ch_id, msg["ts"]):
                        continue

                    sender   = msg.get("user", "unknown")
                    msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    elapsed  = int((now_ts - msg_ts) / 3600)

                    unanswered.append({
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "sender":       sender,
                        "ts":           msg["ts"],
                        "text":         text[:120],
                        "elapsed_h":    elapsed,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                    })

        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for #{ch_name}: {e}")

    return unanswered


def build_reminder_text(items: list[dict]) -> str:
    lines = [
        f":bell: *未返信のメンションが {len(items)} 件あります*（3時間以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        link = (
            f"https://slack.com/archives/{item['channel_id']}/p{item['ts'].replace('.', '')}"
        )
        lines.append(
            f"*{i}.* <#{item['channel_id']}> – {item['msg_time_utc']}"
            f"（{item['elapsed_h']}時間以上前）\n"
            f"   送信者: <@{item['sender']}>\n"
            f"   内容: _{item['text']}…_\n"
            f"   {link}\n"
        )
    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM sent.")


def main() -> None:
    now_ts = time.time()
    print(f"[INFO] Check started at {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    unanswered = find_unanswered_mentions(now_ts)

    if not unanswered:
        print("[INFO] 未対応メンションなし。リマインドは送りません。")
        return

    print(f"[INFO] {len(unanswered)} 件の未対応メンションを検出。DMを送信します。")
    reminder = build_reminder_text(unanswered)
    send_dm(reminder)


if __name__ == "__main__":
    main()
