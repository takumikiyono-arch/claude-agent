#!/usr/bin/env python3
"""
Outgoing Message Reminder
--------------------------
1. Slack : 自分が送ったメッセージで、1日以上返信がないものをDMでリマインド
2. Gmail : 自分が送ったメールで、3日以上返信がないものをSlack DMでリマインド

応答を求めているかの判定は「?／？」または日本語のリクエスト系キーワードで行う。
"""

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Gmail SDK（pip install google-auth google-auth-oauthlib google-api-python-client）
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as google_build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    print("[WARN] Gmail SDK が見つかりません。pip install google-auth google-auth-oauthlib google-api-python-client")

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN       = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID        = "U0973MEH3V0"

SLACK_THRESHOLD_S = 1 * 24 * 60 * 60   # 1日 = 返信待ち判定閾値
GMAIL_THRESHOLD_S = 3 * 24 * 60 * 60   # 3日 = 返信待ち判定閾値
LOOKBACK_S        = 7 * 24 * 60 * 60   # スキャン範囲（過去7日）
ACTIVE_HOURS      = range(8, 20)        # 8:00〜19:59 のみ実行

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDS_FILE   = Path(__file__).parent / "credentials.json"   # Google Cloud OAuthクレデンシャル
TOKEN_FILE   = Path(__file__).parent / "token.json"          # 初回認証後に自動生成

# 応答を求めているかどうかの判定パターン
RESPONSE_NEEDED = re.compile(
    r"[?？]"
    r"|お願い|ご確認|確認して|教えてください|いかがでしょうか|どうでしょうか"
    r"|よろしくお願い|ご返信|ご回答|ご連絡|お返事|ご意見|ご検討"
    r"|please|let me know|could you|can you|would you",
    re.IGNORECASE,
)
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
# 共通ユーティリティ
# ══════════════════════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM sent.")


def requires_response(text: str) -> bool:
    return bool(RESPONSE_NEEDED.search(text))


# ══════════════════════════════════════════════════════════════════════════════
# Slack: 自分が送った未返信メッセージ
# ══════════════════════════════════════════════════════════════════════════════

def fetch_joined_channels() -> list[dict]:
    channels = []
    try:
        for page in slack_client.conversations_list(
            types="public_channel,private_channel,mpim,im",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")
    return channels


def others_replied_after(channel: str, thread_ts: str, sent_ts: float) -> bool:
    """送信後に自分以外が返信しているかどうかを返す。"""
    try:
        for page in slack_client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:
                    continue
                if float(msg.get("ts", 0)) <= sent_ts:
                    continue
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def find_unanswered_sent_slack(now_ts: float) -> list[dict]:
    """1日以上返信のない、自分が送った「応答を求めている」メッセージを返す。"""
    cutoff  = now_ts - SLACK_THRESHOLD_S
    oldest  = now_ts - LOOKBACK_S
    results = []

    channels = fetch_joined_channels()
    print(f"[INFO] Slack: {len(channels)} チャンネルをスキャン中...")

    for ch in channels:
        ch_id   = ch["id"]
        ch_name = ch.get("name", ch_id)
        try:
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # 自分が送ったメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue
                    # スレッド返信（子メッセージ）は除外
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    text   = msg.get("text", "")
                    msg_ts = float(msg["ts"])

                    if msg_ts > cutoff:          # まだ1日経っていない
                        continue
                    if not requires_response(text):   # 応答不要そうなメッセージ
                        continue
                    if others_replied_after(ch_id, msg["ts"], msg_ts):  # 返信済み
                        continue

                    msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    elapsed  = int((now_ts - msg_ts) / 3600)
                    link     = (
                        f"https://slack.com/archives/{ch_id}"
                        f"/p{msg['ts'].replace('.', '')}"
                    )
                    results.append({
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "text":         text[:120],
                        "elapsed_h":    elapsed,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                        "link":         link,
                    })

        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for #{ch_name}: {e}")

    return results


def build_slack_reminder_text(items: list[dict]) -> str:
    lines = [
        f":outbox_tray: *返信待ち Slack メッセージが {len(items)} 件あります*"
        f"（1日以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        lines.append(
            f"*{i}.* <#{item['channel_id']}> – {item['msg_time_utc']}"
            f"（{item['elapsed_h']}時間経過）\n"
            f"   内容: _{item['text']}…_\n"
            f"   {item['link']}\n"
        )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Gmail: 自分が送った未返信メール
# ══════════════════════════════════════════════════════════════════════════════

def get_gmail_service():
    """Gmail API サービスオブジェクトを返す。認証情報がなければ None を返す。"""
    if not GMAIL_AVAILABLE:
        return None
    if not CREDS_FILE.exists():
        print("[WARN] credentials.json が見つかりません。Gmailチェックをスキップ。")
        print("       Google Cloud Console で OAuth2 クライアントIDを作成し、")
        print(f"       {CREDS_FILE} として保存してください。")
        return None

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return google_build("gmail", "v1", credentials=creds)


def get_my_email(service) -> str:
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def find_unanswered_sent_gmail(service, now_ts: float) -> list[dict]:
    """3日以上返信のない送信済みスレッドを返す。"""
    cutoff_dt = datetime.fromtimestamp(now_ts - GMAIL_THRESHOLD_S, tz=timezone.utc)
    oldest_dt = datetime.fromtimestamp(now_ts - LOOKBACK_S, tz=timezone.utc)

    # Gmail検索クエリ: 送信済みフォルダで指定期間内
    after_str  = oldest_dt.strftime("%Y/%m/%d")
    before_str = cutoff_dt.strftime("%Y/%m/%d")
    query      = f"in:sent after:{after_str} before:{before_str}"
    print(f"[INFO] Gmail: query = {query}")

    my_email = get_my_email(service)
    results  = []
    seen_threads: set[str] = set()  # スレッドの重複処理を避ける

    page_token = None
    while True:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=200, pageToken=page_token)
            .execute()
        )
        messages = resp.get("messages", [])

        for msg_ref in messages:
            thread_id = msg_ref["threadId"]
            if thread_id in seen_threads:
                continue
            seen_threads.add(thread_id)

            # スレッド全体を取得（メタデータのみ）
            thread = (
                service.users()
                .threads()
                .get(
                    userId="me",
                    id=thread_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Date", "Subject"],
                )
                .execute()
            )

            thread_msgs = thread.get("messages", [])
            if not thread_msgs:
                continue

            def get_header(msg, name: str) -> str:
                return next(
                    (h["value"] for h in msg["payload"]["headers"] if h["name"] == name),
                    "",
                )

            # スレッドの最後のメッセージが自分かどうかで「未返信」を判定
            last_msg      = thread_msgs[-1]
            last_from     = get_header(last_msg, "From")
            if my_email.lower() not in last_from.lower():
                # 相手が最後に返信している → 返信済み
                continue

            last_ts = int(last_msg["internalDate"]) / 1000
            if last_ts > now_ts - GMAIL_THRESHOLD_S:
                continue  # まだ3日経っていない

            subject = get_header(last_msg, "Subject") or "(件名なし)"

            # 最初の送信メッセージから宛先を取得
            first_sent = next(
                (
                    m for m in thread_msgs
                    if my_email.lower() in get_header(m, "From").lower()
                ),
                thread_msgs[0],
            )
            to_header = get_header(first_sent, "To") or "unknown"

            sent_dt   = datetime.fromtimestamp(last_ts, tz=timezone.utc)
            elapsed_d = int((now_ts - last_ts) / 86400)
            gmail_url = f"https://mail.google.com/mail/u/0/#all/{thread_id}"

            results.append({
                "subject":   subject[:80],
                "to":        to_header[:80],
                "sent_date": sent_dt.strftime("%Y-%m-%d %H:%M UTC"),
                "elapsed_d": elapsed_d,
                "url":       gmail_url,
            })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def build_gmail_reminder_text(items: list[dict]) -> str:
    lines = [
        f":email: *返信待ち Gmail が {len(items)} 件あります*（3日以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        lines.append(
            f"*{i}.* 件名: _{item['subject']}_\n"
            f"   宛先: {item['to']}\n"
            f"   送信日: {item['sent_date']}（{item['elapsed_d']}日以上経過）\n"
            f"   {item['url']}\n"
        )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# エントリポイント
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時のみ）のためスキップ。")
        return

    print(f"[INFO] Check started at {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    # ── Slack チェック ────────────────────────────────────────────────────────
    slack_items = find_unanswered_sent_slack(now_ts)
    if slack_items:
        print(f"[INFO] Slack: {len(slack_items)} 件の未返信送信メッセージを検出。DMを送信します。")
        send_dm(build_slack_reminder_text(slack_items))
    else:
        print("[INFO] Slack: 返信待ちの送信メッセージなし。")

    # ── Gmail チェック ───────────────────────────────────────────────────────
    gmail_service = get_gmail_service()
    if gmail_service:
        gmail_items = find_unanswered_sent_gmail(gmail_service, now_ts)
        if gmail_items:
            print(f"[INFO] Gmail: {len(gmail_items)} 件の未返信メールを検出。DMを送信します。")
            send_dm(build_gmail_reminder_text(gmail_items))
        else:
            print("[INFO] Gmail: 返信待ちのメールなし。")


if __name__ == "__main__":
    main()
