#!/usr/bin/env python3
"""
Pending Reply Reminder
----------------------
Slack : 自分が送ったメッセージで 1 日以上返信のないものを自分の DM でリマインド。
Gmail : 自分が送ったメールで 3 日以上返信のないものを Slack DM でリマインド。

必要な環境変数:
  SLACK_BOT_TOKEN   - xoxp-... or xoxb-... トークン
オプション:
  GMAIL_TOKEN_PATH       - Gmail OAuth トークンファイルのパス (default: ./gmail_token.json)
  GMAIL_CREDENTIALS_PATH - Google Console から発行した credentials.json のパス (default: ./gmail_credentials.json)
"""

import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN         = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID          = "U0973MEH3V0"
SLACK_THRESHOLD_SEC = 1 * 24 * 60 * 60    # 1 日
GMAIL_THRESHOLD_SEC = 3 * 24 * 60 * 60    # 3 日
LOOKBACK_SEC        = 7 * 24 * 60 * 60    # 過去 7 日を対象
SCRIPT_DIR          = Path(__file__).parent

GMAIL_TOKEN_PATH       = Path(os.environ.get("GMAIL_TOKEN_PATH",       SCRIPT_DIR / "gmail_token.json"))
GMAIL_CREDENTIALS_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", SCRIPT_DIR / "gmail_credentials.json"))
GMAIL_SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
# ─────────────────────────────────────────────────────────────────────────────

# 返信を求めていると判断するキーワードパターン
_RESPONSE_RE = re.compile(
    r"[?？]"
    r"|確認|教えて|いかがでしょう|よろしいでしょう|いかがですか|よろしいですか"
    r"|お願い|できますか|ご回答|お返事|ご確認|承認|いただけますか"
    r"|お知らせ|ご連絡|ご意見|どうでしょう|どう思|どちら|いつまで"
    r"|could you|please reply|let me know|thoughts|feedback"
    r"|please review|please approve|please confirm|LGTM|wdyt",
    re.IGNORECASE,
)

slack_client = WebClient(token=SLACK_TOKEN)


def needs_response(text: str) -> bool:
    return bool(_RESPONSE_RE.search(text))


def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


# ── Slack ─────────────────────────────────────────────────────────────────────

def _thread_has_reply_from_others(channel: str, thread_ts: str) -> bool:
    """自分以外が当該スレッドに返信しているか確認する。"""
    try:
        for page in slack_client.conversations_replies(channel=channel, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:
                    continue  # 親メッセージ自身はスキップ
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


def _fetch_all_channels() -> list[dict]:
    channels = []
    try:
        for page in slack_client.conversations_list(
            types="public_channel,private_channel,im,mpim",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list: {e}")
    return channels


def check_slack_sent(now_ts: float) -> list[dict]:
    """
    自分が投稿したトップレベルメッセージのうち:
      - SLACK_THRESHOLD_SEC 以上前に送った
      - 返信を求めている内容である
      - 自分以外からの返信がまだない
    を返す。
    """
    cutoff = now_ts - SLACK_THRESHOLD_SEC
    oldest = now_ts - LOOKBACK_SEC
    pending = []

    channels = _fetch_all_channels()
    print(f"[Slack] {len(channels)} チャンネル/DM をスキャン中...")

    for ch in channels:
        ch_id   = ch["id"]
        ch_name = ch.get("name") or ch_id
        try:
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # 自分が送ったトップレベルメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue  # 自分の返信はスキップ

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:
                        continue  # まだ閾値未達

                    text = msg.get("text", "")
                    if not needs_response(text):
                        continue

                    if _thread_has_reply_from_others(ch_id, msg["ts"]):
                        continue  # 既に返信あり

                    elapsed_h = int((now_ts - msg_ts) / 3600)
                    msg_time  = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    pending.append({
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "text":         text[:120],
                        "elapsed_h":    elapsed_h,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                    })
        except SlackApiError as e:
            print(f"[WARN] conversations_history #{ch_name}: {e}")

    return pending


# ── Gmail ─────────────────────────────────────────────────────────────────────

def _get_gmail_service():
    """保存済み OAuth トークンから Gmail API サービスを構築して返す。"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        print("[WARN] google-api-python-client がインストールされていません。Gmail チェックをスキップします。")
        return None, None

    creds = None
    if GMAIL_TOKEN_PATH.exists():
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_PATH), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            GMAIL_TOKEN_PATH.write_text(creds.to_json())
        else:
            print(
                "[WARN] Gmail の認証情報が設定されていません。"
                "gmail_setup.py を一度実行して認証を完了させてください。"
            )
            return None, None

    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds)

    # 自分のメールアドレスを取得
    profile   = service.users().getProfile(userId="me").execute()
    my_email  = profile.get("emailAddress", "").lower()
    return service, my_email


def _thread_has_external_reply(service, thread_id: str, sent_msg_id: str, my_email: str) -> bool:
    """スレッドに自分以外からの返信があるか確認する。"""
    thread = service.users().threads().get(
        userId="me", id=thread_id, format="metadata",
        metadataHeaders=["From"],
    ).execute()
    for msg in thread.get("messages", []):
        if msg["id"] == sent_msg_id:
            continue
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        sender  = headers.get("From", "").lower()
        if my_email not in sender:
            return True
    return False


def check_gmail_sent(now_ts: float) -> list[dict]:
    """
    送信済みメールのうち:
      - GMAIL_THRESHOLD_SEC 以上前に送った (かつ LOOKBACK_SEC 以内)
      - 返信を求めている内容である
      - 自分以外からの返信がまだスレッドにない
    を返す。
    """
    service, my_email = _get_gmail_service()
    if not service:
        return []

    # Gmail 検索: 送信済み かつ 3〜7日前
    threshold_days = int(GMAIL_THRESHOLD_SEC / 86400)
    lookback_days  = int(LOOKBACK_SEC        / 86400)
    query = f"in:sent older_than:{threshold_days}d newer_than:{lookback_days}d"

    pending = []
    try:
        result   = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
        messages = result.get("messages", [])
        print(f"[Gmail] {len(messages)} 件の送信メッセージを確認中...")

        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["Subject", "Date", "To"],
            ).execute()

            headers  = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject  = headers.get("Subject", "(件名なし)")
            to       = headers.get("To", "")
            date_str = headers.get("Date", "")
            snippet  = msg.get("snippet", "")
            thread_id = msg.get("threadId")

            if not needs_response(subject + " " + snippet):
                continue

            if _thread_has_external_reply(service, thread_id, msg_ref["id"], my_email):
                continue

            try:
                sent_dt = parsedate_to_datetime(date_str)
                if sent_dt.tzinfo is None:
                    sent_dt = sent_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            elapsed_days = (datetime.now(timezone.utc) - sent_dt).days
            pending.append({
                "subject":      subject,
                "to":           to[:80],
                "sent_at":      sent_dt.strftime("%Y-%m-%d %H:%M UTC"),
                "elapsed_days": elapsed_days,
                "snippet":      snippet[:120],
            })

    except Exception as e:
        print(f"[WARN] Gmail チェック失敗: {e}")

    return pending


# ── リマインドメッセージ生成 ─────────────────────────────────────────────────

def _build_reminder_text(slack_items: list[dict], gmail_items: list[dict]) -> str:
    lines = [":bell: *返信待ちリマインダー*\n"]

    if slack_items:
        lines.append(f":slack: *Slack — {len(slack_items)} 件（1日以上未返信）*")
        for i, item in enumerate(slack_items, 1):
            link = (
                f"https://slack.com/archives/{item['channel_id']}"
                f"/p{item['ts'].replace('.', '')}"
            )
            lines.append(
                f"*{i}.* <#{item['channel_id']}> — {item['msg_time_utc']}"
                f"（約 {item['elapsed_h']} 時間経過）\n"
                f"   内容: _{item['text'][:100]}_\n"
                f"   {link}"
            )

    if gmail_items:
        if slack_items:
            lines.append("")
        lines.append(f":email: *Gmail — {len(gmail_items)} 件（3日以上未返信）*")
        for i, item in enumerate(gmail_items, 1):
            lines.append(
                f"*{i}.* 件名: *{item['subject']}*\n"
                f"   宛先: {item['to']}\n"
                f"   送信日時: {item['sent_at']}（約 {item['elapsed_days']} 日経過）\n"
                f"   プレビュー: _{item['snippet'][:100]}_"
            )

    return "\n".join(lines)


def _send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


# ── メイン ────────────────────────────────────────────────────────────────────

def main() -> None:
    now_ts = time.time()
    print(f"[INFO] チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    slack_pending = check_slack_sent(now_ts)
    gmail_pending = check_gmail_sent(now_ts)

    if not slack_pending and not gmail_pending:
        print("[INFO] 返信待ちなし。リマインドは送りません。")
        return

    print(f"[INFO] Slack: {len(slack_pending)} 件, Gmail: {len(gmail_pending)} 件 — DM を送信します。")
    reminder = _build_reminder_text(slack_pending, gmail_pending)
    _send_dm(reminder)


if __name__ == "__main__":
    main()
