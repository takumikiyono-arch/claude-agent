#!/usr/bin/env python3
"""
Outbound Message Reminder (check_outbound_reminders.py)
---------------------------------------------------------
自分が送信したメッセージ・メールで返信が来ていないものを検出し、
Slack の自分宛 DM にリマインドを送る。

  - Slack DM / チャンネルスレッド: 自分が最後に送信してから 1 日以上返信なし
  - Gmail 送信済みメール         : 送信してから 3 日以上返信なし

【Slack 設定】
  環境変数 SLACK_BOT_TOKEN に User Token (xoxp-...) をセット。
  Bot Token (xoxb-...) では search.messages が使えないため DM のみ動作する。

【Gmail OAuth2 初回設定】
  1. https://console.cloud.google.com/ で新規プロジェクト作成
  2. 「APIとサービス」→「Gmail API」を有効化
  3. 「認証情報」→ OAuth2 クライアントID (デスクトップアプリ) を作成し
     credentials.json をダウンロード
  4. このスクリプトと同じディレクトリに gmail_credentials.json として保存
  5. 初回実行時にブラウザで認証 → gmail_token.json が自動生成される
"""

import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# Slack
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Gmail (google-api-python-client, google-auth-oauthlib が必要)
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as google_build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    print("[WARN] Gmail 関連ライブラリが未インストール。Gmail チェックをスキップします。")
    print("       pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

# ── 設定 ──────────────────────────────────────────────────────────────────────
SLACK_TOKEN         = os.environ["SLACK_BOT_TOKEN"]
MY_SLACK_USER_ID    = "U0973MEH3V0"

SLACK_THRESHOLD_H   = 24            # Slack: 1 日 = 24 時間
GMAIL_THRESHOLD_D   = 3             # Gmail: 3 日
LOOKBACK_DAYS       = 14            # 最大何日前まで遡るか

ACTIVE_HOURS        = range(8, 20)  # 8:00〜19:59 のみ実行

GMAIL_SCOPES        = ["https://www.googleapis.com/auth/gmail.readonly"]
SCRIPT_DIR          = Path(__file__).parent
GMAIL_TOKEN_FILE    = SCRIPT_DIR / "gmail_token.json"
GMAIL_CREDS_FILE    = SCRIPT_DIR / "gmail_credentials.json"
# ─────────────────────────────────────────────────────────────────────────────

slack_client = WebClient(token=SLACK_TOKEN)


# ═══════════════════════════════════════════════════════════════════════════════
# Slack ユーティリティ
# ═══════════════════════════════════════════════════════════════════════════════

def get_my_dm_channel() -> str:
    """自分自身との DM チャンネル ID を返す"""
    resp = slack_client.conversations_open(users=MY_SLACK_USER_ID)
    return resp["channel"]["id"]


def get_dm_channels() -> list[dict]:
    """1:1 DM + グループ DM チャンネル一覧を返す"""
    channels = []
    try:
        for page in slack_client.conversations_list(
            types="im,mpim",
            exclude_archived=True,
        ):
            channels.extend(page["channels"])
    except SlackApiError as e:
        print(f"[WARN] conversations_list(im/mpim) 失敗: {e}")
    return channels


# ═══════════════════════════════════════════════════════════════════════════════
# Slack: DM チェック
# ═══════════════════════════════════════════════════════════════════════════════

def find_unanswered_slack_dms(now_ts: float) -> list[dict]:
    """
    DM チャンネルで自分が最後に送ったメッセージが SLACK_THRESHOLD_H 時間以上前で
    相手からの返信がないものを返す。
    """
    threshold_sec = SLACK_THRESHOLD_H * 3600
    cutoff_ts     = now_ts - threshold_sec
    oldest_ts     = now_ts - (LOOKBACK_DAYS * 24 * 3600)
    waiting       = []

    dm_channels = get_dm_channels()
    print(f"[INFO] Slack DM: {len(dm_channels)} 件のチャンネルを確認中...")

    for ch in dm_channels:
        ch_id = ch["id"]
        try:
            messages = []
            for page in slack_client.conversations_history(
                channel=ch_id,
                oldest=str(oldest_ts),
                latest=str(now_ts),
                inclusive=True,
                limit=50,
            ):
                messages.extend(page["messages"])

            if not messages:
                continue

            # 新しい順に並べる
            messages.sort(key=lambda m: float(m["ts"]), reverse=True)
            latest    = messages[0]
            latest_ts = float(latest["ts"])

            # 最新メッセージが自分のものでなければスキップ（相手が返信済み）
            if latest.get("user") != MY_SLACK_USER_ID:
                continue

            # まだ閾値内であればスキップ
            if latest_ts > cutoff_ts:
                continue

            # DM 相手を特定
            try:
                ch_info   = slack_client.conversations_info(channel=ch_id)
                ch_detail = ch_info["channel"]
                if ch_detail.get("is_im"):
                    other_user = f"<@{ch_detail.get('user', 'unknown')}>"
                else:
                    # グループ DM: 自分以外のメンバー
                    members      = ch_detail.get("members", [])
                    other_members = [u for u in members if u != MY_SLACK_USER_ID]
                    other_user   = " ".join(f"<@{u}>" for u in other_members) or "unknown"
            except SlackApiError:
                other_user = "unknown"

            elapsed_h = int((now_ts - latest_ts) / 3600)
            msg_time  = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
            ts_link   = latest["ts"].replace(".", "")

            waiting.append({
                "channel_id":   ch_id,
                "other_user":   other_user,
                "ts":           latest["ts"],
                "text":         latest.get("text", "")[:120],
                "elapsed_h":    elapsed_h,
                "elapsed_d":    elapsed_h // 24,
                "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                "link":         f"https://slack.com/archives/{ch_id}/p{ts_link}",
            })

        except SlackApiError as e:
            print(f"[WARN] conversations_history 失敗 ({ch_id}): {e}")

    return waiting


# ═══════════════════════════════════════════════════════════════════════════════
# Slack: チャンネルスレッド チェック (User Token 必須)
# ═══════════════════════════════════════════════════════════════════════════════

def find_unanswered_slack_threads(now_ts: float) -> list[dict]:
    """
    チャンネル内のスレッドで自分が最後に返信してから SLACK_THRESHOLD_H 時間以上
    経過し、相手からの返信がないものを返す。
    search.messages API を使うため User Token (xoxp-...) が必要。
    Bot Token の場合はこの関数はスキップされる。
    """
    threshold_sec = SLACK_THRESHOLD_H * 3600
    cutoff_ts     = now_ts - threshold_sec
    waiting       = []

    oldest_str = datetime.fromtimestamp(
        now_ts - LOOKBACK_DAYS * 86400, tz=timezone.utc
    ).strftime("%Y-%m-%d")

    try:
        resp    = slack_client.search_messages(
            query=f"from:me after:{oldest_str}",
            count=100,
        )
        matches = resp.get("messages", {}).get("matches", [])
        print(f"[INFO] Slack スレッド: {len(matches)} 件の送信済みメッセージを確認中...")
    except SlackApiError as e:
        # Bot Token では search.messages は使えないためスキップ
        print(f"[INFO] Slack スレッドチェックをスキップ (User Token が必要): {e.response['error']}")
        return []

    seen_threads: set[tuple] = set()

    for msg in matches:
        ch_id     = msg.get("channel", {}).get("id")
        thread_ts = msg.get("thread_ts") or msg.get("ts")

        if not ch_id or not thread_ts:
            continue

        key = (ch_id, thread_ts)
        if key in seen_threads:
            continue
        seen_threads.add(key)

        try:
            all_msgs: list[dict] = []
            for page in slack_client.conversations_replies(
                channel=ch_id,
                ts=thread_ts,
                limit=100,
            ):
                all_msgs.extend(page["messages"])

            if not all_msgs:
                continue

            all_msgs.sort(key=lambda m: float(m["ts"]))
            latest    = all_msgs[-1]
            latest_ts = float(latest["ts"])

            # 最新が自分のメッセージでなければスキップ（相手が返信済み）
            if latest.get("user") != MY_SLACK_USER_ID:
                continue

            if latest_ts > cutoff_ts:
                continue

            ch_name   = msg.get("channel", {}).get("name", ch_id)
            elapsed_h = int((now_ts - latest_ts) / 3600)
            msg_time  = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
            ts_link   = latest["ts"].replace(".", "")

            waiting.append({
                "channel_id":   ch_id,
                "channel_name": ch_name,
                "ts":           latest["ts"],
                "text":         latest.get("text", "")[:120],
                "elapsed_h":    elapsed_h,
                "elapsed_d":    elapsed_h // 24,
                "msg_time_utc": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                "link":         f"https://slack.com/archives/{ch_id}/p{ts_link}",
            })

        except SlackApiError:
            pass

    return waiting


def build_slack_reminder(dm_items: list[dict], thread_items: list[dict]) -> str:
    total = len(dm_items) + len(thread_items)
    lines = [
        f":envelope_with_arrow: *Slack: 返信待ち {total} 件*"
        f"（{SLACK_THRESHOLD_H}時間以上経過）\n"
    ]

    if dm_items:
        lines.append("*── DM ──*")
        for i, item in enumerate(dm_items, 1):
            hours_rem = item["elapsed_h"] % 24
            lines.append(
                f"*{i}.* {item['other_user']} – {item['msg_time_utc']}"
                f"（{item['elapsed_d']}日{hours_rem}時間前）\n"
                f"   内容: _{item['text'][:80]}_\n"
                f"   {item['link']}\n"
            )

    if thread_items:
        lines.append("*── チャンネルスレッド ──*")
        for i, item in enumerate(thread_items, 1):
            hours_rem = item["elapsed_h"] % 24
            lines.append(
                f"*{i}.* #{item['channel_name']} – {item['msg_time_utc']}"
                f"（{item['elapsed_d']}日{hours_rem}時間前）\n"
                f"   内容: _{item['text'][:80]}_\n"
                f"   {item['link']}\n"
            )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Gmail
# ═══════════════════════════════════════════════════════════════════════════════

def get_gmail_service():
    """Gmail API サービスを返す（OAuth2 認証、トークンをファイルにキャッシュ）"""
    creds = None
    if GMAIL_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_FILE), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GMAIL_CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"\n[ERROR] Gmail credentials が見つかりません: {GMAIL_CREDS_FILE}\n"
                    "  設定手順:\n"
                    "    1. https://console.cloud.google.com/ でプロジェクト作成\n"
                    "    2. Gmail API を有効化\n"
                    "    3. OAuth2 クライアントID（デスクトップアプリ）を作成してダウンロード\n"
                    f"    4. {GMAIL_CREDS_FILE} として保存\n"
                    "    5. スクリプトを再実行（ブラウザで認証）\n"
                )
            flow  = InstalledAppFlow.from_client_secrets_file(
                str(GMAIL_CREDS_FILE), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        GMAIL_TOKEN_FILE.write_text(creds.to_json())

    return google_build("gmail", "v1", credentials=creds)


def find_unanswered_gmail_threads(now_ts: float) -> list[dict]:
    """
    送信済みメールのうち、スレッドで自分が最後に送信し、
    GMAIL_THRESHOLD_D 日以上返信がないものを返す。
    """
    threshold_sec = GMAIL_THRESHOLD_D * 24 * 3600
    cutoff_ts     = now_ts - threshold_sec
    oldest_ts     = now_ts - (LOOKBACK_DAYS * 24 * 3600)
    waiting: list[dict] = []

    try:
        service  = get_gmail_service()
        profile  = service.users().getProfile(userId="me").execute()
        my_email = profile["emailAddress"].lower()

        # 「3日以上前〜14日前」に送信したメールを検索
        after_date  = datetime.fromtimestamp(oldest_ts, tz=timezone.utc).strftime("%Y/%m/%d")
        before_date = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).strftime("%Y/%m/%d")
        query       = f"in:sent after:{after_date} before:{before_date}"

        print(f"[INFO] Gmail: '{query}' で検索中...")

        seen_threads: set[str] = set()
        page_token: str | None = None
        total_msgs = 0

        while True:
            kwargs: dict = dict(userId="me", q=query, maxResults=100)
            if page_token:
                kwargs["pageToken"] = page_token

            result   = service.users().messages().list(**kwargs).execute()
            msgs_ref = result.get("messages", [])
            total_msgs += len(msgs_ref)

            for msg_ref in msgs_ref:
                thread_id = msg_ref["threadId"]
                if thread_id in seen_threads:
                    continue
                seen_threads.add(thread_id)

                try:
                    thread = service.users().threads().get(
                        userId="me",
                        id=thread_id,
                        format="metadata",
                        metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
                    ).execute()
                except Exception as e:
                    print(f"[WARN] thread 取得失敗 ({thread_id}): {e}")
                    continue

                thread_msgs = thread.get("messages", [])
                if not thread_msgs:
                    continue

                # スレッドの最新メッセージをチェック
                latest_msg = thread_msgs[-1]
                h = {
                    hdr["name"]: hdr["value"]
                    for hdr in latest_msg.get("payload", {}).get("headers", [])
                }
                from_hdr = h.get("From", "").lower()
                subject  = h.get("Subject", "(件名なし)")[:80]
                date_str = h.get("Date", "")
                to_hdr   = h.get("To", h.get("Cc", "unknown"))[:80]

                # 最新メッセージが自分でなければ相手が返信済み → スキップ
                if my_email not in from_hdr:
                    continue

                # 送信日時をパース
                try:
                    sent_dt = parsedate_to_datetime(date_str)
                    sent_ts = sent_dt.timestamp()
                except Exception:
                    continue

                if sent_ts > cutoff_ts or sent_ts < oldest_ts:
                    continue

                elapsed_h = int((now_ts - sent_ts) / 3600)
                waiting.append({
                    "subject":   subject,
                    "to":        to_hdr,
                    "sent_at":   datetime.fromtimestamp(sent_ts, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    ),
                    "elapsed_h": elapsed_h,
                    "elapsed_d": elapsed_h // 24,
                    "thread_id": thread_id,
                })

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        print(f"[INFO] Gmail: {total_msgs} 件確認 → {len(waiting)} 件が返信待ち")

    except FileNotFoundError as e:
        print(str(e))
    except Exception as e:
        print(f"[ERROR] Gmail チェック失敗: {e}")

    return waiting


def build_gmail_reminder(items: list[dict]) -> str:
    lines = [
        f":email: *Gmail: 返信待ち {len(items)} 件*"
        f"（{GMAIL_THRESHOLD_D}日以上経過）\n"
    ]
    for i, item in enumerate(items, 1):
        hours_rem = item["elapsed_h"] % 24
        lines.append(
            f"*{i}.* 宛先: {item['to']}\n"
            f"   件名: _{item['subject']}_\n"
            f"   送信: {item['sent_at']}（{item['elapsed_d']}日{hours_rem}時間前）\n"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def send_dm_reminder(text: str) -> None:
    dm_ch = get_my_dm_channel()
    slack_client.chat_postMessage(channel=dm_ch, text=text, mrkdwn=True)
    print("[INFO] DM を送信しました。")


def main() -> None:
    now_ts     = time.time()
    local_hour = datetime.fromtimestamp(now_ts).hour
    if local_hour not in ACTIVE_HOURS:
        print(
            f"[INFO] 現在 {local_hour}時 — "
            f"実行時間外（{ACTIVE_HOURS.start}〜{ACTIVE_HOURS.stop - 1}時のみ）のためスキップ。"
        )
        return

    print(f"[INFO] 開始: {datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}")

    reminders: list[str] = []

    # ── Slack チェック ──────────────────────────────────────────────────────────
    try:
        dm_items     = find_unanswered_slack_dms(now_ts)
        thread_items = find_unanswered_slack_threads(now_ts)
        if dm_items or thread_items:
            reminders.append(build_slack_reminder(dm_items, thread_items))
        else:
            print("[INFO] Slack: 返信待ちなし。")
    except Exception as e:
        print(f"[ERROR] Slack チェック失敗: {e}")

    # ── Gmail チェック ──────────────────────────────────────────────────────────
    if GMAIL_AVAILABLE:
        try:
            gmail_items = find_unanswered_gmail_threads(now_ts)
            if gmail_items:
                reminders.append(build_gmail_reminder(gmail_items))
            else:
                print("[INFO] Gmail: 返信待ちなし。")
        except Exception as e:
            print(f"[ERROR] Gmail チェック失敗: {e}")
    # ─────────────────────────────────────────────────────────────────────────

    if not reminders:
        print("[INFO] 返信待ちなし。リマインドは送りません。")
        return

    send_dm_reminder("\n\n".join(reminders))


if __name__ == "__main__":
    main()
