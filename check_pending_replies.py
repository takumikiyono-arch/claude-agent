#!/usr/bin/env python3
"""
Pending Reply Reminder
----------------------
Slack で自分が送ったメッセージで1日以上未返信のもの、
Gmail で自分が送ったメールで3日以上未返信のものを検出し、
Slack DM でリマインドを送る。

必須環境変数:
  SLACK_BOT_TOKEN        Slack User OAuth token (xoxp-...) または Bot token
任意環境変数:
  GMAIL_TOKEN_FILE       Gmail token.json のパス (デフォルト: ~/.gmail_token.json)
  GMAIL_CREDENTIALS_FILE Gmail credentials.json のパス (初回認証用)
  GMAIL_MY_EMAIL         自分のGmailアドレス (省略時はラベルで判定)
"""

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN     = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID      = "U0973MEH3V0"
MY_EMAIL        = os.environ.get("GMAIL_MY_EMAIL", "")

SLACK_THRESHOLD_SEC = 1 * 24 * 60 * 60   # Slack: 1日
GMAIL_THRESHOLD_SEC = 3 * 24 * 60 * 60   # Gmail: 3日
LOOKBACK_DAYS       = 14                  # 過去14日分を対象にするか
ACTIVE_HOURS        = range(8, 20)        # 8:00〜19:59 のみ実行

GMAIL_TOKEN_FILE       = os.environ.get("GMAIL_TOKEN_FILE",
                             str(Path.home() / ".gmail_token.json"))
GMAIL_CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE",
                             str(Path.home() / ".gmail_credentials.json"))
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ════════════════════════════════════════════════════════════
#  Slack
# ════════════════════════════════════════════════════════════

def fetch_joined_channels() -> list[dict]:
    channels = []
    for ch_type in ("public_channel,private_channel", "im,mpim"):
        try:
            for page in slack_client.conversations_list(
                types=ch_type,
                exclude_archived=True,
                limit=200,
            ):
                channels.extend(page["channels"])
        except SlackApiError as e:
            print(f"[WARN] conversations_list({ch_type}) 失敗: {e}")
    return channels


def others_replied_in_thread(channel: str, thread_ts: str) -> bool:
    """スレッドに自分以外の返信があるか確認"""
    try:
        for page in slack_client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:
                    continue
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def dm_has_reply_after(channel: str, after_ts: float, now_ts: float) -> bool:
    """DMチャンネルで after_ts より後に相手からのメッセージがあるか確認"""
    try:
        for page in slack_client.conversations_history(
            channel=channel,
            oldest=str(after_ts + 0.001),
            latest=str(now_ts),
            limit=20,
        ):
            for msg in page["messages"]:
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def find_slack_sent_awaiting_reply(now_ts: float) -> list[dict]:
    """自分が送ったメッセージで1日以上未返信のものを返す"""
    threshold = now_ts - SLACK_THRESHOLD_SEC
    oldest    = now_ts - (LOOKBACK_DAYS * 86400)
    unanswered = []

    channels = fetch_joined_channels()
    print(f"[INFO] Slack: {len(channels)} チャンネルをスキャン中...")

    # DM は1チャンネルあたり最新の未返信メッセージだけを報告（重複防止）
    dm_flagged: set[str] = set()

    for ch in channels:
        ch_id   = ch["id"]
        is_im   = ch.get("is_im", False) or ch.get("is_mpim", False)
        ch_name = ch.get("name") or (f"DM:{ch.get('user', ch_id)}" if is_im else ch_id)

        # DM で既に報告済みのチャンネルはスキップ
        if is_im and ch_id in dm_flagged:
            continue

        try:
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # スレッドの返信は除外（トップレベルのみ対象）
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    # 自分が送ったメッセージのみ
                    if msg.get("user") != MY_USER_ID:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > threshold:
                        continue  # まだ1日経過していない

                    # スレッドに他の人の返信があればスキップ
                    if msg.get("reply_count", 0) > 0:
                        if others_replied_in_thread(ch_id, msg["ts"]):
                            continue

                    # DM の場合: このメッセージより後に相手からの返信があればスキップ
                    if is_im:
                        if dm_has_reply_after(ch_id, msg_ts, now_ts):
                            dm_flagged.add(ch_id)
                            continue

                    elapsed_h = int((now_ts - msg_ts) / 3600)
                    msg_time_jst = (
                        datetime.fromtimestamp(msg_ts, tz=timezone.utc) + timedelta(hours=9)
                    ).strftime("%Y-%m-%d %H:%M JST")

                    unanswered.append({
                        "channel_id":   ch_id,
                        "channel_name": f"#{ch_name}" if not is_im else f"DM ({ch_name})",
                        "ts":           msg["ts"],
                        "text":         msg.get("text", "")[:120],
                        "elapsed_h":    elapsed_h,
                        "msg_time_jst": msg_time_jst,
                    })

                    if is_im:
                        dm_flagged.add(ch_id)

        except SlackApiError as e:
            print(f"[WARN] #{ch_name} のスキャン失敗: {e}")

    return unanswered


# ════════════════════════════════════════════════════════════
#  Gmail
# ════════════════════════════════════════════════════════════

def get_gmail_service():
    """Gmail API サービスオブジェクトを返す。認証情報がなければ None を返す"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("[WARN] google-api-python-client 未インストール。Gmail チェックをスキップ。")
        print("       pip install google-api-python-client google-auth-oauthlib でインストール可能。")
        return None

    creds = None
    token_path = Path(GMAIL_TOKEN_FILE)
    creds_path = Path(GMAIL_CREDENTIALS_FILE)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif creds_path.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            print(f"[WARN] Gmail 認証情報が見つかりません ({GMAIL_CREDENTIALS_FILE})。")
            print("       setup_gmail_auth.py を実行して認証してください。")
            return None

        with open(token_path, "w") as f:
            f.write(creds.to_json())

    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def find_gmail_sent_awaiting_reply(now_ts: float) -> list[dict]:
    """自分が送ったメールで3日以上未返信のものを返す"""
    service = get_gmail_service()
    if not service:
        return []

    # Gmail 日付検索: LOOKBACK_DAYS 日以内かつ GMAIL_THRESHOLD_SEC 以上前に送ったもの
    oldest_dt    = datetime.fromtimestamp(now_ts - (LOOKBACK_DAYS * 86400), tz=timezone.utc)
    threshold_dt = datetime.fromtimestamp(now_ts - GMAIL_THRESHOLD_SEC, tz=timezone.utc)
    query = (
        f"in:sent "
        f"after:{oldest_dt.strftime('%Y/%m/%d')} "
        f"before:{threshold_dt.strftime('%Y/%m/%d')}"
    )

    unanswered = []
    try:
        page_token = None
        while True:
            result = service.users().threads().list(
                userId="me",
                q=query,
                maxResults=50,
                pageToken=page_token,
            ).execute()

            for thread_info in result.get("threads", []):
                thread = service.users().threads().get(
                    userId="me",
                    id=thread_info["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()

                messages = thread.get("messages", [])
                if not messages:
                    continue

                # スレッドの最後のメッセージが自分が送ったものか確認
                last_msg     = messages[-1]
                last_labels  = last_msg.get("labelIds", [])
                last_headers = {
                    h["name"]: h["value"]
                    for h in last_msg.get("payload", {}).get("headers", [])
                }
                last_from = last_headers.get("From", "")

                # 最後のメッセージが相手から来ていれば返信済み → スキップ
                if MY_EMAIL and MY_EMAIL.lower() not in last_from.lower():
                    continue
                if not MY_EMAIL and "SENT" not in last_labels:
                    continue

                # 最初の自分の送信メッセージの情報を取得
                first_sent = next(
                    (m for m in messages if "SENT" in m.get("labelIds", [])),
                    None
                )
                if not first_sent:
                    continue

                sent_ts_ms = int(first_sent.get("internalDate", 0))
                sent_ts    = sent_ts_ms / 1000
                if sent_ts > now_ts - GMAIL_THRESHOLD_SEC:
                    continue  # まだ3日経過していない

                first_headers = {
                    h["name"]: h["value"]
                    for h in first_sent.get("payload", {}).get("headers", [])
                }
                subject   = first_headers.get("Subject", "(件名なし)")
                to_addr   = first_headers.get("To", "")
                elapsed_d = int((now_ts - sent_ts) / 86400)
                sent_jst  = (
                    datetime.fromtimestamp(sent_ts, tz=timezone.utc) + timedelta(hours=9)
                ).strftime("%Y-%m-%d %H:%M JST")

                unanswered.append({
                    "subject":   subject[:80],
                    "to":        to_addr[:80],
                    "sent_jst":  sent_jst,
                    "elapsed_d": elapsed_d,
                })

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    except Exception as e:
        print(f"[WARN] Gmail API エラー: {e}")

    return unanswered


# ════════════════════════════════════════════════════════════
#  DM 送信
# ════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def build_reminder_text(slack_items: list[dict], gmail_items: list[dict]) -> str:
    lines = [":bell: *未返信リマインド*\n"]

    if slack_items:
        lines.append(f"*【Slack】{len(slack_items)} 件 — 1日以上未返信*")
        for i, item in enumerate(slack_items, 1):
            link = (
                f"https://slack.com/archives/{item['channel_id']}"
                f"/p{item['ts'].replace('.', '')}"
            )
            lines.append(
                f"*{i}.* {item['channel_name']} — {item['msg_time_jst']}"
                f"（{item['elapsed_h']} 時間経過）\n"
                f"   内容: _{item['text']}…_\n"
                f"   {link}"
            )
        lines.append("")

    if gmail_items:
        lines.append(f"*【Gmail】{len(gmail_items)} 件 — 3日以上未返信*")
        for i, item in enumerate(gmail_items, 1):
            lines.append(
                f"*{i}.* 件名: _{item['subject']}_\n"
                f"   宛先: {item['to']}\n"
                f"   送信: {item['sent_jst']}（{item['elapsed_d']} 日経過）"
            )

    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


# ════════════════════════════════════════════════════════════
#  メイン
# ════════════════════════════════════════════════════════════

def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour} 時 — 実行時間外（8〜19時のみ）のためスキップ。")
        return

    print(f"[INFO] チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    slack_items = find_slack_sent_awaiting_reply(now_ts)
    gmail_items = find_gmail_sent_awaiting_reply(now_ts)

    if not slack_items and not gmail_items:
        print("[INFO] 未返信なし。リマインドは送りません。")
        return

    print(f"[INFO] Slack: {len(slack_items)} 件, Gmail: {len(gmail_items)} 件 検出。DM 送信中...")
    send_dm(build_reminder_text(slack_items, gmail_items))


if __name__ == "__main__":
    main()
