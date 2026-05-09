#!/usr/bin/env python3
"""
Unanswered Sent Messages Reminder
----------------------------------
- Slack: 自分が送ったメッセージに1日以上返信がないものを検出
- Gmail: 自分が送ったメールに3日以上返信がないものを検出
新規の未返信のみ（重複通知なし）自分のSlack DMへ通知する。

Gmail初回セットアップ:
  python check_unanswered_sent.py --setup-gmail
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

# ── 設定 ─────────────────────────────────────────────────────────────────────
SLACK_TOKEN          = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID           = "U0973MEH3V0"
SLACK_THRESHOLD_SEC  = 24 * 60 * 60   # 1日
GMAIL_THRESHOLD_DAYS = 3              # 3日
LOOKBACK_DAYS        = 7             # 7日前まで遡る
ACTIVE_HOURS         = range(8, 20)  # 8:00〜19:59 のみ実行
STATE_EXPIRE_DAYS    = 14            # 通知済み記録の保持期間

SCRIPT_DIR        = Path(__file__).parent
GMAIL_CREDENTIALS = SCRIPT_DIR / "gmail_credentials.json"
GMAIL_TOKEN       = SCRIPT_DIR / "gmail_token.json"
GMAIL_SCOPES      = ["https://www.googleapis.com/auth/gmail.readonly"]
STATE_FILE        = SCRIPT_DIR / "notified_sent_state.json"
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
# 通知済み状態管理（重複通知防止）
# ══════════════════════════════════════════════════════════════════════════════

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"slack": {}, "gmail": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def clean_expired(state: dict) -> dict:
    expire_cutoff = (datetime.now(timezone.utc) - timedelta(days=STATE_EXPIRE_DAYS)).isoformat()
    state["slack"] = {k: v for k, v in state["slack"].items() if v > expire_cutoff}
    state["gmail"] = {k: v for k, v in state["gmail"].items() if v > expire_cutoff}
    return state


# ══════════════════════════════════════════════════════════════════════════════
# Slack: 自分が送ったメッセージへの未返信を検出
# ══════════════════════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def fetch_all_conversations() -> list[dict]:
    convs = []
    try:
        for page in slack_client.conversations_list(
            types="public_channel,private_channel,im,mpim",
            exclude_archived=True,
        ):
            convs.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list failed: {e}")
    return convs


def others_replied(channel: str, thread_ts: str) -> bool:
    """スレッドに自分以外からの返信があるか確認"""
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


def find_slack_unanswered(now_ts: float, notified: dict) -> list[dict]:
    """自分が送ったメッセージのうち1日以上返信のないものを返す"""
    cutoff  = now_ts - SLACK_THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_DAYS * 24 * 3600
    results = []

    conversations = fetch_all_conversations()
    print(f"[Slack] {len(conversations)} 件の会話をスキャン中...")

    for conv in conversations:
        conv_id   = conv["id"]
        conv_name = conv.get("name") or conv.get("user") or conv_id

        try:
            for page in slack_client.conversations_history(
                channel=conv_id,
                oldest=str(oldest),
                latest=str(now_ts),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # スレッド返信はスキップ（トップレベルメッセージのみ対象）
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue
                    if msg.get("user") != MY_USER_ID:
                        continue

                    msg_ts = float(msg["ts"])
                    if msg_ts > cutoff:
                        continue  # まだ1日経っていない

                    state_key = f"{conv_id}:{msg['ts']}"
                    if state_key in notified:
                        continue  # 既に通知済み

                    if others_replied(conv_id, msg["ts"]):
                        continue  # 返信あり

                    elapsed_h = int((now_ts - msg_ts) / 3600)
                    results.append({
                        "conv_id":   conv_id,
                        "conv_name": conv_name,
                        "ts":        msg["ts"],
                        "text":      msg.get("text", "")[:120],
                        "elapsed_h": elapsed_h,
                        "msg_time":  datetime.fromtimestamp(msg_ts, tz=timezone.utc).strftime(
                            "%Y-%m-%d %H:%M UTC"
                        ),
                        "link":      (
                            f"https://slack.com/archives/{conv_id}"
                            f"/p{msg['ts'].replace('.', '')}"
                        ),
                        "state_key": state_key,
                    })

        except SlackApiError as e:
            print(f"[WARN] conversations_history #{conv_name}: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Gmail: 自分が送ったメールへの未返信を検出
# ══════════════════════════════════════════════════════════════════════════════

def get_gmail_service():
    if not GMAIL_AVAILABLE:
        print("[WARN] google-api-python-client 未インストール。Gmail をスキップします。")
        return None
    if not GMAIL_CREDENTIALS.exists():
        print(f"[WARN] {GMAIL_CREDENTIALS} がありません。Gmail をスキップします。")
        print("       セットアップ方法: python check_unanswered_sent.py --setup-gmail")
        return None

    creds = None
    if GMAIL_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            GMAIL_TOKEN.write_text(creds.to_json())
        else:
            print("[WARN] Gmail 未認証。'python check_unanswered_sent.py --setup-gmail' を実行してください。")
            return None

    return build("gmail", "v1", credentials=creds)


def setup_gmail_auth() -> None:
    """初回のみ：ブラウザ経由でOAuth2認証を行いトークンを保存する"""
    if not GMAIL_CREDENTIALS.exists():
        print(f"エラー: {GMAIL_CREDENTIALS} が見つかりません。")
        print("Google Cloud Console で Gmail API を有効化し、")
        print("OAuth2 クライアント ID（デスクトップアプリ）をダウンロードして")
        print(f"{GMAIL_CREDENTIALS} として保存してください。")
        sys.exit(1)

    flow  = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDENTIALS), GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)
    GMAIL_TOKEN.write_text(creds.to_json())
    print(f"[OK] Gmail 認証完了。{GMAIL_TOKEN} にトークンを保存しました。")


def find_gmail_unanswered(service, notified: dict) -> list[dict]:
    """送信済みメールのうち3日以上返信のないスレッドを返す"""
    if service is None:
        return []

    now       = datetime.now(timezone.utc)
    oldest    = now - timedelta(days=LOOKBACK_DAYS)
    threshold = now - timedelta(days=GMAIL_THRESHOLD_DAYS)

    # 送信から GMAIL_THRESHOLD_DAYS〜LOOKBACK_DAYS 日前のスレッドを検索
    query = (
        f"in:sent "
        f"after:{oldest.strftime('%Y/%m/%d')} "
        f"before:{threshold.strftime('%Y/%m/%d')}"
    )

    results = []
    try:
        profile  = service.users().getProfile(userId="me").execute()
        my_email = profile["emailAddress"].lower()

        response = service.users().threads().list(
            userId="me", q=query, maxResults=100
        ).execute()

        threads = response.get("threads", [])
        print(f"[Gmail] {len(threads)} 件のスレッドをチェック中...")

        for t_meta in threads:
            thread_id = t_meta["id"]
            if thread_id in notified:
                continue

            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="metadata",
                metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
            ).execute()

            messages = thread.get("messages", [])
            if not messages:
                continue

            subject      = ""
            last_sent_ts = None
            has_reply    = False

            for msg in messages:
                hdrs = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                from_hdr    = hdrs.get("From", "").lower()
                to_cc_hdr   = (hdrs.get("To", "") + " " + hdrs.get("Cc", "")).lower()
                subject     = hdrs.get("Subject", subject) or subject
                internal_ts = int(msg.get("internalDate", 0)) / 1000

                if my_email in from_hdr:
                    if last_sent_ts is None or internal_ts > last_sent_ts:
                        last_sent_ts = internal_ts
                else:
                    # 自分の最後の送信より後に来た相手からの返信
                    if my_email in to_cc_hdr and last_sent_ts and internal_ts > last_sent_ts:
                        has_reply = True
                        break

            if has_reply or last_sent_ts is None:
                continue

            sent_dt   = datetime.fromtimestamp(last_sent_ts, tz=timezone.utc)
            elapsed_d = (now - sent_dt).days

            results.append({
                "thread_id": thread_id,
                "subject":   subject or "(件名なし)",
                "snippet":   thread.get("snippet", "")[:120],
                "elapsed_d": elapsed_d,
                "sent_date": sent_dt.strftime("%Y-%m-%d"),
                "link":      f"https://mail.google.com/mail/u/0/#inbox/{thread_id}",
            })

    except Exception as e:
        print(f"[WARN] Gmail エラー: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# DM 通知文の生成・送信
# ══════════════════════════════════════════════════════════════════════════════

def build_slack_section(items: list[dict]) -> str:
    lines = [f":speech_balloon: *Slack 未返信: {len(items)} 件*（送信から1日以上経過）\n"]
    for i, it in enumerate(items, 1):
        lines.append(
            f"*{i}.* {it['msg_time']}（{it['elapsed_h']}時間経過）\n"
            f"   会話: `{it['conv_name']}`\n"
            f"   内容: _{it['text']}_\n"
            f"   <{it['link']}|メッセージを開く>\n"
        )
    return "\n".join(lines)


def build_gmail_section(items: list[dict]) -> str:
    lines = [f":envelope: *Gmail 未返信: {len(items)} 件*（送信から3日以上経過）\n"]
    for i, it in enumerate(items, 1):
        lines.append(
            f"*{i}.* {it['sent_date']}（{it['elapsed_d']}日経過）\n"
            f"   件名: _{it['subject']}_\n"
            f"   概要: {it['snippet']}\n"
            f"   <{it['link']}|メールを開く>\n"
        )
    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


# ══════════════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if "--setup-gmail" in sys.argv:
        setup_gmail_auth()
        return

    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外のためスキップ。")
        return

    print(f"[INFO] チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    state = clean_expired(load_state())

    # Slack: 自分の送信メッセージへの未返信チェック
    slack_items = find_slack_unanswered(now_ts, state["slack"])
    print(f"[Slack] 新規未返信: {len(slack_items)} 件")

    # Gmail: 送信メールへの未返信チェック
    gmail_service = get_gmail_service()
    gmail_items   = find_gmail_unanswered(gmail_service, state["gmail"])
    print(f"[Gmail] 新規未返信: {len(gmail_items)} 件")

    sections = []
    if slack_items:
        sections.append(build_slack_section(slack_items))
    if gmail_items:
        sections.append(build_gmail_section(gmail_items))

    if not sections:
        print("[INFO] 新規の未返信なし。リマインドは送りません。")
        return

    send_dm("\n\n".join(sections))

    now_iso = datetime.now(timezone.utc).isoformat()
    for it in slack_items:
        state["slack"][it["state_key"]] = now_iso
    for it in gmail_items:
        state["gmail"][it["thread_id"]] = now_iso
    save_state(state)


if __name__ == "__main__":
    main()
