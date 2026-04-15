#!/usr/bin/env python3
"""
Gmail 送信メール 未返信リマインダー
------------------------------------
自分が送った Gmail のうち、スレッドの最後のメッセージが自分からのもので
THRESHOLD_SEC (3日) 以上返信がないものを検索し、Slack DM でリマインドを送る。

事前準備:
  1. Google Cloud Console でプロジェクトを作成し Gmail API を有効化
  2. OAuth 2.0 クライアント認証情報 (credentials.json) をダウンロード
  3. 環境変数を設定:
       GOOGLE_CREDENTIALS_PATH  (デフォルト: credentials.json)
       GOOGLE_TOKEN_PATH        (デフォルト: token.json)
  4. 初回実行時にブラウザで認証を行い token.json を生成
       python3 check_gmail_sent.py
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as google_build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN      = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID       = "U0973MEH3V0"
THRESHOLD_SEC    = 3 * 24 * 60 * 60   # 3 日
LOOKBACK_DAYS    = 14                  # 過去 14 日間をスキャン
ACTIVE_HOURS     = range(8, 20)       # 8:00〜19:59 のみ実行

CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH       = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


def get_gmail_service():
    """Gmail API サービスを初期化して返す。初回はブラウザ認証が走る。"""
    creds = None
    if Path(TOKEN_PATH).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDENTIALS_PATH).exists():
                raise FileNotFoundError(
                    f"認証ファイルが見つかりません: {CREDENTIALS_PATH}\n"
                    "Google Cloud Console から OAuth 2.0 認証情報をダウンロードし、\n"
                    f"GOOGLE_CREDENTIALS_PATH 環境変数で指定してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return google_build("gmail", "v1", credentials=creds)


def find_unanswered_sent_emails(service, now_ts: float) -> list[dict]:
    """
    送信済みメールのうち、スレッドの最後のメッセージが自分からのもので
    THRESHOLD_SEC 以上返信がないスレッドを返す。
    """
    cutoff_ts = now_ts - THRESHOLD_SEC
    results   = []

    after_epoch = int(now_ts - LOOKBACK_DAYS * 24 * 3600)
    query = f"in:sent after:{after_epoch}"

    try:
        response = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=100,
        ).execute()
    except Exception as e:
        print(f"[WARN] Gmail messages.list failed: {e}")
        return []

    messages = response.get("messages", [])
    print(f"[INFO] Gmail 送信メッセージ {len(messages)} 件のスレッドをチェック中...")

    seen_threads: set[str] = set()

    for msg_ref in messages:
        thread_id = msg_ref["threadId"]
        if thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        try:
            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="metadata",
                metadataHeaders=["Subject", "From", "To"],
            ).execute()
        except Exception as e:
            print(f"[WARN] threads.get failed for {thread_id}: {e}")
            continue

        thread_msgs = thread.get("messages", [])
        if not thread_msgs:
            continue

        # スレッドの最後のメッセージを確認（Gmail API は時系列順で返す）
        last_msg    = thread_msgs[-1]
        last_labels = last_msg.get("labelIds", [])

        # 最後のメッセージが自分からのもの (SENT) でなければ返信済み
        if "SENT" not in last_labels:
            continue

        # 最後のメッセージの送信日時 (internalDate は ms)
        sent_ts = int(last_msg.get("internalDate", 0)) / 1000
        if sent_ts == 0:
            continue
        if sent_ts > cutoff_ts:
            continue  # まだ猶予期間内

        elapsed_days = int((now_ts - sent_ts) / 86400)
        sent_time    = datetime.fromtimestamp(sent_ts, tz=timezone.utc)

        headers = {
            h["name"]: h["value"]
            for h in last_msg.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "(件名なし)")
        to_addr = headers.get("To", "unknown")

        results.append({
            "thread_id":    thread_id,
            "subject":      subject,
            "to":           to_addr,
            "sent_time":    sent_time.strftime("%Y-%m-%d %H:%M UTC"),
            "elapsed_days": elapsed_days,
        })

    return results


def build_reminder_text(items: list[dict]) -> str:
    lines = [
        f":email: *返信待ちのメールが {len(items)} 件あります*（3日以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        gmail_link = f"https://mail.google.com/mail/u/0/#all/{item['thread_id']}"
        lines.append(
            f"*{i}.* {item['sent_time']}（{item['elapsed_days']}日以上前）\n"
            f"   宛先: {item['to']}\n"
            f"   件名: _{item['subject']}_\n"
            f"   <{gmail_link}|Gmail で開く>\n"
        )
    return "\n".join(lines)


def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM sent.")


def main() -> None:
    if not GMAIL_AVAILABLE:
        print("[ERROR] Gmail API ライブラリがインストールされていません。")
        print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return

    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時のみ）のためスキップ。")
        return

    print(f"[INFO] Gmail未返信チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    try:
        service = get_gmail_service()
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return
    except Exception as e:
        print(f"[ERROR] Gmail 認証に失敗しました: {e}")
        return

    unanswered = find_unanswered_sent_emails(service, now_ts)

    if not unanswered:
        print("[INFO] 返信待ちのメールなし。リマインドは送りません。")
        return

    print(f"[INFO] {len(unanswered)} 件の返信待ちを検出。DMを送信します。")
    send_dm(build_reminder_text(unanswered))


if __name__ == "__main__":
    main()
