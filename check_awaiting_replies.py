#!/usr/bin/env python3
"""
返信待ちリマインダー
--------------------
自分が送ったSlackメッセージ・Gmailで、一定時間返信がないものを検索し
Slack DMでリマインドを送る。

Slack: 24時間返信なし
Gmail: 72時間（3日）返信なし

必要な環境変数:
  SLACK_USER_TOKEN   : xoxp-... (ユーザートークン。search:read, channels:history等が必要)
  SLACK_BOT_TOKEN    : xoxb-... (DM送信用。chat:write が必要)
  GMAIL_CLIENT_ID    : GCP OAuth2 クライアントID
  GMAIL_CLIENT_SECRET: GCP OAuth2 クライアントシークレット
  GMAIL_REFRESH_TOKEN: Gmail OAuth2 リフレッシュトークン
"""

import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
MY_USER_ID = "U0973MEH3V0"

SLACK_THRESHOLD_HOURS = 24    # Slack: 24時間返信なしでリマインド
GMAIL_THRESHOLD_DAYS  = 3     # Gmail: 3日返信なしでリマインド

# レスポンスを期待するメッセージかどうかの判定キーワード
RESPONSE_KEYWORDS_JA = [
    "ご確認", "ご返信", "ご対応", "お願い", "いかがでしょ", "教えていただ",
    "ご検討", "ご返答", "お伺い", "ご意見", "どうでしょう", "よろしくお願い",
    "宜しくお願い", "ご連絡", "いただけます", "いただけます", "確認お願い",
    "教えてください", "検討してください", "返信ください",
]
RESPONSE_KEYWORDS_EN = [
    "please reply", "please confirm", "let me know", "your thoughts",
    "could you", "can you", "would you", "please advise", "looking forward",
    "waiting for your", "please respond", "RSVP",
]

def needs_response(text: str) -> bool:
    """テキストが返信を期待する内容かどうかを判定する"""
    if "?" in text or "？" in text:
        return True
    text_lower = text.lower()
    for kw in RESPONSE_KEYWORDS_JA + RESPONSE_KEYWORDS_EN:
        if kw.lower() in text_lower:
            return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Slack チェック
# ─────────────────────────────────────────────────────────────────────────────

def check_slack_awaiting():
    """自分が送ったSlackメッセージで24時間返信がないものを返す"""
    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        print("[Slack] SLACK_USER_TOKEN not set, skipping.")
        return []

    client = WebClient(token=token)
    now = time.time()
    threshold_ts = now - SLACK_THRESHOLD_HOURS * 3600
    # 検索対象は過去7日
    oldest_ts = now - 7 * 86400

    awaiting = []

    try:
        # search.messages で自分が送ったメッセージを検索
        # Slack search APIはページネーションあり
        page = 1
        while True:
            resp = client.search_messages(
                query=f"from:<@{MY_USER_ID}>",
                sort="timestamp",
                sort_dir="desc",
                count=100,
                page=page,
            )
            messages = resp["messages"]["matches"]
            if not messages:
                break

            for msg in messages:
                ts = float(msg.get("ts", 0))
                # 古すぎるものはスキップ（7日以上前）
                if ts < oldest_ts:
                    break
                # 閾値（24時間）より新しいものはまだ待機中 → スキップ
                if ts > threshold_ts:
                    continue
                # 返信を期待する内容でなければスキップ
                text = msg.get("text", "")
                if not needs_response(text):
                    continue

                channel_id = msg.get("channel", {}).get("id", "")
                channel_name = msg.get("channel", {}).get("name", channel_id)
                permalink = msg.get("permalink", "")

                # スレッドに他ユーザーの返信があるか確認
                has_reply = False
                if msg.get("reply_count", 0) > 0:
                    try:
                        thread_resp = client.conversations_replies(
                            channel=channel_id,
                            ts=str(ts),
                            limit=50,
                        )
                        for reply in thread_resp.get("messages", [])[1:]:
                            if reply.get("user") != MY_USER_ID:
                                has_reply = True
                                break
                    except SlackApiError:
                        pass

                if not has_reply:
                    elapsed_h = (now - ts) / 3600
                    awaiting.append({
                        "type": "slack",
                        "text": text[:80] + ("..." if len(text) > 80 else ""),
                        "channel": channel_name,
                        "elapsed_hours": elapsed_h,
                        "permalink": permalink,
                        "ts": ts,
                    })

            paging = resp["messages"]["paging"]
            if page >= paging.get("pages", 1):
                break
            page += 1

    except SlackApiError as e:
        print(f"[Slack] search error: {e.response['error']}")

    return awaiting


# ─────────────────────────────────────────────────────────────────────────────
# Gmail チェック
# ─────────────────────────────────────────────────────────────────────────────

def gmail_get_access_token():
    """リフレッシュトークンからアクセストークンを取得する"""
    client_id     = os.environ.get("GMAIL_CLIENT_ID", "")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN", "")

    if not all([client_id, client_secret, refresh_token]):
        return None

    data = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]
    except Exception as e:
        print(f"[Gmail] Token refresh error: {e}")
        return None


def gmail_api(access_token, path, params=None):
    """Gmail REST APIを呼び出す"""
    base = "https://gmail.googleapis.com/gmail/v1"
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"[Gmail] API error {e.code}: {e.read().decode()[:200]}")
        return None


def check_gmail_awaiting():
    """自分が送ったGmailで3日間返信がないものを返す"""
    access_token = gmail_get_access_token()
    if not access_token:
        print("[Gmail] credentials not set, skipping.")
        return []

    now = datetime.now(timezone.utc)
    threshold_dt = now - timedelta(days=GMAIL_THRESHOLD_DAYS)
    oldest_dt    = now - timedelta(days=30)  # 最大30日前まで

    # 送信済みメールをGmailの日付フィルタで取得
    after_str  = oldest_dt.strftime("%Y/%m/%d")
    before_str = threshold_dt.strftime("%Y/%m/%d")

    # 「in:sent after:DATE before:DATE」で絞り込み
    query = f"in:sent after:{after_str} before:{before_str}"

    data = gmail_api(access_token, "/users/me/messages", {
        "q": query,
        "maxResults": 100,
    })
    if not data or "messages" not in data:
        return []

    awaiting = []
    user_email = None

    # 自分のメールアドレスを取得
    profile = gmail_api(access_token, "/users/me/profile")
    if profile:
        user_email = profile.get("emailAddress", "")

    for msg_ref in data.get("messages", []):
        msg_id = msg_ref["id"]

        # メッセージの詳細取得（スレッドIDを得るため）
        msg = gmail_api(access_token, f"/users/me/messages/{msg_id}", {
            "format": "metadata",
            "metadataHeaders": "Subject,From,To,Date",
        })
        if not msg:
            continue

        thread_id = msg.get("threadId")
        headers   = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject   = headers.get("Subject", "(件名なし)")
        to        = headers.get("To", "")
        date_str  = headers.get("Date", "")

        # 本文の一部を取得して返信期待キーワードチェック
        full_msg = gmail_api(access_token, f"/users/me/messages/{msg_id}", {
            "format": "full",
        })
        body_text = ""
        if full_msg:
            parts = full_msg.get("payload", {}).get("parts", [])
            if parts:
                import base64
                for part in parts:
                    if part.get("mimeType") == "text/plain":
                        data_b64 = part.get("body", {}).get("data", "")
                        if data_b64:
                            body_text = base64.urlsafe_b64decode(data_b64 + "==").decode("utf-8", errors="ignore")
                            break

        check_text = subject + " " + body_text[:500]
        if not needs_response(check_text):
            # 件名や本文に返信期待のキーワードがなければスキップ
            # ただし「?」「？」がある場合は含める
            pass

        # スレッドの全メッセージを取得して返信があるか確認
        thread = gmail_api(access_token, f"/users/me/threads/{thread_id}", {
            "format": "metadata",
            "metadataHeaders": "From",
        })
        if not thread:
            continue

        thread_msgs = thread.get("messages", [])
        has_reply   = False
        for tm in thread_msgs:
            tm_headers = {h["name"]: h["value"] for h in tm.get("payload", {}).get("headers", [])}
            from_addr  = tm_headers.get("From", "")
            if tm["id"] != msg_id and user_email and user_email not in from_addr:
                has_reply = True
                break

        if not has_reply:
            # 送信日時を計算
            sent_ts = int(msg.get("internalDate", 0)) / 1000
            elapsed_days = (time.time() - sent_ts) / 86400

            awaiting.append({
                "type":          "gmail",
                "subject":       subject,
                "to":            to,
                "elapsed_days":  elapsed_days,
                "msg_id":        msg_id,
                "thread_id":     thread_id,
            })

        time.sleep(0.1)  # rate limit対策

    return awaiting


# ─────────────────────────────────────────────────────────────────────────────
# リマインド送信
# ─────────────────────────────────────────────────────────────────────────────

def send_reminder(slack_items, gmail_items):
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("SLACK_BOT_TOKEN not set.")
        return

    if not slack_items and not gmail_items:
        print("返信待ちアイテムはありません。")
        return

    client = WebClient(token=token)
    resp   = client.conversations_open(users=MY_USER_ID)
    dm_ch  = resp["channel"]["id"]

    lines = [":bell: *返信待ちリマインド*\n"]

    if slack_items:
        lines.append(f"*Slack — {SLACK_THRESHOLD_HOURS}時間以上返信なし（{len(slack_items)}件）*")
        for item in slack_items:
            elapsed = f"{item['elapsed_hours']:.0f}時間"
            lines.append(f"• [{item['channel']}] {elapsed}経過 — 「{item['text']}」")
            if item.get("permalink"):
                lines.append(f"  {item['permalink']}")
        lines.append("")

    if gmail_items:
        lines.append(f"*Gmail — {GMAIL_THRESHOLD_DAYS}日以上返信なし（{len(gmail_items)}件）*")
        for item in gmail_items:
            elapsed = f"{item['elapsed_days']:.0f}日"
            to_short = item['to'][:50] + ("..." if len(item['to']) > 50 else "")
            lines.append(f"• {elapsed}経過 — 件名:「{item['subject']}」 宛先: {to_short}")
            lines.append(f"  https://mail.google.com/mail/u/0/#inbox/{item['thread_id']}")
        lines.append("")

    message = "\n".join(lines)
    client.chat_postMessage(channel=dm_ch, text=message)
    print(f"Reminder sent: Slack={len(slack_items)}, Gmail={len(gmail_items)}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 返信待ちチェック開始")
    slack_items = check_slack_awaiting()
    gmail_items = check_gmail_awaiting()
    send_reminder(slack_items, gmail_items)


if __name__ == "__main__":
    main()
