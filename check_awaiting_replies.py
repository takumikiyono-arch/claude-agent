#!/usr/bin/env python3
"""
Awaiting Reply Reminder
-----------------------
自分が送ったメッセージ/メールで返信が来ていないものを自分の Slack DM に通知する。
  - Slack : 送信から 1 日以上経過 & 他者からの返信なし
  - Gmail : 送信から 3 日以上経過 & スレッドに自分以外の返信なし
"""

import os
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN          = os.environ["SLACK_BOT_TOKEN"]   # xoxp-... ユーザートークン推奨
MY_USER_ID           = "U0973MEH3V0"
SLACK_THRESHOLD_SEC  = 1 * 24 * 60 * 60   # 1日
GMAIL_THRESHOLD_SEC  = 3 * 24 * 60 * 60   # 3日
LOOKBACK_SEC         = 7 * 24 * 60 * 60   # 7日間さかのぼる
ACTIVE_HOURS         = range(8, 20)        # 8:00〜19:59 のみ実行
GMAIL_TOKEN_PATH     = os.environ.get("GMAIL_TOKEN_PATH", "token.json")
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ═══════════════════════════════════════════════════════════════════════════════
# Slack — 自分が送って返信待ちのメッセージを収集
# ═══════════════════════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def others_replied_in_thread(channel: str, thread_ts: str) -> bool:
    """スレッドに自分以外の返信があれば True を返す。"""
    try:
        for page in slack_client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:  # 親メッセージはスキップ
                    continue
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def find_slack_unanswered(now_ts: float) -> list[dict]:
    """1日以上返信がない自分の送信メッセージ（チャンネル + DM）を収集する。"""
    cutoff  = now_ts - SLACK_THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_SEC
    results = []

    channels: list[dict] = []
    try:
        for page in slack_client.conversations_list(
            types="public_channel,private_channel,im,mpim",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")
        return results

    print(f"[Slack] {len(channels)} チャンネル/DM をスキャン中...")

    for ch in channels:
        ch_id   = ch["id"]
        # DM の場合は name がなく user フィールドが相手のユーザーID
        ch_name = ch.get("name") or ch.get("user") or ch_id
        try:
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # スレッド返信はスキップ（トップレベルメッセージのみ対象）
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    # 自分が送ったメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:  # まだ1日経っていない
                        continue

                    # 他者からの返信がある場合はスキップ
                    if others_replied_in_thread(ch_id, msg["ts"]):
                        continue

                    msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    elapsed  = int((now_ts - msg_ts) / 3600)
                    results.append({
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


# ═══════════════════════════════════════════════════════════════════════════════
# Gmail — 自分が送って返信待ちのスレッドを収集
# ═══════════════════════════════════════════════════════════════════════════════

def _get_gmail_service():
    """token.json から認証情報を読み込み Gmail サービスを返す。"""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as e:
        raise ImportError(
            "Google ライブラリが未インストールです。"
            "pip install google-auth google-auth-oauthlib google-api-python-client"
        ) from e

    if not os.path.exists(GMAIL_TOKEN_PATH):
        raise FileNotFoundError(
            f"Gmail トークンが見つかりません: {GMAIL_TOKEN_PATH}\n"
            "setup_gmail_oauth.py を実行して token.json を生成してください。"
        )

    creds = Credentials.from_authorized_user_file(
        GMAIL_TOKEN_PATH,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def find_gmail_unanswered(now_ts: float) -> list[dict]:
    """3日以上返信がない送信スレッドを収集する。"""
    cutoff_ts = now_ts - GMAIL_THRESHOLD_SEC
    oldest_ts = now_ts - LOOKBACK_SEC
    results   = []

    try:
        service = _get_gmail_service()
    except (FileNotFoundError, ImportError) as e:
        print(f"[Gmail] スキップ: {e}")
        return results

    oldest_date = datetime.fromtimestamp(oldest_ts, tz=timezone.utc).strftime("%Y/%m/%d")
    query = f"in:sent after:{oldest_date}"

    try:
        resp    = service.users().threads().list(userId="me", q=query, maxResults=200).execute()
        threads = resp.get("threads", [])
    except Exception as e:
        print(f"[Gmail] threads.list 失敗: {e}")
        return results

    print(f"[Gmail] {len(threads)} スレッドを確認中...")

    me_profile = service.users().getProfile(userId="me").execute()
    my_email   = me_profile["emailAddress"].lower()

    for thread_meta in threads:
        try:
            thread = service.users().threads().get(
                userId="me",
                id=thread_meta["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject"],
            ).execute()
        except Exception:
            continue

        messages = thread.get("messages", [])
        if not messages:
            continue

        # スレッドの最新メッセージが自分からか確認
        last_msg    = messages[-1]
        last_hdrs   = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}
        from_hdr    = last_hdrs.get("From", "").lower()
        if my_email not in from_hdr:
            continue  # 最後が相手のメッセージ = 返信済み

        # 最後の送信日時チェック（internalDate は ms）
        internal_date = int(last_msg.get("internalDate", 0)) / 1000
        if internal_date > cutoff_ts:  # まだ3日経っていない
            continue
        if internal_date < oldest_ts:
            continue

        # 件名と宛先は最初のメッセージから取得
        first_hdrs = {h["name"]: h["value"] for h in messages[0].get("payload", {}).get("headers", [])}
        subject    = last_hdrs.get("Subject") or first_hdrs.get("Subject", "(件名なし)")
        to_hdr     = first_hdrs.get("To", "")

        sent_time = datetime.fromtimestamp(internal_date, tz=timezone.utc)
        elapsed_h = int((now_ts - internal_date) / 3600)

        results.append({
            "subject":   subject[:80],
            "to":        to_hdr[:80],
            "sent_time": sent_time.strftime("%Y-%m-%d %H:%M UTC"),
            "elapsed_d": elapsed_h // 24,
            "thread_id": thread_meta["id"],
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# リマインド送信
# ═══════════════════════════════════════════════════════════════════════════════

def build_reminder_text(slack_items: list[dict], gmail_items: list[dict]) -> str:
    lines = []

    if slack_items:
        lines.append(f":slack: *Slack — 未返信 {len(slack_items)} 件*（1日以上経過）\n")
        for i, item in enumerate(slack_items, 1):
            link = (
                f"https://slack.com/archives/{item['channel_id']}"
                f"/p{item['ts'].replace('.', '')}"
            )
            lines.append(
                f"*{i}.* <#{item['channel_id']}> — {item['msg_time_utc']}"
                f"（{item['elapsed_h']}時間経過）\n"
                f"   内容: _{item['text']}…_\n"
                f"   {link}\n"
            )

    if gmail_items:
        if lines:
            lines.append("")
        lines.append(f":email: *Gmail — 未返信 {len(gmail_items)} 件*（3日以上経過）\n")
        for i, item in enumerate(gmail_items, 1):
            lines.append(
                f"*{i}.* 件名: _{item['subject']}_\n"
                f"   宛先: {item['to']}\n"
                f"   送信: {item['sent_time']}（{item['elapsed_d']}日経過）\n"
                f"   https://mail.google.com/mail/u/0/#sent/{item['thread_id']}\n"
            )

    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時のみ）のためスキップ。")
        return

    print(f"[INFO] チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    slack_items = find_slack_unanswered(now_ts)
    gmail_items = find_gmail_unanswered(now_ts)

    if not slack_items and not gmail_items:
        print("[INFO] 未返信メッセージなし — リマインドは送りません。")
        return

    print(f"[INFO] Slack: {len(slack_items)} 件 / Gmail: {len(gmail_items)} 件 — DM を送信します。")
    reminder = build_reminder_text(slack_items, gmail_items)
    send_dm(reminder)


if __name__ == "__main__":
    main()
