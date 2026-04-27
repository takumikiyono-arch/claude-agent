#!/usr/bin/env python3
"""
Slack & Gmail 未返信リマインダー
─────────────────────────────────
• Slack : 自分が送ったメッセージで 1 日以上他者から返信がないもの
• Gmail : 自分が送ったメールで  3 日以上他者から返信がないもの
→ 両方の結果を自分の Slack DM にまとめて通知（8〜19 時のみ）

【Gmail 初回セットアップ】
  1. Google Cloud Console で OAuth2 クライアント ID を作成
  2. credentials.json をこのスクリプトと同じディレクトリに配置
  3. 初回は python3 reminder.py を手動実行 → ブラウザ認証 → token.json 生成
  4. 以降は token.json を使って自動実行（有効期限切れ時は自動リフレッシュ）

【環境変数】
  SLACK_BOT_TOKEN   : Slack Bot/User トークン（必須）
  GMAIL_TOKEN_PATH  : token.json のパス（省略時: スクリプトと同ディレクトリ）
  GMAIL_CREDS_PATH  : credentials.json のパス（省略時: スクリプトと同ディレクトリ）
"""

import os
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── 設定 ────────────────────────────────────────────────────────────────────
SLACK_TOKEN           = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID            = "U0973MEH3V0"
SLACK_THRESHOLD_SEC   = 1 * 24 * 60 * 60   # Slack: 1 日
GMAIL_THRESHOLD_DAYS  = 3                   # Gmail: 3 日
LOOKBACK_SEC          = 7 * 24 * 60 * 60   # 最大 7 日前まで遡る
ACTIVE_HOURS          = range(8, 20)        # 8:00〜19:59 のみ実行

_here = os.path.dirname(os.path.abspath(__file__))
GMAIL_TOKEN_PATH = os.environ.get("GMAIL_TOKEN_PATH", os.path.join(_here, "token.json"))
GMAIL_CREDS_PATH = os.environ.get("GMAIL_CREDS_PATH", os.path.join(_here, "credentials.json"))
GMAIL_SCOPES     = ["https://www.googleapis.com/auth/gmail.readonly"]
# ────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ─── Slack ───────────────────────────────────────────────────────────────────

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def others_replied_in_thread(channel: str, thread_ts: str) -> bool:
    """スレッド内に自分以外からの返信が 1 件以上あれば True。"""
    try:
        for page in slack_client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:
                    continue  # 親メッセージは除外
                if msg.get("user") and msg["user"] != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def fetch_joined_channels() -> list[dict]:
    channels = []
    try:
        for page in slack_client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")
    return channels


def find_unanswered_slack_messages(now_ts: float) -> list[dict]:
    """自分が送ったメッセージで 1 日以上他者から返信がないものを返す。"""
    cutoff  = now_ts - SLACK_THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_SEC
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
                    # スレッドの返信は除外（トップレベルメッセージのみ対象）
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    # 自分が送ったメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:
                        continue  # まだ 1 日経っていない

                    if others_replied_in_thread(ch_id, msg["ts"]):
                        continue  # 返信あり → スキップ

                    msg_time = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    elapsed_h = int((now_ts - msg_ts) / 3600)

                    results.append({
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "text":         msg.get("text", "")[:120],
                        "elapsed_h":    elapsed_h,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                    })

        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for #{ch_name}: {e}")

    return results


# ─── Gmail ───────────────────────────────────────────────────────────────────

def get_gmail_service():
    creds = None
    if os.path.exists(GMAIL_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDS_PATH, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def find_unanswered_gmail_messages(now_ts: float) -> list[dict]:
    """送信済みメールで 3 日以上他者から返信がないものを返す。"""
    if not os.path.exists(GMAIL_CREDS_PATH) and not os.path.exists(GMAIL_TOKEN_PATH):
        print("[WARN] Gmail credentials が見つかりません。Gmail チェックをスキップします。")
        print(f"       credentials.json を {GMAIL_CREDS_PATH} に配置してください。")
        return []

    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"[WARN] Gmail 認証失敗: {e}")
        return []

    try:
        profile   = service.users().getProfile(userId="me").execute()
        my_email  = profile["emailAddress"].lower()
    except Exception as e:
        print(f"[WARN] Gmail プロフィール取得失敗: {e}")
        return []

    oldest_dt  = datetime.fromtimestamp(now_ts - LOOKBACK_SEC, tz=timezone.utc)
    after_date = oldest_dt.strftime("%Y/%m/%d")
    query      = f"in:sent after:{after_date}"
    results    = []

    try:
        response = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()
        messages = response.get("messages", [])
    except Exception as e:
        print(f"[WARN] Gmail search failed: {e}")
        return []

    print(f"[INFO] Gmail: {len(messages)} 件の送信メールをスキャン中...")

    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["Subject", "Date", "From", "To"],
            ).execute()

            msg_ts     = int(msg.get("internalDate", 0)) / 1000
            age_days   = (now_ts - msg_ts) / 86400

            if age_days < GMAIL_THRESHOLD_DAYS:
                continue  # まだ 3 日経っていない
            if age_days > 7:
                continue  # 7 日超は対象外

            thread_id = msg.get("threadId")
            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="metadata",
                metadataHeaders=["From"],
            ).execute()

            # 自分以外からのメッセージが 1 件でもあれば返信あり
            has_reply = any(
                my_email not in {
                    h["value"].lower()
                    for h in tm.get("payload", {}).get("headers", [])
                    if h["name"] == "From"
                }
                for tm in thread.get("messages", [])
            )
            if has_reply:
                continue

            headers_map = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            subject   = headers_map.get("Subject", "(件名なし)")
            to_addr   = headers_map.get("To", "")
            msg_time  = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
            elapsed_d = int(age_days)

            results.append({
                "subject":   subject[:80],
                "to":        to_addr[:80],
                "elapsed_d": elapsed_d,
                "msg_time":  msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                "thread_id": thread_id,
            })

        except Exception as e:
            print(f"[WARN] Gmail メッセージ処理失敗: {e}")

    return results


# ─── リマインド送信 ───────────────────────────────────────────────────────────

def build_reminder_text(slack_items: list[dict], gmail_items: list[dict]) -> str:
    lines = [":bell: *未返信リマインダー*\n"]

    if slack_items:
        lines.append(f"*【Slack】{len(slack_items)} 件 ― 1 日以上返信なし*")
        for i, item in enumerate(slack_items, 1):
            link = (
                f"https://slack.com/archives/{item['channel_id']}"
                f"/p{item['ts'].replace('.', '')}"
            )
            lines.append(
                f"*{i}.* <#{item['channel_id']}> — {item['msg_time_utc']}"
                f"（{item['elapsed_h']} 時間前）\n"
                f"   内容: _{item['text']}…_\n"
                f"   {link}\n"
            )
    else:
        lines.append("*【Slack】* 未返信なし :white_check_mark:\n")

    if gmail_items:
        lines.append(f"*【Gmail】{len(gmail_items)} 件 ― 3 日以上返信なし*")
        for i, item in enumerate(gmail_items, 1):
            lines.append(
                f"*{i}.* 件名: _{item['subject']}_\n"
                f"   宛先: {item['to']}\n"
                f"   送信: {item['msg_time']}（{item['elapsed_d']} 日以上前）\n"
            )
    else:
        lines.append("*【Gmail】* 未返信なし :white_check_mark:\n")

    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour} 時 — 実行時間外（8〜19 時のみ）のためスキップ。")
        return

    print(f"[INFO] チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    slack_items = find_unanswered_slack_messages(now_ts)
    gmail_items = find_unanswered_gmail_messages(now_ts)

    if not slack_items and not gmail_items:
        print("[INFO] 未対応メッセージなし。リマインドは送りません。")
        return

    print(f"[INFO] Slack: {len(slack_items)} 件 / Gmail: {len(gmail_items)} 件 を検出。DM 送信中...")
    reminder = build_reminder_text(slack_items, gmail_items)
    send_dm(reminder)


if __name__ == "__main__":
    main()
