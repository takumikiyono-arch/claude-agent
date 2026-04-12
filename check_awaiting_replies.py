#!/usr/bin/env python3
"""
Awaiting Reply Reminder
-----------------------
Slack : 自分が送った投稿・DMに 1日以上返信がない → 自分宛 Slack DM でリマインド
Gmail : 自分が送ったメールに 3日以上返信がない → 自分宛 Slack DM でリマインド
"""

import os
import time
from datetime import datetime, timezone, timedelta
from email.utils import parseaddr

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN          = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID           = "U0973MEH3V0"

# Slack: 1日返信なし → リマインド
SLACK_THRESHOLD_SEC  = 1 * 24 * 60 * 60   # 1日
LOOKBACK_SEC         = 7 * 24 * 60 * 60   # 7日間をスキャン対象

# Gmail: 3日返信なし → リマインド
GMAIL_THRESHOLD_DAYS = 3
GMAIL_LOOKBACK_DAYS  = 14                  # 最大 14日前まで遡る

GMAIL_TOKEN_FILE     = os.environ.get("GMAIL_TOKEN_FILE",
                                      os.path.join(os.path.dirname(__file__), "gmail_token.json"))
GMAIL_SCOPES         = ["https://www.googleapis.com/auth/gmail.readonly"]

ACTIVE_HOURS         = range(8, 20)        # 8:00〜19:59 のみ実行
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
# Slack ユーティリティ
# ══════════════════════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] Slack DM を送信しました。")


def fetch_joined_channels() -> list[dict]:
    channels = []
    try:
        for page in slack_client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list (チャンネル) 失敗: {e}")
    return channels


def fetch_dm_conversations() -> list[dict]:
    """IM (1対1 DM) と MPIM (グループ DM) を返す。"""
    dms = []
    try:
        for page in slack_client.conversations_list(
            types="im,mpim",
            exclude_archived=True,
        ):
            dms.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list (DM) 失敗: {e}")
    return dms


def has_reply_from_others(channel_id: str, thread_ts: str) -> bool:
    """スレッドに自分以外のユーザーの返信があれば True。"""
    try:
        for page in slack_client.conversations_replies(channel=channel_id, ts=thread_ts):
            for msg in page["messages"]:
                if msg.get("ts") == thread_ts:
                    continue  # 親メッセージはスキップ
                if msg.get("user") != MY_USER_ID:
                    return True
    except SlackApiError:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Slack チェック: チャンネル投稿
# ══════════════════════════════════════════════════════════════════════════════

def check_channels_for_awaiting(now_ts: float) -> list[dict]:
    """
    参加チャンネルを走査し、自分が送ったトップレベル投稿で
    SLACK_THRESHOLD_SEC 以上返信がないものを返す。
    """
    cutoff_old = now_ts - SLACK_THRESHOLD_SEC   # これより古いものが対象
    oldest     = now_ts - LOOKBACK_SEC
    unanswered = []

    channels = fetch_joined_channels()
    print(f"[Slack:チャンネル] {len(channels)} チャンネルをスキャン中...")

    for ch in channels:
        ch_id   = ch["id"]
        ch_name = ch.get("name", ch_id)
        try:
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(cutoff_old),
                inclusive=True,
                limit=200,
            ):
                for msg in page["messages"]:
                    # 自分のトップレベルメッセージだけ対象
                    if msg.get("user") != MY_USER_ID:
                        continue
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue  # スレッド返信はスキップ

                    # 他の誰かが返信済みか確認
                    reply_count = msg.get("reply_count", 0)
                    if reply_count > 0 and has_reply_from_others(ch_id, msg["ts"]):
                        continue  # 既に返信あり

                    msg_ts    = float(msg["ts"])
                    elapsed_h = int((now_ts - msg_ts) / 3600)
                    msg_time  = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
                    ts_link   = msg["ts"].replace(".", "")

                    unanswered.append({
                        "source":       "channel",
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "ts_link":      ts_link,
                        "text":         msg.get("text", "")[:120],
                        "elapsed_h":    elapsed_h,
                        "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                    })
        except SlackApiError as e:
            print(f"[WARN] conversations_history 失敗 #{ch_name}: {e}")

    return unanswered


# ══════════════════════════════════════════════════════════════════════════════
# Slack チェック: DM
# ══════════════════════════════════════════════════════════════════════════════

def check_dms_for_awaiting(now_ts: float) -> list[dict]:
    """
    DM・グループ DM を走査し、自分の最後のメッセージから
    SLACK_THRESHOLD_SEC 以上返信がない会話を返す。
    """
    oldest     = now_ts - LOOKBACK_SEC
    unanswered = []

    dms = fetch_dm_conversations()
    print(f"[Slack:DM] {len(dms)} 件の DM 会話をスキャン中...")

    for dm in dms:
        dm_id   = dm["id"]
        dm_name = dm.get("name") or dm.get("user", dm_id)
        try:
            messages = []
            for page in slack_client.conversations_history(
                channel=dm_id,
                oldest=str(oldest),
                latest=str(now_ts),
                limit=50,
            ):
                messages.extend(page["messages"])

            if not messages:
                continue

            # Slack API は新しい順で返す → messages[0] が最新
            last_msg = messages[0]
            if last_msg.get("user") != MY_USER_ID:
                continue  # 相手が最後に返信済み

            msg_ts = float(last_msg["ts"])
            if (now_ts - msg_ts) < SLACK_THRESHOLD_SEC:
                continue  # まだ 1日経っていない

            elapsed_h = int((now_ts - msg_ts) / 3600)
            msg_time  = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
            ts_link   = last_msg["ts"].replace(".", "")

            unanswered.append({
                "source":       "dm",
                "channel_id":   dm_id,
                "channel_name": dm_name,
                "ts":           last_msg["ts"],
                "ts_link":      ts_link,
                "text":         last_msg.get("text", "")[:120],
                "elapsed_h":    elapsed_h,
                "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
            })
        except SlackApiError as e:
            print(f"[WARN] DM history 失敗 ({dm_name}): {e}")

    return unanswered


# ══════════════════════════════════════════════════════════════════════════════
# Gmail チェック
# ══════════════════════════════════════════════════════════════════════════════

def get_gmail_service():
    """保存済みトークンで Gmail API サービスを返す。トークン未設定時は None。"""
    if not os.path.exists(GMAIL_TOKEN_FILE):
        print(f"[WARN] Gmail トークンファイルが見つかりません: {GMAIL_TOKEN_FILE}")
        print("       setup_gmail_auth.py を実行して認証を完了させてください。")
        return None

    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    if not creds.valid:
        print("[WARN] Gmail 認証情報が無効です。setup_gmail_auth.py を再実行してください。")
        return None

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _get_header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def check_gmail_awaiting_replies(gmail_service) -> list[dict]:
    """
    送信済みメールのスレッドを走査し、自分が最後の送信者で
    GMAIL_THRESHOLD_DAYS 日以上返信がないものを返す。
    """
    if gmail_service is None:
        return []

    now = time.time()
    unanswered = []

    try:
        profile  = gmail_service.users().getProfile(userId="me").execute()
        my_email = profile["emailAddress"].lower()
        print(f"[Gmail] {my_email} として確認中...")
    except Exception as e:
        print(f"[ERROR] Gmail プロフィール取得失敗: {e}")
        return []

    # 検索対象: lookback〜threshold 日前に送信したメール
    threshold_dt = (datetime.now() - timedelta(days=GMAIL_THRESHOLD_DAYS)).strftime("%Y/%m/%d")
    lookback_dt  = (datetime.now() - timedelta(days=GMAIL_LOOKBACK_DAYS)).strftime("%Y/%m/%d")
    query = f"in:sent after:{lookback_dt} before:{threshold_dt}"

    try:
        thread_ids = set()
        page_token = None
        while True:
            kwargs: dict = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                kwargs["pageToken"] = page_token
            result     = gmail_service.users().messages().list(**kwargs).execute()
            for m in result.get("messages", []):
                thread_ids.add(m["threadId"])
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        print(f"[Gmail] {len(thread_ids)} スレッドを確認中...")

        for thread_id in thread_ids:
            thread   = gmail_service.users().threads().get(
                userId="me", id=thread_id, format="metadata",
                metadataHeaders=["From", "To", "Subject"],
            ).execute()
            messages = thread.get("messages", [])
            if not messages:
                continue

            # スレッド内の最後のメッセージ
            last_msg    = messages[-1]
            from_raw    = _get_header(last_msg, "From")
            _, from_addr = parseaddr(from_raw)

            if from_addr.lower() != my_email:
                continue  # 相手が最後に返信済み

            last_ts = int(last_msg["internalDate"]) / 1000
            if (now - last_ts) < GMAIL_THRESHOLD_DAYS * 86400:
                continue  # まだ閾値に達していない

            subject      = _get_header(last_msg, "Subject") or "(件名なし)"
            to_header    = _get_header(last_msg, "To")
            elapsed_days = int((now - last_ts) / 86400)
            sent_time    = datetime.fromtimestamp(last_ts, tz=timezone.utc)

            unanswered.append({
                "thread_id":    thread_id,
                "subject":      subject[:80],
                "to":           to_header[:100],
                "elapsed_days": elapsed_days,
                "sent_time_utc": sent_time.strftime("%Y-%m-%d %H:%M UTC"),
            })

    except Exception as e:
        print(f"[ERROR] Gmail チェック中にエラー: {e}")

    return unanswered


# ══════════════════════════════════════════════════════════════════════════════
# リマインドメッセージ組み立て
# ══════════════════════════════════════════════════════════════════════════════

def build_slack_reminder(items: list[dict]) -> str:
    lines = [f":speech_balloon: *Slack 返信待ち: {len(items)} 件*（1日以上経過）\n"]
    for i, item in enumerate(items, 1):
        link         = f"https://slack.com/archives/{item['channel_id']}/p{item['ts_link']}"
        source_label = f"DM ({item['channel_name']})" if item["source"] == "dm" else f"#{item['channel_name']}"
        lines.append(
            f"*{i}.* {source_label} – {item['msg_time_utc']}（{item['elapsed_h']}時間経過）\n"
            f"   内容: _{item['text']}…_\n"
            f"   {link}\n"
        )
    return "\n".join(lines)


def build_gmail_reminder(items: list[dict]) -> str:
    lines = [f":email: *Gmail 返信待ち: {len(items)} 件*（3日以上経過）\n"]
    for i, item in enumerate(items, 1):
        lines.append(
            f"*{i}.* 件名: _{item['subject']}_\n"
            f"   宛先: {item['to']}\n"
            f"   送信日時: {item['sent_time_utc']}（{item['elapsed_days']}日経過）\n"
        )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# エントリポイント
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時）のためスキップ。")
        return

    print(f"[INFO] チェック開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    reminder_parts: list[str] = []

    # ── Slack ──────────────────────────────────────────────────────────────
    slack_items: list[dict] = []
    slack_items.extend(check_channels_for_awaiting(now_ts))
    slack_items.extend(check_dms_for_awaiting(now_ts))

    if slack_items:
        print(f"[Slack] 返信待ち: {len(slack_items)} 件")
        reminder_parts.append(build_slack_reminder(slack_items))
    else:
        print("[Slack] 返信待ちなし。")

    # ── Gmail ──────────────────────────────────────────────────────────────
    gmail_service = get_gmail_service()
    gmail_items   = check_gmail_awaiting_replies(gmail_service)

    if gmail_items:
        print(f"[Gmail] 返信待ち: {len(gmail_items)} 件")
        reminder_parts.append(build_gmail_reminder(gmail_items))
    else:
        print("[Gmail] 返信待ちなし。")

    # ── Slack DM 送信 ───────────────────────────────────────────────────────
    if reminder_parts:
        send_dm("\n\n".join(reminder_parts))
    else:
        print("[INFO] 返信待ちなし。リマインドは送りません。")


if __name__ == "__main__":
    main()
