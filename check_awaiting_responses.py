#!/usr/bin/env python3
"""
Awaiting Response Reminder (check_awaiting_responses.py)
---------------------------------------------------------
自分が送ったメッセージで相手から返信が来ていないものを検出し、
自分自身の Slack DM にリマインドを送る。

  ■ Slack DM     : 1日以上返信なし
  ■ Slackチャンネル: 1日以上返信なし
  ■ Gmail        : 3日以上返信なし

■ Gmail セットアップ（初回のみ）
  1. Google Cloud Console でプロジェクトを作成し、Gmail API を有効化
  2. OAuth 2.0 クライアント ID（種類: デスクトップアプリ）を作成し、
     gmail_credentials.json としてこのスクリプトと同じディレクトリに保存
  3. 初回起動時にブラウザが開いて Google 認証を求めます
     （以降は gmail_token.json に保存されて自動更新）
  Gmail を使わない場合は gmail_credentials.json を置かなければスキップされます。

■ 必要な環境変数
  SLACK_BOT_TOKEN  xoxp-... または xoxb-... トークン
"""

import os
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN          = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID           = "U0973MEH3V0"
SLACK_THRESHOLD_SEC  = 1 * 24 * 60 * 60   # 1 日
GMAIL_THRESHOLD_SEC  = 3 * 24 * 60 * 60   # 3 日
LOOKBACK_SEC         = 7 * 24 * 60 * 60   # 過去 7 日間を対象
ACTIVE_HOURS         = range(8, 20)        # 8:00〜19:59 のみ実行

_SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
GMAIL_TOKEN_FILE  = os.path.join(_SCRIPT_DIR, "gmail_token.json")
GMAIL_CREDS_FILE  = os.path.join(_SCRIPT_DIR, "gmail_credentials.json")
GMAIL_SCOPES      = ["https://www.googleapis.com/auth/gmail.readonly"]
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
# Slack 共通ヘルパー
# ══════════════════════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM sent.")


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


# ══════════════════════════════════════════════════════════════════════════════
# Slack DM チェック — 自分が最後に送って返信待ちの DM
# ══════════════════════════════════════════════════════════════════════════════

def find_slack_awaiting_dm_replies(now_ts: float) -> list[dict]:
    """
    自分が最後にメッセージを送った DM 会話を探す。
    相手から返信がなく SLACK_THRESHOLD_SEC 以上経過しているものを返す。
    """
    threshold = now_ts - SLACK_THRESHOLD_SEC
    oldest    = now_ts - LOOKBACK_SEC
    awaiting  = []

    try:
        for page in slack_client.conversations_list(types="im", exclude_archived=True):
            for conv in page["channels"]:
                ch_id      = conv["id"]
                other_user = conv.get("user", "")

                try:
                    messages: list[dict] = []
                    for hist_page in slack_client.conversations_history(
                        channel=ch_id,
                        oldest=str(oldest),
                        limit=200,
                    ):
                        messages.extend(hist_page["messages"])

                    if not messages:
                        continue

                    # 時刻降順でソート（API は通常降順だが念のため）
                    messages.sort(key=lambda m: float(m["ts"]), reverse=True)

                    # 自分の最後の送信メッセージ
                    last_my_msg = next(
                        (m for m in messages if m.get("user") == MY_USER_ID), None
                    )
                    if not last_my_msg:
                        continue

                    last_my_ts = float(last_my_msg["ts"])

                    # 自分のメッセージより後に相手の返信があるか
                    has_reply = any(
                        float(m["ts"]) > last_my_ts and m.get("user") != MY_USER_ID
                        for m in messages
                    )

                    if not has_reply and last_my_ts < threshold:
                        elapsed_sec = now_ts - last_my_ts
                        link = (
                            f"https://slack.com/archives/{ch_id}"
                            f"/p{last_my_msg['ts'].replace('.', '')}"
                        )
                        awaiting.append({
                            "type":        "slack_dm",
                            "channel_id":  ch_id,
                            "other_user":  other_user,
                            "text":        last_my_msg.get("text", "")[:120],
                            "ts":          last_my_msg["ts"],
                            "elapsed_h":   int(elapsed_sec / 3600),
                            "elapsed_d":   int(elapsed_sec / 86400),
                            "msg_time_utc": datetime.fromtimestamp(
                                last_my_ts, tz=timezone.utc
                            ).strftime("%Y-%m-%d %H:%M UTC"),
                            "link":        link,
                        })

                except SlackApiError as e:
                    print(f"[WARN] DM history failed for {ch_id}: {e}")

    except SlackApiError as e:
        print(f"[WARN] conversations_list(im) failed: {e}")

    return awaiting


# ══════════════════════════════════════════════════════════════════════════════
# Slackチャンネル チェック — 自分が送って返信待ちのチャンネルメッセージ
# ══════════════════════════════════════════════════════════════════════════════

def find_slack_awaiting_channel_replies(now_ts: float) -> list[dict]:
    """
    チャンネルで自分が送ったメッセージのうち、他者からの返信がなく
    SLACK_THRESHOLD_SEC 以上経過したものを返す。

    対象:
      - 自分が投稿したトップレベルメッセージ（返信ゼロ）
      - 自分がスレッドの最後の返信者で、その後誰も返信していないもの
    """
    threshold = now_ts - SLACK_THRESHOLD_SEC
    oldest    = now_ts - LOOKBACK_SEC
    awaiting  = []

    channels = fetch_joined_channels()
    print(f"[INFO] チャンネル {len(channels)} 件を確認中...")

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
                    # スレッド返信（子メッセージ）は除外
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    msg_ts = float(msg["ts"])

                    # 自分が投稿したメッセージのみ
                    if msg.get("user") != MY_USER_ID:
                        continue

                    if msg_ts > threshold:
                        continue  # まだ猶予期間内

                    reply_count = msg.get("reply_count", 0)
                    link = (
                        f"https://slack.com/archives/{ch_id}"
                        f"/p{msg['ts'].replace('.', '')}"
                    )

                    if reply_count == 0:
                        # 返信ゼロ — 確実に未返信
                        elapsed_sec = now_ts - msg_ts
                        awaiting.append({
                            "type":         "slack_channel",
                            "channel_id":   ch_id,
                            "channel_name": ch_name,
                            "text":         msg.get("text", "")[:120],
                            "ts":           msg["ts"],
                            "elapsed_h":    int(elapsed_sec / 3600),
                            "elapsed_d":    int(elapsed_sec / 86400),
                            "msg_time_utc": datetime.fromtimestamp(
                                msg_ts, tz=timezone.utc
                            ).strftime("%Y-%m-%d %H:%M UTC"),
                            "link":         link,
                        })
                    else:
                        # スレッドに返信あり → 自分が最後の投稿者か確認
                        try:
                            thread_msgs: list[dict] = []
                            for tp in slack_client.conversations_replies(
                                channel=ch_id, ts=msg["ts"]
                            ):
                                thread_msgs.extend(tp["messages"])

                            thread_msgs.sort(key=lambda m: float(m["ts"]))
                            last_in_thread = thread_msgs[-1]

                            if last_in_thread.get("user") != MY_USER_ID:
                                continue  # 他者が最後に投稿済み

                            last_ts = float(last_in_thread["ts"])
                            if last_ts > threshold:
                                continue  # まだ猶予期間内

                            elapsed_sec = now_ts - last_ts
                            awaiting.append({
                                "type":         "slack_channel",
                                "channel_id":   ch_id,
                                "channel_name": ch_name,
                                "text":         last_in_thread.get("text", "")[:120],
                                "ts":           last_in_thread["ts"],
                                "elapsed_h":    int(elapsed_sec / 3600),
                                "elapsed_d":    int(elapsed_sec / 86400),
                                "msg_time_utc": datetime.fromtimestamp(
                                    last_ts, tz=timezone.utc
                                ).strftime("%Y-%m-%d %H:%M UTC"),
                                "link":         link,
                            })

                        except SlackApiError as e:
                            print(f"[WARN] conversations_replies failed for {ch_id}: {e}")

        except SlackApiError as e:
            print(f"[WARN] conversations_history failed for #{ch_name}: {e}")

    return awaiting


# ══════════════════════════════════════════════════════════════════════════════
# Gmail — OAuth2 認証
# ══════════════════════════════════════════════════════════════════════════════

def get_gmail_service():
    """Gmail API サービスを返す。credentials がなければ None を返す。"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print(
            "[WARN] Google API ライブラリが未インストールです。\n"
            "       pip install google-auth google-auth-oauthlib google-api-python-client"
        )
        return None

    creds = None

    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GMAIL_CREDS_FILE):
                print(
                    f"[INFO] Gmail credentials が見つかりません ({GMAIL_CREDS_FILE})。"
                    " Gmail チェックをスキップします。"
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ══════════════════════════════════════════════════════════════════════════════
# Gmail チェック — 送信済みで返信待ちのメール
# ══════════════════════════════════════════════════════════════════════════════

def find_gmail_awaiting_replies(now_ts: float) -> list[dict]:
    """
    送信済みメールのうち、相手からの返信がなく GMAIL_THRESHOLD_SEC 以上
    経過したスレッドを返す。
    """
    service = get_gmail_service()
    if service is None:
        return []

    threshold  = now_ts - GMAIL_THRESHOLD_SEC
    lookback_d = int(LOOKBACK_SEC / 86400)
    awaiting: list[dict] = []
    seen_threads: set[str] = set()

    # 自分のメールアドレスを取得
    try:
        profile  = service.users().getProfile(userId="me").execute()
        my_email = profile.get("emailAddress", "").lower()
    except Exception as e:
        print(f"[WARN] Gmail getProfile failed: {e}")
        return []

    def get_msg_ts(m: dict) -> float:
        return int(m.get("internalDate", "0")) / 1000

    def get_headers(m: dict) -> dict[str, str]:
        return {
            h["name"].lower(): h["value"]
            for h in m.get("payload", {}).get("headers", [])
        }

    try:
        result   = service.users().messages().list(
            userId="me",
            q=f"in:sent newer_than:{lookback_d}d",
            maxResults=200,
        ).execute()
        messages = result.get("messages", [])
        print(f"[INFO] Gmail: {len(messages)} 件の送信メールを確認中...")

        for msg_ref in messages:
            thread_id = msg_ref.get("threadId")
            if not thread_id or thread_id in seen_threads:
                continue
            seen_threads.add(thread_id)

            try:
                thread = service.users().threads().get(
                    userId="me",
                    id=thread_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()

                thread_messages = thread.get("messages", [])
                if not thread_messages:
                    continue

                # 時刻昇順でソート
                thread_messages.sort(key=get_msg_ts)

                # 自分が送ったメッセージの中で最後のものを探す
                last_sent_ts      = None
                last_sent_headers = None
                for tmsg in thread_messages:
                    hdrs      = get_headers(tmsg)
                    from_addr = hdrs.get("from", "").lower()
                    if my_email in from_addr:
                        last_sent_ts      = get_msg_ts(tmsg)
                        last_sent_headers = hdrs

                if last_sent_ts is None:
                    continue  # このスレッドに自分の送信メールなし

                if last_sent_ts > threshold:
                    continue  # まだ猶予期間内（3 日未満）

                # 自分の最後のメール以降に他者の返信があるか
                has_reply = False
                for tmsg in thread_messages:
                    if get_msg_ts(tmsg) <= last_sent_ts:
                        continue
                    hdrs      = get_headers(tmsg)
                    from_addr = hdrs.get("from", "").lower()
                    if my_email not in from_addr:
                        has_reply = True
                        break

                if not has_reply:
                    elapsed_sec = now_ts - last_sent_ts
                    awaiting.append({
                        "type":        "gmail",
                        "thread_id":   thread_id,
                        "subject":     last_sent_headers.get("subject", "(件名なし)")[:80],
                        "to":          last_sent_headers.get("to", "")[:100],
                        "elapsed_h":   int(elapsed_sec / 3600),
                        "elapsed_d":   int(elapsed_sec / 86400),
                        "msg_time_utc": datetime.fromtimestamp(
                            last_sent_ts, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M UTC"),
                    })

            except Exception as e:
                print(f"[WARN] Gmail thread fetch failed ({thread_id}): {e}")

    except Exception as e:
        print(f"[WARN] Gmail messages.list failed: {e}")

    return awaiting


# ══════════════════════════════════════════════════════════════════════════════
# リマインダー本文生成
# ══════════════════════════════════════════════════════════════════════════════

def build_reminder_text(
    slack_dm_items: list[dict],
    slack_ch_items: list[dict],
    gmail_items:    list[dict],
) -> str:
    total = len(slack_dm_items) + len(slack_ch_items) + len(gmail_items)
    lines = [f":mailbox_with_no_mail: *返信待ちが {total} 件あります*\n"]

    if slack_dm_items:
        lines.append(f"*─ Slack DM（1日以上未返信）: {len(slack_dm_items)} 件 ─*")
        for i, item in enumerate(slack_dm_items, 1):
            lines.append(
                f"*{i}.* DM → <@{item['other_user']}> "
                f"（{item['elapsed_d']}日{item['elapsed_h'] % 24}時間前）\n"
                f"   送信日時: {item['msg_time_utc']}\n"
                f"   内容: _{item['text']}…_\n"
                f"   {item['link']}"
            )
        lines.append("")

    if slack_ch_items:
        lines.append(
            f"*─ Slackチャンネル（1日以上未返信）: {len(slack_ch_items)} 件 ─*"
        )
        for i, item in enumerate(slack_ch_items, 1):
            lines.append(
                f"*{i}.* <#{item['channel_id']}> "
                f"（{item['elapsed_d']}日{item['elapsed_h'] % 24}時間前）\n"
                f"   送信日時: {item['msg_time_utc']}\n"
                f"   内容: _{item['text']}…_\n"
                f"   {item['link']}"
            )
        lines.append("")

    if gmail_items:
        lines.append(f"*─ Gmail（3日以上未返信）: {len(gmail_items)} 件 ─*")
        for i, item in enumerate(gmail_items, 1):
            lines.append(
                f"*{i}.* 宛先: {item['to']}\n"
                f"   件名: _{item['subject']}_\n"
                f"   送信日時: {item['msg_time_utc']} "
                f"（{item['elapsed_d']}日{item['elapsed_h'] % 24}時間前）"
            )

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour

    if local_hour not in ACTIVE_HOURS:
        print(
            f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時のみ）のためスキップ。"
        )
        return

    print(
        f"[INFO] Check started at "
        f"{datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}"
    )

    print("[INFO] Slack DM チェック中...")
    slack_dm_items = find_slack_awaiting_dm_replies(now_ts)
    print(f"[INFO]   → {len(slack_dm_items)} 件")

    print("[INFO] Slackチャンネル チェック中...")
    slack_ch_items = find_slack_awaiting_channel_replies(now_ts)
    print(f"[INFO]   → {len(slack_ch_items)} 件")

    print("[INFO] Gmail チェック中...")
    gmail_items = find_gmail_awaiting_replies(now_ts)
    print(f"[INFO]   → {len(gmail_items)} 件")

    total = len(slack_dm_items) + len(slack_ch_items) + len(gmail_items)
    if total == 0:
        print("[INFO] 返信待ちなし。リマインドは送りません。")
        return

    print(f"[INFO] 合計 {total} 件の返信待ちを検出。DMを送信します。")
    reminder = build_reminder_text(slack_dm_items, slack_ch_items, gmail_items)
    send_dm(reminder)


if __name__ == "__main__":
    main()
