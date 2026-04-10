#!/usr/bin/env python3
"""
Awaiting-Reply Reminder
-----------------------
自分が送った Slack メッセージ（1日以上返信なし）と
Gmail メール（3日以上返信なし）をチェックし、
未返信のものがあれば自分の Slack DM にリマインドを送る。

【Slack 検出対象】
  - DM / グループDM: 自分が最後にメッセージを送ってから1日以上返信がないもの
  - チャンネル: 自分が送った「@メンションまたは?を含むトップレベルメッセージ」で
               1日以上他ユーザーから返信がないもの

【Gmail 検出対象】
  - 送信済みスレッドのうち、自分が最後の送信者かつ3日以上返信がないもの

【必要な環境変数】
  SLACK_BOT_TOKEN    : Slack Bot または User トークン（xoxb- / xoxp-）
  GMAIL_TOKEN_FILE   : Gmail OAuth2 トークンファイルパス（デフォルト: token.json）
  GMAIL_CREDENTIALS_FILE : Google Cloud OAuth2 クライアント JSON（デフォルト: credentials.json）
                           初回認証時のみ必要。以降は token.json で自動更新。
"""

import os
import sys
import time
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Gmail API（インストールされていない場合は Gmail チェックをスキップ）
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    from googleapiclient.discovery import build as google_build
    from google_auth_oauthlib.flow import InstalledAppFlow
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    print("[WARN] Google API ライブラリが未インストールのため Gmail チェックをスキップします。"
          "  pip install google-api-python-client google-auth-oauthlib")

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN            = os.environ["SLACK_BOT_TOKEN"]
MY_USER_ID             = "U0973MEH3V0"
SLACK_THRESHOLD_SEC    = 1 * 24 * 60 * 60   # Slack: 1日
GMAIL_THRESHOLD_SEC    = 3 * 24 * 60 * 60   # Gmail: 3日
LOOKBACK_DAYS          = 7                   # 過去何日分をスキャンするか
ACTIVE_HOURS           = range(8, 20)        # 8:00〜19:59 のみ実行
GMAIL_TOKEN_FILE       = os.environ.get("GMAIL_TOKEN_FILE", "token.json")
GMAIL_CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE", "credentials.json")
GMAIL_SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
# Slack ── 自分が送ったメッセージで返信待ちのもの
# ══════════════════════════════════════════════════════════════════════════════

def find_unanswered_slack_dms(now_ts: float) -> list[dict]:
    """
    DM / グループDM で自分が最後にメッセージを送ってから
    SLACK_THRESHOLD_SEC 以上返信がないものを返す。
    """
    cutoff  = now_ts - SLACK_THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_DAYS * 86400
    results = []

    try:
        for page in slack_client.conversations_list(
            types="im,mpim",
            exclude_archived=True,
        ):
            for ch in page["channels"]:
                ch_id = ch["id"]
                # 自分自身との DM はスキップ
                if ch.get("user") == MY_USER_ID:
                    continue
                try:
                    resp     = slack_client.conversations_history(
                        channel=ch_id,
                        oldest=str(oldest),
                        limit=10,
                    )
                    messages = resp.get("messages", [])
                    if not messages:
                        continue

                    # messages は新しい順
                    latest = messages[0]
                    if latest.get("user") != MY_USER_ID:
                        continue
                    ts = float(latest["ts"])
                    if ts >= cutoff:
                        continue  # まだ1日経っていない

                    elapsed_h = int((now_ts - ts) / 3600)
                    results.append({
                        "kind":       "Slack DM",
                        "channel_id": ch_id,
                        "partner":    ch.get("user", ""),
                        "ts":         latest["ts"],
                        "text":       latest.get("text", "")[:100],
                        "elapsed_h":  elapsed_h,
                        "sent_at":    datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    })
                except SlackApiError:
                    pass
    except SlackApiError as e:
        print(f"[WARN] conversations_list(im/mpim) 失敗: {e}")

    return results


def find_unanswered_slack_threads(now_ts: float) -> list[dict]:
    """
    チャンネルで自分が起点となったトップレベルメッセージのうち、
    @メンションまたは ? を含み、他ユーザーから1日以上返信がないものを返す。
    """
    cutoff  = now_ts - SLACK_THRESHOLD_SEC
    oldest  = now_ts - LOOKBACK_DAYS * 86400
    results = []

    try:
        channels = []
        for page in slack_client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list(channels) 失敗: {e}")
        return results

    print(f"[INFO] Slack チャンネル {len(channels)} 件をスキャン中...")

    for ch in channels:
        ch_id   = ch["id"]
        ch_name = ch.get("name", ch_id)
        try:
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest),
                latest=str(now_ts),
                limit=200,
            ):
                for msg in page["messages"]:
                    # 自分が送ったトップレベルメッセージのみ対象
                    if msg.get("user") != MY_USER_ID:
                        continue
                    # スレッドの返信（thread_ts != ts）はスキップ
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue

                    ts = float(msg["ts"])
                    if ts >= cutoff:
                        continue  # まだ1日経っていない

                    text = msg.get("text", "")
                    # @メンション または ? を含むメッセージのみ対象
                    if "<@" not in text and "?" not in text and "？" not in text:
                        continue

                    # スレッドに他ユーザーの返信があるか確認
                    others_replied = False
                    if msg.get("reply_count", 0) > 0:
                        try:
                            for rpage in slack_client.conversations_replies(
                                channel=ch_id, ts=msg["ts"]
                            ):
                                for reply in rpage["messages"]:
                                    if reply.get("ts") == msg["ts"]:
                                        continue  # 親メッセージはスキップ
                                    if reply.get("user") != MY_USER_ID:
                                        others_replied = True
                                        break
                                if others_replied:
                                    break
                        except SlackApiError:
                            pass

                    if others_replied:
                        continue

                    elapsed_h = int((now_ts - ts) / 3600)
                    results.append({
                        "kind":         "Slackチャンネル",
                        "channel_id":   ch_id,
                        "channel_name": ch_name,
                        "ts":           msg["ts"],
                        "text":         text[:100],
                        "elapsed_h":    elapsed_h,
                        "sent_at":      datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    })
        except SlackApiError as e:
            print(f"[WARN] conversations_history 失敗 #{ch_name}: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Gmail ── 送信済みメールで返信待ちのもの
# ══════════════════════════════════════════════════════════════════════════════

def _get_gmail_service():
    """
    認証済み Gmail API サービスオブジェクトを返す。
    token.json が存在すれば自動更新。存在しない場合は OAuth フローを実行。
    """
    creds = None
    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            with open(GMAIL_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            if not os.path.exists(GMAIL_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Gmail 認証ファイルが見つかりません: {GMAIL_CREDENTIALS_FILE}\n"
                    "Google Cloud Console から OAuth 2.0 クライアントID（デスクトップアプリ用）を\n"
                    "ダウンロードして credentials.json として配置してください。\n"
                    "初回のみ: python3 check_awaiting_replies.py --auth"
                )
            flow  = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
            with open(GMAIL_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

    return google_build("gmail", "v1", credentials=creds)


def _header(headers: list[dict], name: str) -> str:
    """ヘッダーリストから指定名のヘッダー値を返す。"""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def find_unanswered_gmail_threads(now_ts: float) -> list[dict]:
    """
    送信済みスレッドで自分が最後の送信者かつ
    GMAIL_THRESHOLD_SEC 以上返信がないものを返す。
    """
    if not GMAIL_AVAILABLE:
        return []

    results = []
    try:
        service  = _get_gmail_service()
        profile  = service.users().getProfile(userId="me").execute()
        my_email = profile.get("emailAddress", "").lower()

        # 送信済みメールを過去 LOOKBACK_DAYS 日分検索
        after_epoch = int(now_ts - LOOKBACK_DAYS * 86400)
        query       = f"in:sent after:{after_epoch}"

        # スレッド ID を収集（重複排除）
        seen_thread_ids = set()
        page_token      = None
        while True:
            kwargs = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                kwargs["pageToken"] = page_token
            resp       = service.users().messages().list(**kwargs).execute()
            for m in resp.get("messages", []):
                seen_thread_ids.add(m["threadId"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        print(f"[INFO] Gmail スレッド {len(seen_thread_ids)} 件をチェック中...")

        cutoff = now_ts - GMAIL_THRESHOLD_SEC

        for thread_id in seen_thread_ids:
            try:
                thread = service.users().threads().get(
                    userId="me",
                    id=thread_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "To"],
                ).execute()
                msgs = thread.get("messages", [])
                if not msgs:
                    continue

                # internalDate（ミリ秒）で昇順ソート → 最新メッセージを取得
                msgs_sorted = sorted(msgs, key=lambda m: int(m["internalDate"]))
                last_msg    = msgs_sorted[-1]
                last_ts     = int(last_msg["internalDate"]) / 1000  # ms → s

                if last_ts >= cutoff:
                    continue  # まだ3日経っていない

                last_headers = last_msg.get("payload", {}).get("headers", [])
                last_from    = _header(last_headers, "From").lower()

                # 最後のメッセージが自分からのものか確認
                if my_email not in last_from:
                    continue

                first_headers = msgs_sorted[0].get("payload", {}).get("headers", [])
                subject   = _header(first_headers, "Subject") or "(件名なし)"
                to        = _header(first_headers, "To") or ""
                elapsed_h = int((now_ts - last_ts) / 3600)

                results.append({
                    "kind":      "Gmail",
                    "thread_id": thread_id,
                    "subject":   subject[:80],
                    "to":        to[:80],
                    "elapsed_h": elapsed_h,
                    "sent_at":   datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                })
            except Exception as e:
                print(f"[WARN] Gmail スレッド取得失敗 ({thread_id}): {e}")

    except FileNotFoundError as e:
        print(f"[WARN] {e}")
    except Exception as e:
        print(f"[WARN] Gmail チェック失敗: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Slack DM 送信
# ══════════════════════════════════════════════════════════════════════════════

def get_dm_channel(user_id: str) -> str:
    resp = slack_client.conversations_open(users=user_id)
    return resp["channel"]["id"]


def build_reminder_text(
    slack_dms: list[dict],
    slack_threads: list[dict],
    gmail_items: list[dict],
) -> str:
    total = len(slack_dms) + len(slack_threads) + len(gmail_items)
    lines = [f":bell: *返信待ちが {total} 件あります*\n"]

    if slack_dms:
        lines.append("*【Slack DM / グループDM】（1日以上返信なし）*")
        for i, item in enumerate(slack_dms, 1):
            link    = f"https://slack.com/archives/{item['channel_id']}/p{item['ts'].replace('.', '')}"
            partner = f"<@{item['partner']}>" if item.get("partner") else "(不明)"
            lines.append(
                f"  {i}. {partner} – {item['sent_at']}（{item['elapsed_h']}時間以上前）\n"
                f"     内容: _{item['text']}…_\n"
                f"     {link}"
            )

    if slack_threads:
        lines.append("\n*【Slack チャンネルスレッド】（1日以上返信なし）*")
        for i, item in enumerate(slack_threads, 1):
            link = f"https://slack.com/archives/{item['channel_id']}/p{item['ts'].replace('.', '')}"
            lines.append(
                f"  {i}. <#{item['channel_id']}> – {item['sent_at']}（{item['elapsed_h']}時間以上前）\n"
                f"     内容: _{item['text']}…_\n"
                f"     {link}"
            )

    if gmail_items:
        lines.append("\n*【Gmail】（3日以上返信なし）*")
        for i, item in enumerate(gmail_items, 1):
            elapsed_d = item["elapsed_h"] // 24
            lines.append(
                f"  {i}. 件名: _{item['subject']}_\n"
                f"     宛先: {item['to']}\n"
                f"     送信日時: {item['sent_at']}（{elapsed_d}日以上前）"
            )

    return "\n".join(lines)


def send_dm(text: str) -> None:
    dm_channel = get_dm_channel(MY_USER_ID)
    slack_client.chat_postMessage(channel=dm_channel, text=text, mrkdwn=True)
    print("[INFO] DM 送信完了。")


# ══════════════════════════════════════════════════════════════════════════════
# エントリーポイント
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # --auth フラグ: Gmail の初回 OAuth 認証のみ実行して終了
    if "--auth" in sys.argv:
        if not GMAIL_AVAILABLE:
            print("[ERROR] Google API ライブラリが未インストールです。")
            sys.exit(1)
        print("[INFO] Gmail 認証フローを開始します...")
        _get_gmail_service()
        print(f"[INFO] 認証完了。トークンを {GMAIL_TOKEN_FILE} に保存しました。")
        return

    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(f"[INFO] 現在 {local_hour}時 — 実行時間外（8〜19時のみ）のためスキップ。")
        return

    print(f"[INFO] 返信待ちチェック開始: "
          f"{datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    slack_dms     = find_unanswered_slack_dms(now_ts)
    slack_threads = find_unanswered_slack_threads(now_ts)
    gmail_items   = find_unanswered_gmail_threads(now_ts) if GMAIL_AVAILABLE else []

    print(f"[INFO] 検出: Slack DM {len(slack_dms)}件 / "
          f"Slackチャンネル {len(slack_threads)}件 / Gmail {len(gmail_items)}件")

    if not (slack_dms or slack_threads or gmail_items):
        print("[INFO] 返信待ちなし。リマインドは送りません。")
        return

    reminder = build_reminder_text(slack_dms, slack_threads, gmail_items)
    send_dm(reminder)


if __name__ == "__main__":
    main()
