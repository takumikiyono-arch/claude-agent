#!/usr/bin/env python3
"""
Gmail Sent-Email Reminder
--------------------------
自分が送信したメールのうち、3日以上返信がないスレッドを検索し、
Slack DM でリマインドを送る。

初回セットアップ:
  1. Google Cloud Console (https://console.cloud.google.com) で新規プロジェクトを作成
  2. 「APIとサービス」→「ライブラリ」→ Gmail API を有効化
  3. 「認証情報」→「OAuth 2.0 クライアント ID」を作成（アプリの種類: デスクトップ）
  4. ダウンロードした JSON を gmail_credentials.json として本スクリプトと同じディレクトリに配置
  5. 初回実行時にブラウザで Google 認証 → gmail_token.json が自動生成される
  6. 以降はトークンを自動更新（再認証不要）

環境変数:
  SLACK_BOT_TOKEN  xoxp-... (User Token) or xoxb-... (Bot Token)
"""

import os
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN      = os.environ["SLACK_BOT_TOKEN"]
MY_SLACK_USER_ID = "U0973MEH3V0"
THRESHOLD_DAYS   = 3              # 3日以上返信なし → リマインド
LOOKBACK_DAYS    = 30             # 過去30日分をスキャン
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]

_dir             = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(_dir, "gmail_credentials.json")
TOKEN_FILE       = os.path.join(_dir, "gmail_token.json")
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ── Gmail 認証 ────────────────────────────────────────────────────────────────

def get_gmail_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print(
            "[ERROR] Google API ライブラリが見つかりません。\n"
            "        pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        )
        sys.exit(1)

    if not os.path.exists(CREDENTIALS_FILE):
        print(
            f"[ERROR] {CREDENTIALS_FILE} が見つかりません。\n"
            "        Google Cloud Console から OAuth 2.0 クライアント ID をダウンロードして配置してください。"
        )
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ── Gmail スキャン ────────────────────────────────────────────────────────────

def find_unanswered_sent(service) -> list[dict]:
    """
    送信済みスレッドのうち、最後のメッセージが自分からで
    3日以上返信がないものを返す。
    """
    now_ts       = time.time()
    threshold_ts = now_ts - THRESHOLD_DAYS * 86400
    after_epoch  = int(now_ts - LOOKBACK_DAYS * 86400)

    # 自分のメールアドレスを取得（1回だけ）
    profile  = service.users().getProfile(userId="me").execute()
    my_email = profile["emailAddress"].lower()

    unanswered: list[dict] = []
    seen_threads: set[str] = set()
    page_token             = None

    while True:
        params: dict = dict(
            userId    = "me",
            q         = f"in:sent after:{after_epoch}",
            maxResults= 100,
        )
        if page_token:
            params["pageToken"] = page_token

        result      = service.users().threads().list(**params).execute()
        thread_refs = result.get("threads", [])

        for ref in thread_refs:
            tid = ref["id"]
            if tid in seen_threads:
                continue
            seen_threads.add(tid)

            thread = service.users().threads().get(
                userId          = "me",
                id              = tid,
                format          = "metadata",
                metadataHeaders = ["From", "Subject", "Date", "To"],
            ).execute()

            msgs = thread.get("messages", [])
            if not msgs:
                continue

            # スレッドの最後のメッセージを確認
            last_msg      = msgs[-1]
            last_headers  = last_msg.get("payload", {}).get("headers", [])
            last_from     = get_header(last_headers, "From").lower()
            last_date_str = get_header(last_headers, "Date")

            # 最後のメッセージが自分から送ったものでなければスキップ（相手が返信済み）
            if my_email not in last_from:
                continue

            # 送信日時をパース
            try:
                last_date_ts = parsedate_to_datetime(last_date_str).timestamp()
            except Exception:
                continue

            # しきい値（3日）を超えていなければスキップ
            if last_date_ts > threshold_ts:
                continue

            # 件名・宛先を最初に自分が送ったメッセージから取得
            subject = to = ""
            for m in msgs:
                m_headers = m.get("payload", {}).get("headers", [])
                if my_email in get_header(m_headers, "From").lower():
                    subject = get_header(m_headers, "Subject") or "(件名なし)"
                    to      = get_header(m_headers, "To")
                    break

            elapsed_days = int((now_ts - last_date_ts) / 86400)
            sent_time    = (
                datetime.fromtimestamp(last_date_ts, tz=timezone.utc)
                .strftime("%Y-%m-%d %H:%M UTC")
            )

            unanswered.append({
                "thread_id":    tid,
                "subject":      subject[:80],
                "to":           to[:80],
                "sent_time":    sent_time,
                "elapsed_days": elapsed_days,
            })

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return unanswered


# ── Slack DM 送信 ─────────────────────────────────────────────────────────────

def build_reminder_text(items: list[dict]) -> str:
    lines = [
        f":email: *返信待ちのGmailが {len(items)} 件あります*（3日以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        link = f"https://mail.google.com/mail/u/0/#all/{item['thread_id']}"
        lines.append(
            f"*{i}.* {item['subject']}\n"
            f"   宛先: {item['to']}\n"
            f"   送信日時: {item['sent_time']}（{item['elapsed_days']}日以上前）\n"
            f"   {link}\n"
        )
    return "\n".join(lines)


def send_slack_dm(text: str) -> None:
    resp       = slack_client.conversations_open(users=MY_SLACK_USER_ID)
    dm_channel = resp["channel"]["id"]
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] Slack DM 送信完了。")


# ── エントリーポイント ─────────────────────────────────────────────────────────

def main() -> None:
    service    = get_gmail_service()
    unanswered = find_unanswered_sent(service)

    if not unanswered:
        print("[INFO] 未返信のGmailなし。")
        return

    print(f"[INFO] {len(unanswered)} 件の未返信Gmailを検出。Slack DMを送信します。")
    send_slack_dm(build_reminder_text(unanswered))


if __name__ == "__main__":
    main()
